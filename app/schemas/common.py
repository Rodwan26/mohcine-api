from decimal import Decimal
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class CursorPage(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: Optional[str] = None
    has_more: bool = False
    limit: int = 20
