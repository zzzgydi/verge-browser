from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class MouseButton(StrEnum):
    left = "left"
    middle = "middle"
    right = "right"


class BrowserActionType(StrEnum):
    MOVE_TO = "MOVE_TO"
    CLICK = "CLICK"
    DOUBLE_CLICK = "DOUBLE_CLICK"
    RIGHT_CLICK = "RIGHT_CLICK"
    MOUSE_DOWN = "MOUSE_DOWN"
    MOUSE_UP = "MOUSE_UP"
    DRAG_TO = "DRAG_TO"
    SCROLL = "SCROLL"
    TYPE_TEXT = "TYPE_TEXT"
    KEY_PRESS = "KEY_PRESS"
    HOTKEY = "HOTKEY"
    WAIT = "WAIT"


class BrowserAction(BaseModel):
    type: BrowserActionType
    x: int | None = None
    y: int | None = None
    button: MouseButton = MouseButton.left
    text: str | None = None
    key: str | None = None
    keys: list[str] = Field(default_factory=list)
    duration_ms: int | None = Field(default=None, ge=0)
    delta_x: int | None = None
    delta_y: int | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> "BrowserAction":
        if self.type == BrowserActionType.TYPE_TEXT and not self.text:
            raise ValueError("TYPE_TEXT requires text")
        if self.type == BrowserActionType.KEY_PRESS and not self.key:
            raise ValueError("KEY_PRESS requires key")
        if self.type == BrowserActionType.HOTKEY and not self.keys:
            raise ValueError("HOTKEY requires keys")
        if self.type == BrowserActionType.WAIT and self.duration_ms is None:
            raise ValueError("WAIT requires duration_ms")
        return self


class BrowserActionsRequest(BaseModel):
    actions: list[BrowserAction] = Field(min_length=1)
    continue_on_error: bool = False
    screenshot_after: bool = False


class BrowserActionsResponse(BaseModel):
    ok: bool
    executed: int
    screenshot_after: bool
    errors: list[str]


class ScreenshotType(StrEnum):
    window = "window"
    page = "page"


class ScreenshotMetadata(BaseModel):
    width: int
    height: int
    page_viewport: dict[str, int]
    window_viewport: dict[str, int]
    window_id: str | None = None


class ScreenshotEnvelope(BaseModel):
    type: ScreenshotType
    format: Literal["png", "jpeg", "webp"]
    media_type: str
    metadata: ScreenshotMetadata
    data_base64: str
