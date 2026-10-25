import json
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy.orm import Session

from app.core.error_response import log_and_get_error_id
from app.core.jwt_auth import get_current_admin_user
from app.core.limits import MAX_SKILL_ARCHIVE_BYTES
from app.core.security_logging import log_security_event
from app.core.user_context import get_current_user_id
from app.models import AgentSkill, AgentSkillSettingsUpdate, User
from app.models.database import get_db
from app.services.agent_skills import (
    SkillError,
    install_skill,
    list_skill_resources,
    load_skill,
    read_skill_upload,
    remove_skill_files,
    skill_files_present,
    skill_record_fields,
    skill_visible_to,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _json_or_none(value):
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _skill_response(skill: AgentSkill) -> Dict[str, Any]:
    return {
        "id": skill.id,
        "name": skill.name,
        "description": skill.description,
        "license": skill.license,
        "compatibility": skill.compatibility,
        "metadata": _json_or_none(skill.skill_metadata),
        "allowed_tools": skill.allowed_tools,
        "warnings": _json_or_none(skill.warnings) or [],
        "is_enabled": bool(skill.is_enabled),
        "allow_scripts": bool(skill.allow_scripts),
        "allowed_user_ids": None if skill.allowed_user_ids is None else (_json_or_none(skill.allowed_user_ids) or []),
        "files_present": skill_files_present(skill.name),
        "created_at": skill.created_at,
        "updated_at": skill.updated_at,
    }


def _get_skill(db: Session, skill_id: int) -> AgentSkill:
    skill = db.query(AgentSkill).filter(AgentSkill.id == skill_id).first()
    if not skill:
        raise HTTPException(status_code=404, detail="找不到該技能")
    return skill


@router.get("/enabled")
def get_enabled_skills(db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    skills = db.query(AgentSkill).filter(AgentSkill.is_enabled == True).order_by(AgentSkill.name).all()
    return {
        "status": "success",
        "skills": [
            {"name": s.name, "description": s.description}
            for s in skills
            if skill_files_present(s.name) and skill_visible_to(s.allowed_user_ids, user_id)
        ],
    }


@router.get("")
def get_all_skills(db: Session = Depends(get_db), current_user: dict = Depends(get_current_admin_user)):
    skills = db.query(AgentSkill).order_by(AgentSkill.name).all()
    return {"status": "success", "total": len(skills), "skills": [_skill_response(s) for s in skills]}


@router.get("/{skill_id}")
def get_skill_detail(skill_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_admin_user)):
    skill = _get_skill(db, skill_id)
    detail = _skill_response(skill)
    try:
        detail["body"] = load_skill(skill.name).body
    except SkillError as e:
        error_id = log_and_get_error_id(logger, f"讀取技能 {skill.name} 失敗", e, logging.WARNING)
        detail["body"] = None
        detail["load_error"] = f"無法讀取 SKILL.md，請重新上傳技能（錯誤代碼：{error_id}）"
    detail["resources"], detail["resources_truncated"] = list_skill_resources(skill.name)
    return {"status": "success", "skill": detail}


@router.post("/upload")
async def upload_skill(
    request: Request,
    file: UploadFile = File(...),
    replace: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin_user),
):
    data = await file.read(MAX_SKILL_ARCHIVE_BYTES + 1)
    try:
        parsed, files = read_skill_upload(file.filename or "", data)
    except SkillError as e:
        raise HTTPException(status_code=400, detail=str(e))

    existing = db.query(AgentSkill).filter(AgentSkill.name == parsed.name).first()
    if existing and not replace:
        raise HTTPException(status_code=409, detail=f"已存在同名技能：{parsed.name}")
    try:
        install_skill(parsed, files, replace=replace)
    except SkillError as e:
        raise HTTPException(status_code=400, detail=str(e))

    fields = skill_record_fields(parsed)
    if existing:
        for key, value in fields.items():
            setattr(existing, key, value)
        skill = existing
    else:
        skill = AgentSkill(name=parsed.name, is_enabled=True, allow_scripts=False, created_by=current_user["user_id"], **fields)
        db.add(skill)
    db.commit()
    db.refresh(skill)
    log_security_event(
        "ADMIN_SKILL_INSTALLED",
        request=request,
        user_id=current_user["user_id"],
        details={"skill": parsed.name, "replaced": existing is not None, "files": len(files)},
    )
    action = "更新" if existing else "安裝"
    return {"status": "success", "message": f"已{action}技能「{parsed.name}」", "skill": _skill_response(skill)}


@router.patch("/{skill_id}/toggle")
def toggle_skill(skill_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_admin_user)):
    skill = _get_skill(db, skill_id)
    skill.is_enabled = not skill.is_enabled
    db.commit()
    db.refresh(skill)
    return {
        "status": "success",
        "is_enabled": skill.is_enabled,
        "message": f"技能已{'啟用' if skill.is_enabled else '停用'}",
    }


@router.patch("/{skill_id}/settings")
def update_skill_settings(
    skill_id: int,
    settings_data: AgentSkillSettingsUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin_user),
):
    skill = _get_skill(db, skill_id)
    if settings_data.allow_scripts is not None:
        skill.allow_scripts = settings_data.allow_scripts
    if settings_data.allowed_user_ids is not None:
        user_ids = sorted(set(settings_data.allowed_user_ids))
        existing = {row.id for row in db.query(User.id).filter(User.id.in_(user_ids)).all()} if user_ids else set()
        missing = [user_id for user_id in user_ids if user_id not in existing]
        if missing:
            raise HTTPException(status_code=400, detail=f"找不到使用者：{', '.join(map(str, missing))}")
        skill.allowed_user_ids = json.dumps(user_ids) if user_ids else None
    db.commit()
    db.refresh(skill)
    log_security_event(
        "ADMIN_SKILL_SETTINGS_UPDATED",
        request=request,
        user_id=current_user["user_id"],
        details={"skill": skill.name, "allow_scripts": bool(skill.allow_scripts), "allowed_user_ids": _json_or_none(skill.allowed_user_ids)},
    )
    return {"status": "success", "message": "技能設定已更新", "skill": _skill_response(skill)}


@router.delete("/{skill_id}")
def delete_skill(
    skill_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin_user),
):
    skill = _get_skill(db, skill_id)
    name = skill.name
    db.delete(skill)
    db.commit()
    remove_skill_files(name)
    log_security_event("ADMIN_SKILL_DELETED", request=request, user_id=current_user["user_id"], details={"skill": name})
    return {"status": "success", "message": f"已刪除技能「{name}」"}
