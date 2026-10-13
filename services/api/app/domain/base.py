"""Strict immutable input/output contracts shared by domain slices."""

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, frozen=True, allow_inf_nan=False
    )
