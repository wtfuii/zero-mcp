"""Conversion of the library's Pydantic models into MCP-friendly JSON values.

Responses keep the client's snake_case field names (the names documented by
``finanzen-zero-api``) and use JSON mode, so ``Decimal`` amounts become strings
that preserve their precision and datetimes become ISO 8601 strings. MCP tool
results are then plain ``dict``/``list`` values, which the SDK exposes both as
structured content and as JSON text.
"""

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel


def dump(model: BaseModel) -> dict[str, Any]:
    """Return one model as a JSON-safe dict with snake_case keys."""
    return model.model_dump(mode="json")


def dump_many(models: Iterable[BaseModel]) -> list[dict[str, Any]]:
    """Return a sequence of models as JSON-safe dicts."""
    return [dump(model) for model in models]
