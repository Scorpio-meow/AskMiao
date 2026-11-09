from typing import List, Optional
from sqlalchemy.orm import Session
from app import prompts
from app.models import AgentInstruction
def _rows(db: Session, user_id: Optional[int]) -> List[AgentInstruction]:
    query = db.query(AgentInstruction)
    query = query.filter(AgentInstruction.user_id.is_(None)) if user_id is None else query.filter(AgentInstruction.user_id == user_id)
    return query.order_by(AgentInstruction.id).all()
def get_instructions(db: Session, user_id: Optional[int]) -> str:
    rows = _rows(db, user_id)
    return rows[0].content if rows else ""
def set_instructions(db: Session, user_id: Optional[int], content: str) -> str:
    content = content.strip()
    rows = _rows(db, user_id)
    row = rows[0] if rows else None
    for duplicate in rows[1:]:
        db.delete(duplicate)
    if not content:
        if row is not None:
            db.delete(row)
    elif row is None:
        db.add(AgentInstruction(user_id=user_id, content=content))
    else:
        row.content = content
    db.commit()
    return content
def delete_user_instructions(db: Session, user_id: int) -> None:
    db.query(AgentInstruction).filter(AgentInstruction.user_id == user_id).delete(synchronize_session=False)
def instructions_prompt(db: Session, user_id: Optional[int]) -> str:
    organization = get_instructions(db, None)
    personal = get_instructions(db, user_id) if user_id is not None else ""
    parts = []
    if organization:
        parts.append(prompts.ORGANIZATION_INSTRUCTIONS.format(content=organization))
    if personal:
        parts.append(prompts.PERSONAL_INSTRUCTIONS.format(content=personal))
    return "".join(parts)