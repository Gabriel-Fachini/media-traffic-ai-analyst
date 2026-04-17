from __future__ import annotations

from dataclasses import dataclass
from typing import Final


DATASET_ID: Final = "bigquery-public-data.thelook_ecommerce"
CATALOG_SOURCE: Final = (
    "BigQuery INFORMATION_SCHEMA.COLUMNS export restricted to users, orders, and order_items."
)


@dataclass(frozen=True)
class SchemaColumn:
    name: str
    data_type: str
    is_nullable: bool


@dataclass(frozen=True)
class SchemaTable:
    name: str
    columns: tuple[SchemaColumn, ...]


@dataclass(frozen=True)
class SchemaRelationship:
    from_table: str
    from_column: str
    to_table: str
    to_column: str


@dataclass(frozen=True)
class SchemaCatalog:
    dataset: str
    source: str
    tables: tuple[SchemaTable, ...]
    relationships: tuple[SchemaRelationship, ...]

    def get_table(self, table_name: str) -> SchemaTable | None:
        for table in self.tables:
            if table.name == table_name:
                return table
        return None


SCHEMA_CATALOG: Final = SchemaCatalog(
    dataset=DATASET_ID,
    source=CATALOG_SOURCE,
    tables=(
        SchemaTable(
            name="users",
            columns=(
                SchemaColumn(name="id", data_type="INT64", is_nullable=True),
                SchemaColumn(name="first_name", data_type="STRING", is_nullable=True),
                SchemaColumn(name="last_name", data_type="STRING", is_nullable=True),
                SchemaColumn(name="email", data_type="STRING", is_nullable=True),
                SchemaColumn(name="age", data_type="INT64", is_nullable=True),
                SchemaColumn(name="gender", data_type="STRING", is_nullable=True),
                SchemaColumn(name="state", data_type="STRING", is_nullable=True),
                SchemaColumn(name="street_address", data_type="STRING", is_nullable=True),
                SchemaColumn(name="postal_code", data_type="STRING", is_nullable=True),
                SchemaColumn(name="city", data_type="STRING", is_nullable=True),
                SchemaColumn(name="country", data_type="STRING", is_nullable=True),
                SchemaColumn(name="latitude", data_type="FLOAT64", is_nullable=True),
                SchemaColumn(name="longitude", data_type="FLOAT64", is_nullable=True),
                SchemaColumn(name="traffic_source", data_type="STRING", is_nullable=True),
                SchemaColumn(name="created_at", data_type="TIMESTAMP", is_nullable=True),
                SchemaColumn(name="user_geom", data_type="GEOGRAPHY", is_nullable=True),
            ),
        ),
        SchemaTable(
            name="orders",
            columns=(
                SchemaColumn(name="order_id", data_type="INT64", is_nullable=True),
                SchemaColumn(name="user_id", data_type="INT64", is_nullable=True),
                SchemaColumn(name="status", data_type="STRING", is_nullable=True),
                SchemaColumn(name="gender", data_type="STRING", is_nullable=True),
                SchemaColumn(name="created_at", data_type="TIMESTAMP", is_nullable=True),
                SchemaColumn(name="returned_at", data_type="TIMESTAMP", is_nullable=True),
                SchemaColumn(name="shipped_at", data_type="TIMESTAMP", is_nullable=True),
                SchemaColumn(name="delivered_at", data_type="TIMESTAMP", is_nullable=True),
                SchemaColumn(name="num_of_item", data_type="INT64", is_nullable=True),
            ),
        ),
        SchemaTable(
            name="order_items",
            columns=(
                SchemaColumn(name="id", data_type="INT64", is_nullable=True),
                SchemaColumn(name="order_id", data_type="INT64", is_nullable=True),
                SchemaColumn(name="user_id", data_type="INT64", is_nullable=True),
                SchemaColumn(name="product_id", data_type="INT64", is_nullable=True),
                SchemaColumn(
                    name="inventory_item_id",
                    data_type="INT64",
                    is_nullable=True,
                ),
                SchemaColumn(name="status", data_type="STRING", is_nullable=True),
                SchemaColumn(name="created_at", data_type="TIMESTAMP", is_nullable=True),
                SchemaColumn(name="shipped_at", data_type="TIMESTAMP", is_nullable=True),
                SchemaColumn(name="delivered_at", data_type="TIMESTAMP", is_nullable=True),
                SchemaColumn(name="returned_at", data_type="TIMESTAMP", is_nullable=True),
                SchemaColumn(name="sale_price", data_type="FLOAT64", is_nullable=True),
            ),
        ),
    ),
    relationships=(
        SchemaRelationship(
            from_table="users",
            from_column="id",
            to_table="orders",
            to_column="user_id",
        ),
        SchemaRelationship(
            from_table="orders",
            from_column="order_id",
            to_table="order_items",
            to_column="order_id",
        ),
        SchemaRelationship(
            from_table="users",
            from_column="id",
            to_table="order_items",
            to_column="user_id",
        ),
    ),
)


__all__ = [
    "CATALOG_SOURCE",
    "DATASET_ID",
    "SCHEMA_CATALOG",
    "SchemaCatalog",
    "SchemaColumn",
    "SchemaRelationship",
    "SchemaTable",
]
