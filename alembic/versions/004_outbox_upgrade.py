"""outbox_upgrade

Adds retry_count, last_error, next_retry_at to event_outbox.
Adds idempotency_key to inventory_transactions.

Revision ID: 004
Revises: 003_phase2_architecture_upgrade
Create Date: 2026-05-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004_outbox_upgrade"
down_revision: Union[str, None] = "003_phase2_architecture_upgrade"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("event_outbox", sa.Column("retry_count", sa.Integer, nullable=False, server_default=sa.text("0")))
    op.add_column("event_outbox", sa.Column("last_error", sa.Text, nullable=True))
    op.add_column("event_outbox", sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("inventory_transactions", sa.Column("idempotency_key", sa.String(255), nullable=True, unique=True))


def downgrade() -> None:
    op.drop_column("inventory_transactions", "idempotency_key")
    op.drop_column("event_outbox", "next_retry_at")
    op.drop_column("event_outbox", "last_error")
    op.drop_column("event_outbox", "retry_count")
