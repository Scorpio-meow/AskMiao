import asyncio
import codecs
import io
import json
import re
import secrets
import shutil
import stat
import sys
import tempfile
import time
import threading
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Tuple

import yaml

from app.core.config import settings
from app.core.limits import (
    MAX_SKILL_ARCHIVE_BYTES,
    MAX_SKILL_FILES,
    MAX_SKILL_MD_BYTES,
    MAX_SKILL_RESOURCE_CHARS,
    MAX_SKILL_RESOURCE_LISTING,
    MAX_CONCURRENT_SKILL_SCRIPTS,
    MAX_SKILL_SCRIPT_ARG_CHARS,
    MAX_SKILL_SCRIPT_ARGS,
    MAX_SKILL_SCRIPT_OUTPUT_CHARS,
    MAX_SKILL_SCRIPT_SECONDS,
    MAX_SKILL_SCRIPT_STDIN_CHARS,
    MAX_SKILL_UNCOMPRESSED_BYTES,
)

SKILL_FILE = "SKILL.md"
SKILL_NAME_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
MAX_SKILL_NAME_CHARS = 64
MAX_SKILL_DESCRIPTION_CHARS = 1024
MAX_SKILL_COMPATIBILITY_CHARS = 500
KNOWN_FIELDS = ("name", "description", "license", "compatibility", "metadata", "allowed-tools")
IGNORED_ARCHIVE_PARTS = ("__MACOSX", ".DS_Store", ".git")
TEMP_PREFIX = ".tmp-"
STALE_PREFIX = ".old-"

_install_lock = threading.Lock()


class SkillError(ValueError):
    pass


@dataclass
class ParsedSkill:
    name: str
    description: str
    body: str
    license: Optional[str] = None
    compatibility: Optional[str] = None
    metadata: Optional[Dict[str, str]] = None
    allowed_tools: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


def skills_root() -> Path:
    return Path(settings.SKILLS_DIR)


def _split_frontmatter(text: str) -> Tuple[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise SkillError("SKILL.md 必須以 --- 開頭的 YAML frontmatter 起始")
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "\n".join(lines[1:index]), "\n".join(lines[index + 1:]).strip()
    raise SkillError("SKILL.md 的 YAML frontmatter 缺少結尾的 ---")


def _quote_colon_values(frontmatter: str) -> str:
    fixed = []
    for line in frontmatter.splitlines():
        match = re.match(r"^([A-Za-z0-9_-]+):\s+(.*)$", line)
        if match and ": " in match.group(2) and match.group(2)[0] not in "\"'|>[{":
            fixed.append(f"{match.group(1)}: |-")
            fixed.append(f"  {match.group(2)}")
        else:
            fixed.append(line)
    return "\n".join(fixed)


def _load_frontmatter(frontmatter: str) -> Dict[str, Any]:
    try:
        data = yaml.safe_load(frontmatter)
    except yaml.YAMLError:
        try:
            data = yaml.safe_load(_quote_colon_values(frontmatter))
        except yaml.YAMLError as e:
            raise SkillError("SKILL.md 的 YAML frontmatter 無法解析") from e
    if not isinstance(data, dict):
        raise SkillError("SKILL.md 的 YAML frontmatter 必須是鍵值對應")
    return data


def _optional_text(data: Dict[str, Any], key: str) -> Optional[str]:
    value = data.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_skill_md(text: str, directory_name: Optional[str] = None) -> ParsedSkill:
    frontmatter, body = _split_frontmatter(text)
    data = _load_frontmatter(frontmatter)
    warnings: List[str] = []

    name = _optional_text(data, "name")
    if not name:
        raise SkillError("SKILL.md 缺少 name 欄位")
    if len(name) > MAX_SKILL_NAME_CHARS or not SKILL_NAME_PATTERN.fullmatch(name):
        raise SkillError(
            f"技能名稱「{name[:MAX_SKILL_NAME_CHARS]}」不合規：只能用小寫英數與連字號、最多 {MAX_SKILL_NAME_CHARS} 字，"
            "不以連字號開頭或結尾，也不含連續連字號"
        )
    if directory_name and directory_name != name:
        warnings.append(f"name「{name}」與技能目錄名稱「{directory_name}」不同，已以 name 作為目錄名稱安裝")

    description = _optional_text(data, "description")
    if not description:
        raise SkillError("SKILL.md 缺少 description 欄位，Agent 無法判斷何時使用此技能")
    if len(description) > MAX_SKILL_DESCRIPTION_CHARS:
        warnings.append(f"description 超過 {MAX_SKILL_DESCRIPTION_CHARS} 字")

    compatibility = _optional_text(data, "compatibility")
    if compatibility and len(compatibility) > MAX_SKILL_COMPATIBILITY_CHARS:
        warnings.append(f"compatibility 超過 {MAX_SKILL_COMPATIBILITY_CHARS} 字")

    metadata = data.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        warnings.append("metadata 應為鍵值對應，已忽略")
        metadata = None
    if metadata is not None:
        metadata = {str(k): "" if v is None else str(v) for k, v in metadata.items()}

    allowed_tools = _optional_text(data, "allowed-tools")
    unknown = sorted(str(k) for k in data if k not in KNOWN_FIELDS)
    if unknown:
        warnings.append(f"規格未定義的欄位：{', '.join(unknown)}")
    if not body:
        warnings.append("SKILL.md 沒有指示內容")

    return ParsedSkill(
        name=name,
        description=description,
        body=body,
        license=_optional_text(data, "license"),
        compatibility=compatibility,
        metadata=metadata,
        allowed_tools=allowed_tools,
        warnings=warnings,
    )


def _decode_skill_md(data: bytes) -> str:
    if len(data) > MAX_SKILL_MD_BYTES:
        raise SkillError(f"SKILL.md 超過 {MAX_SKILL_MD_BYTES // 1024} KiB")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise SkillError("SKILL.md 必須是 UTF-8 文字檔") from e


def _is_ignored(parts: Tuple[str, ...]) -> bool:
    return any(part in IGNORED_ARCHIVE_PARTS for part in parts)


def _archive_members(archive: zipfile.ZipFile) -> List[Tuple[zipfile.ZipInfo, Tuple[str, ...]]]:
    members = []
    declared_total = 0
    for info in archive.infolist():
        raw = info.filename.replace("\\", "/")
        path = PurePosixPath(raw)
        if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw) or ".." in path.parts:
            raise SkillError(f"壓縮檔含不安全的路徑：{info.filename}")
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise SkillError(f"壓縮檔不可包含符號連結：{info.filename}")
        if info.is_dir():
            continue
        parts = tuple(p for p in path.parts if p not in ("", "."))
        if not parts or _is_ignored(parts):
            continue
        members.append((info, parts))
        declared_total += info.file_size
        if len(members) > MAX_SKILL_FILES:
            raise SkillError(f"技能檔案數超過 {MAX_SKILL_FILES} 個")
        if declared_total > MAX_SKILL_UNCOMPRESSED_BYTES:
            raise SkillError(f"技能解壓後超過 {MAX_SKILL_UNCOMPRESSED_BYTES // (1024 * 1024)} MiB")
    return members


def _strip_top_directory(members: List[Tuple[zipfile.ZipInfo, Tuple[str, ...]]]) -> Tuple[List[Tuple[zipfile.ZipInfo, Tuple[str, ...]]], Optional[str]]:
    if any(parts == (SKILL_FILE,) for _, parts in members):
        return members, None
    tops = {parts[0] for _, parts in members}
    if len(tops) == 1:
        top = next(iter(tops))
        stripped = [(info, parts[1:]) for info, parts in members if len(parts) > 1]
        if any(parts == (SKILL_FILE,) for _, parts in stripped):
            return stripped, top
    raise SkillError("壓縮檔根目錄或唯一的頂層目錄中找不到 SKILL.md")


def _read_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo, budget: int) -> bytes:
    with archive.open(info) as source:
        data = source.read(budget + 1)
    if len(data) > budget:
        raise SkillError(f"技能解壓後超過 {MAX_SKILL_UNCOMPRESSED_BYTES // (1024 * 1024)} MiB")
    return data


def _extract_archive(data: bytes) -> Tuple[ParsedSkill, Dict[Tuple[str, ...], bytes]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise SkillError("不是有效的 zip 壓縮檔") from e
    with archive:
        members, top = _strip_top_directory(_archive_members(archive))
        files: Dict[Tuple[str, ...], bytes] = {}
        remaining = MAX_SKILL_UNCOMPRESSED_BYTES
        for info, parts in members:
            content = _read_member(archive, info, remaining)
            remaining -= len(content)
            files[parts] = content
    skill = parse_skill_md(_decode_skill_md(files[(SKILL_FILE,)]), directory_name=top)
    return skill, files


def read_skill_upload(filename: str, data: bytes) -> Tuple[ParsedSkill, Dict[Tuple[str, ...], bytes]]:
    if len(data) > MAX_SKILL_ARCHIVE_BYTES:
        raise SkillError(f"上傳檔超過 {MAX_SKILL_ARCHIVE_BYTES // (1024 * 1024)} MiB")
    lower = (filename or "").lower()
    if lower.endswith(".zip") or lower.endswith(".skill"):
        return _extract_archive(data)
    if lower.endswith(".md"):
        return parse_skill_md(_decode_skill_md(data)), {(SKILL_FILE,): data}
    raise SkillError("請上傳技能目錄的 .zip 壓縮檔或 SKILL.md")


def install_skill(skill: ParsedSkill, files: Dict[Tuple[str, ...], bytes], replace: bool) -> None:
    root = skills_root()
    root.mkdir(parents=True, exist_ok=True)
    target = root / skill.name
    with _install_lock:
        if target.exists() and not replace:
            raise SkillError(f"已存在同名技能：{skill.name}")
        staging = root / f"{TEMP_PREFIX}{skill.name}-{secrets.token_hex(4)}"
        stale = root / f"{STALE_PREFIX}{skill.name}-{secrets.token_hex(4)}"
        try:
            for parts, content in files.items():
                path = staging.joinpath(*parts)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            if target.exists():
                target.rename(stale)
            try:
                staging.rename(target)
            except OSError:
                if stale.exists():
                    stale.rename(target)
                raise
        except OSError as e:
            raise SkillError("技能檔案無法寫入，請確認壓縮檔內沒有重複或不合法的檔名") from e
        finally:
            shutil.rmtree(staging, ignore_errors=True)
            shutil.rmtree(stale, ignore_errors=True)


def remove_skill_files(name: str) -> None:
    target = skill_directory(name)
    if target is not None and target.exists():
        with _install_lock:
            shutil.rmtree(target)


def skill_directory(name: str) -> Optional[Path]:
    if not SKILL_NAME_PATTERN.fullmatch(name or ""):
        return None
    return skills_root() / name


def skill_files_present(name: str) -> bool:
    directory = skill_directory(name)
    return directory is not None and (directory / SKILL_FILE).is_file()


def load_skill(name: str) -> ParsedSkill:
    directory = skill_directory(name)
    if directory is None or not (directory / SKILL_FILE).is_file():
        raise SkillError(f"找不到技能檔案：{name}")
    return parse_skill_md(_decode_skill_md((directory / SKILL_FILE).read_bytes()), directory_name=name)


def list_skill_resources(name: str) -> Tuple[List[str], bool]:
    directory = skill_directory(name)
    if directory is None or not directory.is_dir():
        return [], False
    resources = sorted(
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*")
        if path.is_file() and not path.is_symlink() and path.relative_to(directory).as_posix() != SKILL_FILE
    )
    return resources[:MAX_SKILL_RESOURCE_LISTING], len(resources) > MAX_SKILL_RESOURCE_LISTING


def _skill_file(name: str, relative_path: str) -> Tuple[Optional[Path], Optional[PurePosixPath], Dict[str, Any]]:
    directory = skill_directory(name)
    if directory is None or not directory.is_dir():
        return None, None, {"error": f"找不到技能：{name}"}
    raw = (relative_path or "").replace("\\", "/").strip()
    path = PurePosixPath(raw)
    if not raw or path.is_absolute() or ".." in path.parts or re.match(r"^[A-Za-z]:", raw):
        return None, None, {"error": "path 必須是技能目錄內的相對路徑，例如 references/REFERENCE.md"}
    target = directory.joinpath(*path.parts)
    try:
        resolved = target.resolve(strict=True)
    except (FileNotFoundError, OSError):
        return None, None, {"error": f"技能「{name}」中沒有這個檔案：{raw}"}
    if directory.resolve() not in resolved.parents or target.is_symlink() or not resolved.is_file():
        return None, None, {"error": f"技能「{name}」中沒有這個檔案：{raw}"}
    return resolved, path, {}


def read_skill_resource(name: str, relative_path: str) -> Dict[str, Any]:
    resolved, path, error = _skill_file(name, relative_path)
    if resolved is None:
        return error
    raw = path.as_posix()
    byte_budget = MAX_SKILL_RESOURCE_CHARS * 4
    with open(resolved, "rb") as handle:
        data = handle.read(byte_budget + 1)
    cut = len(data) > byte_budget
    try:
        text = codecs.getincrementaldecoder("utf-8")().decode(data[:byte_budget], final=not cut)
    except UnicodeDecodeError:
        return {"error": f"{raw} 不是 UTF-8 文字檔，無法讀取"}
    truncated = cut or len(text) > MAX_SKILL_RESOURCE_CHARS
    return {
        "skill": name,
        "path": raw,
        "truncated": truncated,
        "content": format_skill_resource(name, raw, text[:MAX_SKILL_RESOURCE_CHARS], truncated),
    }


def format_skill_activation(skill: ParsedSkill, resources: List[str], listing_truncated: bool, allow_scripts: bool) -> str:
    body = skill.body
    truncated_note = ""
    if len(body) > MAX_SKILL_RESOURCE_CHARS:
        body = body[:MAX_SKILL_RESOURCE_CHARS]
        truncated_note = "\n[技能指示過長，以下已截斷]"
    parts = [f'<skill_content name="{skill.name}">', body + truncated_note]
    if skill.compatibility:
        parts.append(f"\n相容性說明：{skill.compatibility}")
    script_note = (
        "技能指示要求執行腳本時以 run_skill_script 執行。"
        if allow_scripts
        else "本系統不會執行技能內的腳本，腳本只能讀取內容參考。"
    )
    parts.append(f"\n技能中的相對路徑以技能目錄為基準；需要時以 read_skill_resource 讀取，{script_note}")
    if resources:
        listing = "\n".join(f"  <file>{path}</file>" for path in resources)
        more = "\n  <!-- 檔案過多，清單不完整 -->" if listing_truncated else ""
        parts.append(f"<skill_resources>\n{listing}{more}\n</skill_resources>")
    parts.append("</skill_content>")
    return "\n".join(parts)


def format_skill_resource(name: str, path: str, text: str, truncated: bool) -> str:
    note = "\n[檔案過長，以下已截斷]" if truncated else ""
    return f'<skill_resource skill="{name}" path="{path}">\n{text}{note}\n</skill_resource>'


def allowed_tool_names(allowed_tools: Optional[str]) -> List[str]:
    return [token.split("(", 1)[0] for token in (allowed_tools or "").split() if token.split("(", 1)[0]]


def activate_skill(name: str, allow_scripts: bool) -> Dict[str, Any]:
    try:
        skill = load_skill(name)
    except SkillError as e:
        return {"error": str(e)}
    resources, listing_truncated = list_skill_resources(name)
    return {
        "skill": name,
        "allowed_tools": allowed_tool_names(skill.allowed_tools),
        "content": format_skill_activation(skill, resources, listing_truncated, allow_scripts),
    }


def skill_visible_to(allowed_user_ids: Optional[str], user_id: Optional[int]) -> bool:
    if allowed_user_ids is None:
        return True
    try:
        users = json.loads(allowed_user_ids)
    except json.JSONDecodeError:
        return False
    return isinstance(users, list) and user_id is not None and user_id in users


def script_interpreter(path: PurePosixPath) -> Optional[List[str]]:
    suffix = path.suffix.lower()
    if suffix == ".py":
        return [sys.executable, "-I"]
    program = {".sh": "bash", ".js": "node", ".mjs": "node"}.get(suffix)
    located = shutil.which(program) if program else None
    return [located] if located else None


_script_slots = asyncio.Semaphore(MAX_CONCURRENT_SKILL_SCRIPTS)


async def _read_capped(stream: asyncio.StreamReader) -> Tuple[str, bool]:
    kept = bytearray()
    truncated = False
    while True:
        chunk = await stream.read(65536)
        if not chunk:
            break
        room = MAX_SKILL_SCRIPT_OUTPUT_CHARS * 4 - len(kept)
        if room > 0:
            kept.extend(chunk[:room])
        if len(chunk) > max(room, 0):
            truncated = True
    text = kept.decode("utf-8", errors="replace")
    return text[:MAX_SKILL_SCRIPT_OUTPUT_CHARS], truncated or len(text) > MAX_SKILL_SCRIPT_OUTPUT_CHARS


async def run_skill_script(name: str, relative_path: str, args: Any, stdin_text: Any) -> Dict[str, Any]:
    from app.services.mcp_service import PROCESS_GROUP_KWARGS, build_stdio_env, kill_process_tree

    resolved, path, error = _skill_file(name, relative_path)
    if resolved is None:
        return error
    interpreter = script_interpreter(path)
    if interpreter is None:
        return {"error": f"不支援執行 {path.suffix or '沒有副檔名的'} 檔案，或主機上沒有對應的直譯器"}
    if args is None:
        args = []
    if not isinstance(args, list) or len(args) > MAX_SKILL_SCRIPT_ARGS or any(
        not isinstance(arg, (str, int, float)) or len(str(arg)) > MAX_SKILL_SCRIPT_ARG_CHARS for arg in args
    ):
        return {"error": f"args 必須是最多 {MAX_SKILL_SCRIPT_ARGS} 個、每個最多 {MAX_SKILL_SCRIPT_ARG_CHARS} 字的字串陣列"}
    stdin_bytes = str(stdin_text or "")[:MAX_SKILL_SCRIPT_STDIN_CHARS].encode("utf-8")
    start = time.time()
    async with _script_slots:
        with tempfile.TemporaryDirectory(prefix="askmiao-skill-") as workdir:
            copy = Path(workdir) / name
            await asyncio.to_thread(shutil.copytree, skill_directory(name), copy, symlinks=False)
            process = await asyncio.create_subprocess_exec(
                *interpreter, str(copy.joinpath(*path.parts)), *[str(arg) for arg in args],
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=build_stdio_env({}),
                cwd=str(copy),
                **PROCESS_GROUP_KWARGS,
            )

            async def communicate():
                async def feed():
                    try:
                        process.stdin.write(stdin_bytes)
                        await process.stdin.drain()
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    finally:
                        process.stdin.close()
                _, stdout, stderr = await asyncio.gather(feed(), _read_capped(process.stdout), _read_capped(process.stderr))
                await process.wait()
                return stdout, stderr

            timed_out = False
            try:
                (stdout, stdout_cut), (stderr, stderr_cut) = await asyncio.wait_for(communicate(), timeout=MAX_SKILL_SCRIPT_SECONDS)
            except asyncio.TimeoutError:
                timed_out = True
                stdout, stdout_cut, stderr, stderr_cut = "", False, "", False
            finally:
                if process.returncode is None:
                    await kill_process_tree(process)
                    try:
                        await asyncio.wait_for(process.wait(), timeout=5)
                    except asyncio.TimeoutError:
                        process.kill()
    return {
        "skill": name,
        "path": path.as_posix(),
        "exit_code": process.returncode,
        "timed_out": timed_out,
        "duration_seconds": round(time.time() - start, 3),
        "stdout": stdout,
        "stderr": stderr,
        "output_truncated": stdout_cut or stderr_cut,
    }


def skill_record_fields(skill: ParsedSkill) -> Dict[str, Any]:
    return {
        "description": skill.description,
        "license": skill.license,
        "compatibility": skill.compatibility,
        "skill_metadata": json.dumps(skill.metadata, ensure_ascii=False) if skill.metadata else None,
        "allowed_tools": skill.allowed_tools,
        "warnings": json.dumps(skill.warnings, ensure_ascii=False) if skill.warnings else None,
    }


def cleanup_staging_directories() -> None:
    root = skills_root()
    if not root.is_dir():
        return
    for entry in root.iterdir():
        if entry.is_dir() and entry.name.startswith((TEMP_PREFIX, STALE_PREFIX)):
            shutil.rmtree(entry, ignore_errors=True)
