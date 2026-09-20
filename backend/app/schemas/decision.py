"""Review decision Pydantic schemas module."""

from __future__ import annotations

import enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DecisionType(enum.StrEnum):
    """Explicit review decisions supported by review workflow."""

    NO_ACTION = "no_action"
    CLIP_SELECTED = "clip_selected"


class VideoDecisionRequest(BaseModel):
    """Payload for submitting an explicit review decision on a video."""

    decision: DecisionType | None = Field(
        default=None, description="Explicit review decision: no_action or clip_selected"
    )
    status: DecisionType | None = Field(
        default=None, description="Alternative alias for decision: no_action or clip_selected"
    )

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def validate_input(cls, data: Any) -> Any:
        """Ensure either 'decision' or 'status' is supplied in the request body."""
        if isinstance(data, dict):
            if "decision" not in data and "status" not in data:
                raise ValueError("Either 'decision' or 'status' field must be provided.")
        return data

    @property
    def decision_value(self) -> DecisionType:
        """Return resolved decision enum value."""
        target = self.decision or self.status
        if target is None:
            raise ValueError("Either 'decision' or 'status' must be provided.")
        return target
