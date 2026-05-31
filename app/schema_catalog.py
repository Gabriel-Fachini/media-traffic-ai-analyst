"""Backward-compat shim — real implementation moved to app/core/schema_catalog.py."""

from app.core.schema_catalog import (
    CATALOG_SOURCE,
    DATASET_ID,
    SCHEMA_CATALOG,
    SchemaColumn,
    SchemaRelationship,
    SchemaCatalog,
    SchemaTable,
)

__all__ = [
    "CATALOG_SOURCE",
    "DATASET_ID",
    "SCHEMA_CATALOG",
    "SchemaColumn",
    "SchemaRelationship",
    "SchemaCatalog",
    "SchemaTable",
]
