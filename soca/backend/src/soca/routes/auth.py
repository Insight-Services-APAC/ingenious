"""Authentication routes for SoCa API."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from soca.auth import authenticate_user, create_access_token, get_current_user
from soca.models import LoginRequest, LoginResponse, User

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest) -> LoginResponse:
    """Login with email and password."""
    user = authenticate_user(request.email, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": user.id, "email": user.email})
    return LoginResponse(token=token, user=user)


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Get current user info."""
    return {"user": current_user}
