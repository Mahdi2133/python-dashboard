# -*- coding: utf-8 -*-
"""Which operation a process is for.

Several processes can now run at once, one per operation: «فرایند کشیدن»
opens at مرکز آبرسانی, «فرایند نصب» at کارگاه نصب, each with its own stages.
Empty means both, as the single process of older installs was.

Revision ID: b9d2e47c1a86
Revises: a4f1c86e3b20
"""
import sqlalchemy as sa
from alembic import op

revision = 'b9d2e47c1a86'
down_revision = 'a4f1c86e3b20'
branch_labels = None
depends_on = None


def _has(table, column):
    return column in {c["name"] for c in
                      sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    if not _has("workflow_definitions", "operation_kind"):
        with op.batch_alter_table("workflow_definitions") as batch:
            batch.add_column(sa.Column("operation_kind", sa.String(length=10),
                                       nullable=True))


def downgrade():
    if _has("workflow_definitions", "operation_kind"):
        with op.batch_alter_table("workflow_definitions") as batch:
            batch.drop_column("operation_kind")
