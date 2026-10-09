"""Authentication endpoints — login and current-user lookup."""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.api.database import get_db
from src.api.models.db_models import User
from src.api.models.schemas import LoginRequest, TokenResponse, UserResponse
from src.api.utils.security import create_access_token, get_current_user, verify_password

logger = logging.getLogger("nairobifloodwatch.auth")
router = APIRouter()


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    try:
        user.last_login = datetime.now(timezone.utc)
        db.commit()
        db.refresh(user)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("login: failed to update last_login: %s", exc)
        raise HTTPException(status_code=500, detail="Database error occurred")

    token = create_access_token({"sub": user.email, "role": user.role, "user_id": user.id})
    return TokenResponse(access_token=token, token_type="bearer", user=UserResponse.model_validate(user))


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return current_user
