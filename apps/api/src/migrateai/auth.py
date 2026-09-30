import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Request
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .entities import User, UserSession, WorkspaceMember

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    if len(password) < 12 or len(password) > 256:
        raise HTTPException(422, "Password must be between 12 and 256 characters.")
    return password_hash.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return password_hash.verify(password, encoded)
    except UnknownHashError:
        return False


def create_session(user_id: str, db: Session) -> str:
    token = secrets.token_urlsafe(32)
    token_id = hashlib.sha256(token.encode()).hexdigest()
    expiry = datetime.now(UTC) + timedelta(hours=8)
    db.add(UserSession(id=token_id, user_id=user_id, expires_at=expiry))
    return token


def session_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get("migrateai_session")
    if not token:
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    token_id = hashlib.sha256(token.encode()).hexdigest()
    session = db.get(UserSession, token_id)
    if session is None:
        raise HTTPException(status_code=401, detail="Session expired. Sign in again.")
    expires_at = (
        session.expires_at.replace(tzinfo=UTC)
        if session.expires_at.tzinfo is None
        else session.expires_at
    )
    if expires_at <= datetime.now(UTC):
        db.delete(session)
        db.commit()
        raise HTTPException(status_code=401, detail="Session expired. Sign in again.")
    user = db.get(User, session.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Account not found.")
    return user


def require_workspace(workspace_id: str, user: User, db: Session) -> WorkspaceMember:
    member = db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
    )
    if member is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    return member


def require_role(member: WorkspaceMember, minimum: str = "member") -> None:
    hierarchy = {"viewer": 0, "member": 1, "admin": 2, "owner": 3}
    if hierarchy.get(member.role, -1) < hierarchy[minimum]:
        raise HTTPException(
            status_code=403, detail="Your workspace role does not allow this action."
        )
