"""
Shared base for every DTO in the platform.

`PlatformBaseModel` centralizes the Pydantic v2 configuration every DTO
needs:
- `from_attributes=True`: lets a DTO be built directly from an ORM
  instance (`JobDTO.model_validate(job_orm_instance)`) for the Exporter
  layer, without a hand-written mapping function per model.
- `str_strip_whitespace=True`: every string field is trimmed on
  assignment — the Parser layer extracts raw text straight from HTML,
  which routinely carries leading/trailing whitespace and newlines.
- `use_enum_values=False` (default): DTOs keep real Python Enum members,
  not raw strings, so downstream code gets static-typing benefits and
  the Repository layer can pass them straight into SQLAlchemy `Enum`
  columns.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PlatformBaseModel(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )
