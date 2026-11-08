import asyncio
from functools import lru_cache
from typing import Any, Dict, List, Optional
from app import prompts
from app.core.limits import FILE_READ_PAGE_CHARS, FILE_TEXT_CACHE_ENTRIES
from app.models.database import SessionLocal
from app.services import conversation_files as files
from app.services import file_builders
DELETE_FILE_TOOL_NAME = "delete_conversation_file"
FILE_TOOL_NAMES = (
    "list_conversation_files",
    "read_conversation_file",
    "create_conversation_file",
    "edit_conversation_file",
    DELETE_FILE_TOOL_NAME,
)
def _function(name: str, description: str, properties: Dict[str, Any], required: List[str]) -> Dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }
def file_tool_definitions() -> List[Dict[str, Any]]:
    file_id = {"type": "integer", "description": prompts.FILE_ID}
    content = {"type": "string", "description": prompts.FILE_CONTENT}
    sheets = {
        "type": "array",
        "description": prompts.FILE_SHEETS,
        "items": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "rows": {"type": "array", "items": {"type": "array", "items": {}}}},
            "required": ["name", "rows"],
        },
    }
    slides = {
        "type": "array",
        "description": prompts.FILE_SLIDES,
        "items": {
            "type": "object",
            "properties": {"title": {"type": "string"}, "bullets": {"type": "array", "items": {"type": "string"}}, "notes": {"type": "string"}},
            "required": ["title"],
        },
    }
    edits = {
        "type": "array",
        "description": prompts.FILE_EDITS,
        "items": {"type": "object", "properties": {"find": {"type": "string"}, "replace": {"type": "string"}}, "required": ["find", "replace"]},
    }
    cells = {
        "type": "array",
        "description": prompts.FILE_CELLS,
        "items": {"type": "object", "properties": {"sheet": {"type": "string"}, "cell": {"type": "string"}, "value": {}}, "required": ["sheet", "cell"]},
    }
    return [
        _function("list_conversation_files", prompts.LIST_FILES, {}, []),
        _function(
            "read_conversation_file",
            prompts.READ_FILE.format(page_chars=FILE_READ_PAGE_CHARS),
            {"file_id": file_id, "offset": {"type": "integer", "description": prompts.READ_FILE_OFFSET}},
            ["file_id"],
        ),
        _function(
            "create_conversation_file",
            prompts.CREATE_FILE,
            {
                "filename": {"type": "string", "description": prompts.CREATE_FILE_NAME.format(extensions="、".join(file_builders.CREATABLE_EXTENSIONS))},
                "content": content,
                "sheets": sheets,
                "slides": slides,
            },
            ["filename"],
        ),
        _function(
            "edit_conversation_file",
            prompts.EDIT_FILE,
            {"file_id": file_id, "edits": edits, "cells": cells, "content": content, "sheets": sheets, "slides": slides},
            ["file_id"],
        ),
        _function(DELETE_FILE_TOOL_NAME, prompts.DELETE_FILE, {"file_id": file_id}, ["file_id"]),
    ]
def _file_id(arguments: Dict[str, Any]) -> int:
    try:
        return int(arguments.get("file_id"))
    except (TypeError, ValueError) as e:
        raise files.ConversationFileError("file_id 必須是檔案編號（整數）") from e
def file_tool_approval(name: str, arguments: Dict[str, Any], user_id: Optional[int], conversation_id: Optional[int]) -> Optional[Dict[str, str]]:
    if name != DELETE_FILE_TOOL_NAME:
        return None
    target = f"#{arguments.get('file_id')}"
    if user_id is not None and conversation_id is not None:
        try:
            with SessionLocal() as db:
                file = files.get_file(db, _file_id(arguments), user_id, conversation_id, with_data=False)
                target = f"#{file.id}「{file.filename}」"
        except files.ConversationFileError:
            target = f"#{arguments.get('file_id')}（這個對話沒有此檔案）"
    return {"kind": "file", "display_name": prompts.DELETE_FILE_APPROVAL, "target": target}
def _list(user_id: int, conversation_id: int) -> Dict[str, Any]:
    with SessionLocal() as db:
        return {"files": [files.summary(file) for file in files.list_files(db, conversation_id, user_id)]}
def _load(user_id: int, conversation_id: int, file_id: int):
    with SessionLocal() as db:
        file = files.get_file(db, file_id, user_id, conversation_id, with_data=True)
        return files.summary(file), file.filename, file.data
@lru_cache(maxsize=FILE_TEXT_CACHE_ENTRIES)
def _file_text(user_id: int, conversation_id: int, file_id: int, created_at: Optional[str]) -> str:
    _, filename, data = _load(user_id, conversation_id, file_id)
    return file_builders.file_text(filename, data)
def _read(user_id: int, conversation_id: int, arguments: Dict[str, Any]) -> Dict[str, Any]:
    file_id = _file_id(arguments)
    try:
        offset = int(arguments.get("offset") or 0)
    except (TypeError, ValueError) as e:
        raise files.ConversationFileError("offset 必須是整數") from e
    with SessionLocal() as db:
        summary = files.summary(files.get_file(db, file_id, user_id, conversation_id, with_data=False))
    return {"file": summary, **file_builders.read_page(_file_text(user_id, conversation_id, file_id, summary["created_at"]), offset)}
def _save(user_id: int, conversation_id: int, filename: str, data: bytes, parent_id: Optional[int]) -> Dict[str, Any]:
    with SessionLocal() as db:
        parent = files.get_file(db, parent_id, user_id, conversation_id, with_data=False) if parent_id is not None else None
        return files.summary(files.add_file(
            db,
            conversation_id=conversation_id,
            user_id=user_id,
            filename=filename,
            data=data,
            origin="assistant",
            parent=parent,
            enforce_limits=True,
        ))
async def _create(user_id: int, conversation_id: int, arguments: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(arguments.get("filename"), str):
        raise files.ConversationFileError("filename 必須是含副檔名的檔名")
    filename = files.clean_filename(arguments["filename"])
    data = await asyncio.to_thread(file_builders.build_file, files.extension_of(filename), arguments)
    async with files.storage_lock:
        created = await asyncio.to_thread(_save, user_id, conversation_id, filename, data, None)
    return {"action": "created", "file": created, "message": prompts.FILE_CREATED.format(file_id=created["id"], filename=created["filename"])}
async def _edit(user_id: int, conversation_id: int, arguments: Dict[str, Any]) -> Dict[str, Any]:
    source, filename, data = await asyncio.to_thread(_load, user_id, conversation_id, _file_id(arguments))
    async with file_builders.extraction_slots:
        edited = await asyncio.to_thread(file_builders.edit_file, filename, data, arguments)
    async with files.storage_lock:
        updated = await asyncio.to_thread(_save, user_id, conversation_id, filename, edited, source["id"])
    return {
        "action": "updated",
        "file": updated,
        "source_file_id": source["id"],
        "message": prompts.FILE_UPDATED.format(source_id=source["id"], file_id=updated["id"], filename=updated["filename"]),
    }
def _delete(user_id: int, conversation_id: int, arguments: Dict[str, Any]) -> Dict[str, Any]:
    with SessionLocal() as db:
        removed = files.delete_file(db, _file_id(arguments), user_id, conversation_id)
    return {"action": "deleted", "file": removed, "message": prompts.FILE_DELETED.format(file_id=removed["id"], filename=removed["filename"])}
async def execute_file_tool(name: str, arguments: Dict[str, Any], user_id: Optional[int], conversation_id: Optional[int]) -> Dict[str, Any]:
    if user_id is None or conversation_id is None:
        return {"error": prompts.FILE_TOOLS_UNAVAILABLE}
    try:
        if name == "list_conversation_files":
            return await asyncio.to_thread(_list, user_id, conversation_id)
        if name == "read_conversation_file":
            async with file_builders.extraction_slots:
                return await asyncio.to_thread(_read, user_id, conversation_id, arguments)
        if name == "create_conversation_file":
            return await _create(user_id, conversation_id, arguments)
        if name == "edit_conversation_file":
            return await _edit(user_id, conversation_id, arguments)
        return await asyncio.to_thread(_delete, user_id, conversation_id, arguments)
    except files.AttachmentQuotaExceeded:
        return {"error": prompts.FILE_QUOTA_EXCEEDED}
    except files.ConversationFileError as e:
        return {"error": str(e)}