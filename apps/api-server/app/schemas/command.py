from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BrowserCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["open", "snapshot", "click", "fill", "press", "text", "tabs", "switch", "url", "title", "upload"]
    tab: str = Field(default="default", min_length=1, max_length=64)
    url: str | None = None
    ref: str | None = None
    text: str | None = None
    key: str | None = None
    target: str | None = None
    selector: str | None = None
    path: str | None = None
    index: int | None = Field(default=None, ge=0)
    interactive: bool = False

    @model_validator(mode="after")
    def required_parameters(self):
        required = {
            "open": ["url"],
            "click": ["ref"],
            "fill": ["ref", "text"],
            "press": ["key"],
            "text": ["target"],
            "switch": ["index"],
            "upload": ["selector", "path"],
        }
        for field in required.get(self.action, []):
            if getattr(self, field) is None:
                raise ValueError(f"{self.action} requires {field}")
        if self.url is not None and self.url != "about:blank" and not self.url.startswith(("https://", "http://")):
            raise ValueError("open supports http(s) URLs or about:blank")
        return self

    def worker_command(self):
        return {"action": self.action, "tab": self.tab, "params": self.model_dump(exclude={"action", "tab"}, exclude_none=True)}
