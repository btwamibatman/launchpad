"""Контракт API: что принимаем и что отдаём."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ItemStatus = Literal["todo", "in_progress", "done"]


class ItemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    status: ItemStatus = "todo"


class ItemUpdate(BaseModel):
    """PATCH: поля можно пропустить, но переданные значения не могут быть null."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: ItemStatus | None = None

    @field_validator("title", "description", "status")
    @classmethod
    def reject_null(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("Field cannot be null")
        return value


class ItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    status: ItemStatus
    created_at: datetime
    updated_at: datetime
