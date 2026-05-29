"""create_products_categories

Revision ID: 002
Revises: 72a3de1f5069
Create Date: 2026-05-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002_products_categories"
down_revision: Union[str, None] = "72a3de1f5069"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("categories.id"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False, index=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("image", sa.String(500), nullable=True),
        sa.Column("sort_order", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("categories.id"), nullable=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False, index=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "product_pricing",
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("products.id"), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("compare_at_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("cost_price", sa.Numeric(10, 2), nullable=True),
    )

    op.create_table(
        "product_inventory",
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("products.id"), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("sku", sa.String(100), nullable=True),
        sa.Column("barcode", sa.String(100), nullable=True),
        sa.Column("quantity", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("reserved_quantity", sa.Integer, server_default=sa.text("0"), nullable=False),
    )

    op.create_table(
        "product_variants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("products.id"), nullable=False, index=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("sku", sa.String(100), nullable=True),
        sa.Column("price_override", sa.Numeric(10, 2), nullable=True),
        sa.Column("quantity", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "media",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("entity_type", sa.String(50), nullable=False, index=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("alt", sa.String(255), nullable=True),
        sa.Column("sort_order", sa.Integer, server_default=sa.text("0"), nullable=False),
    )

    op.create_index("ix_products_tenant_slug", "products", ["tenant_id", "slug"])
    op.create_index("ix_categories_tenant_slug", "categories", ["tenant_id", "slug"])
    op.create_index("ix_media_entity", "media", ["entity_type", "entity_id"])


def downgrade() -> None:
    op.drop_table("media")
    op.drop_table("product_variants")
    op.drop_table("product_inventory")
    op.drop_table("product_pricing")
    op.drop_table("products")
    op.drop_table("categories")
