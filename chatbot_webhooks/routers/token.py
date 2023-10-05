# -*- coding: utf-8 -*-
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from tortoise.contrib.pydantic import pydantic_model_creator

from chatbot_webhooks.dependencies import validate_token
from chatbot_webhooks.models import User

TokenInPydantic = pydantic_model_creator(
    User, name="TokenIn", include=["username", "token", "token_expiry"], optional=["token_expiry"]
)
TokenOutPydantic = pydantic_model_creator(
    User, name="TokenIn", include=["username", "token", "token_expiry"]
)

router = APIRouter(prefix="/token", tags=["token"], dependencies=[Depends(validate_token)])


@router.get("/")
async def get_tokens() -> list[TokenOutPydantic]:
    """Get all tokens."""
    return await TokenOutPydantic.from_queryset(User.all())


@router.post("/", status_code=201)
async def create_token(user_info: TokenInPydantic) -> TokenOutPydantic:
    """Create a new token."""
    user = await User.create(**user_info.dict(exclude_unset=True), token=uuid4())
    logger.info(f"Created token for user {user.username}")
    return await TokenOutPydantic.from_tortoise_orm(user)


@router.post("/{token_id}/deactivate")
async def deactivate_token(token_id: int) -> None:
    """Deactivate a token."""
    user = await User.get_or_none(id=token_id)
    if not user:
        raise HTTPException(status_code=404, detail="Token not found")
    user.is_active = False
    await user.save()
    logger.info(f"Deactivated token for user {user.username}")


@router.post("/{token_id}/activate")
async def activate_token(token_id: int) -> None:
    """Activate a token."""
    user = await User.get_or_none(id=token_id)
    if not user:
        raise HTTPException(status_code=404, detail="Token not found")
    user.is_active = True
    await user.save()
    logger.info(f"Activated token for user {user.username}")
