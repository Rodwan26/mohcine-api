"""phase2_architecture_upgrade

Adds audit columns, optimistic locking, public IDs, composite indexes,
inventory_transactions table, and event_outbox table.

Revision ID: 003
Revises: 002_products_categories
Create Date: 2026-05-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "003_phase2_architecture_upgrade"
down_revision: Union[str, None] = "002_products_categories"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Audit columns on existing tables ---
    for table in ("products", "categories", "product_variants", "users", "product_pricing", "product_inventory", "media"):
        op.add_column(table, sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True, index=True))
        op.add_column(table, sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True))
        op.add_column(table, sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True))

    # --- Optimistic locking version_id ---
    for table in ("products", "categories", "product_variants", "users"):
        op.add_column(table, sa.Column("version_id", sa.Integer, nullable=False, server_default=sa.text("1")))

    # --- Public IDs ---
    for table, col_name in (("products", "public_id"), ("categories", "public_id"),
                            ("product_variants", "public_id"), ("users", "public_id")):
        op.add_column(table, sa.Column(col_name, sa.String(50), nullable=True, unique=True))

    # --- Composite indexes ---
    op.create_index("ix_products_tenant_created", "products", ["tenant_id", sa.text("created_at DESC")])
    op.create_index("ix_products_tenant_category", "products", ["tenant_id", "category_id"])
    op.create_index("ix_products_tenant_active", "products", ["tenant_id", "is_active"])
    op.create_index("ix_categories_tenant_created", "categories", ["tenant_id", sa.text("created_at DESC")])
    op.create_index("ix_users_tenant_active", "users", ["tenant_id", "is_active"])
    op.create_index("ix_product_variants_tenant_product", "product_variants", ["tenant_id", "product_id"])

    # --- event_outbox table ---
    op.create_table(
        "event_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("event_name", sa.String(255), nullable=False, index=True),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default=sa.text("'pending'"), index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --- inventory_transactions table ---
    op.create_table(
        "inventory_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("products.id"), nullable=False, index=True),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("product_variants.id"), nullable=True, index=True),
        sa.Column("type", sa.String(50), nullable=False, index=True),
        sa.Column("quantity_change", sa.Integer, nullable=False),
        sa.Column("running_balance", sa.Integer, nullable=False),
        sa.Column("reference", sa.String(255), nullable=True),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("inventory_transactions")
    op.drop_table("event_outbox")

    op.drop_index("ix_product_variants_tenant_product", table_name="product_variants")
    op.drop_index("ix_users_tenant_active", table_name="users")
    op.drop_index("ix_categories_tenant_created", table_name="categories")
    op.drop_index("ix_products_tenant_active", table_name="products")
    op.drop_index("ix_products_tenant_category", table_name="products")
    op.drop_index("ix_products_tenant_created", table_name="products")

    for table in ("products", "categories", "product_variants", "users"):
        op.drop_column(table, "public_id")
        op.drop_column(table, "version_id")

    for table in ("products", "categories", "product_variants", "users", "product_pricing", "product_inventory", "media"):
        op.drop_column(table, "deleted_by")
        op.drop_column(table, "updated_by")
        op.drop_column(table, "created_by")
