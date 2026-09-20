"""Clip segment Pydantic schemas module."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator


def validate_finite_nonnegative(value: float, field_name: str) -> float:
    """Validate that a float value is finite and non-negative."""
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be a finite number")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return value


def validate_finite(value: float, field_name: str) -> float:
    """Validate that a float value is finite."""
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be a finite number")
    return value


class ClipSegmentBase(BaseModel):
    """Base schema for clip segments."""

    start_seconds: float = Field(description="Clip start position in seconds")
    end_seconds: float = Field(description="Clip end position in seconds")
    label: str | None = Field(default=None, max_length=255, description="Optional clip label")
    note: str | None = Field(default=None, max_length=1024, description="Optional clip note")
    order_index: int = Field(default=0, description="Sequential ordering index")


class ClipSegmentCreate(BaseModel):
    """Schema for creating a new clip segment."""

    start_seconds: float = Field(description="Clip start position in seconds")
    end_seconds: float = Field(description="Clip end position in seconds")
    label: str | None = Field(default=None, max_length=255, description="Optional clip label")
    note: str | None = Field(default=None, max_length=1024, description="Optional clip note")
    order_index: int | None = Field(
        default=None,
        description="Sequential ordering index (defaults to 0 or auto-assigned if omitted)",
    )

    @model_validator(mode="before")
    @classmethod
    def handle_order_alias(cls, data: Any) -> Any:
        """Allow 'order' as an alias for 'order_index'."""
        if isinstance(data, dict):
            if "order" in data and "order_index" not in data:
                data["order_index"] = data["order"]
        return data

    @field_validator("start_seconds")
    @classmethod
    def check_start_seconds(cls, v: float) -> float:
        """Ensure start_seconds is finite and non-negative."""
        return validate_finite_nonnegative(v, "start_seconds")

    @field_validator("end_seconds")
    @classmethod
    def check_end_seconds(cls, v: float) -> float:
        """Ensure end_seconds is finite."""
        return validate_finite(v, "end_seconds")

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        """Ensure end_seconds is strictly greater than start_seconds."""
        if self.end_seconds <= self.start_seconds:
            raise ValueError("end_seconds must be strictly greater than start_seconds")
        return self


class ClipSegmentUpdate(BaseModel):
    """Schema for updating an existing clip segment."""

    start_seconds: float | None = Field(
        default=None, description="Updated clip start position in seconds"
    )
    end_seconds: float | None = Field(
        default=None, description="Updated clip end position in seconds"
    )
    label: str | None = Field(default=None, max_length=255, description="Updated clip label")
    note: str | None = Field(default=None, max_length=1024, description="Updated clip note")
    order_index: int | None = Field(default=None, description="Updated sequential ordering index")

    @model_validator(mode="before")
    @classmethod
    def handle_order_alias(cls, data: Any) -> Any:
        """Allow 'order' as an alias for 'order_index'."""
        if isinstance(data, dict):
            if "order" in data and "order_index" not in data:
                data["order_index"] = data["order"]
        return data

    @field_validator("start_seconds")
    @classmethod
    def check_start_seconds(cls, v: float | None) -> float | None:
        """Ensure start_seconds is finite and non-negative if provided."""
        if v is not None:
            return validate_finite_nonnegative(v, "start_seconds")
        return v

    @field_validator("end_seconds")
    @classmethod
    def check_end_seconds(cls, v: float | None) -> float | None:
        """Ensure end_seconds is finite if provided."""
        if v is not None:
            return validate_finite(v, "end_seconds")
        return v

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        """Ensure end_seconds is strictly greater than start_seconds if both provided."""
        if (
            self.start_seconds is not None
            and self.end_seconds is not None
            and self.end_seconds <= self.start_seconds
        ):
            raise ValueError("end_seconds must be strictly greater than start_seconds")
        return self


class ClipSegmentRead(ClipSegmentBase):
    """Schema for returning clip segment details from API."""

    id: int
    video_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def order(self) -> int:
        """Alias for order_index in JSON responses."""
        return self.order_index
