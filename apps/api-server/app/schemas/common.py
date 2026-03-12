from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiEnvelope(BaseModel, Generic[T]):
    code: int
    message: str
    data: T | None


def ok(data: T | None = None, *, message: str = "ok") -> ApiEnvelope[T]:
    return ApiEnvelope(code=0, message=message, data=data)
