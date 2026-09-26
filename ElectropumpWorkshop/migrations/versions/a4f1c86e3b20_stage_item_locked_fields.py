# -*- coding: utf-8 -*-
"""Which fields of a form a stage only shows, and which it fills.

A section dropped on a stage used to be either wholly editable or wholly
«فقط نمایش». Now the admin can lock single fields of it for that stage —
«تیپ پمپ قبلی» read off the well's history, visible to the workshop but not
theirs to change — and leave the rest to be filled.

Revision ID: a4f1c86e3b20
Revises: e8c3f71a2d95
"""
import sqlalchemy as sa
from alembic import op

revision = 'a4f1c86e3b20'
down_revision = 'e8c3f71a2d95'
branch_labels = None
depends_on = None


def _has(table, column):
    return column in {c["name"] for c in
                      sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    if not _has("workflow_stage_items", "locked_fields"):
        with op.batch_alter_table("workflow_stage_items") as batch:
            batch.add_column(sa.Column("locked_fields", sa.Text(), nullable=True))


def downgrade():
    if _has("workflow_stage_items", "locked_fields"):
        with op.batch_alter_table("workflow_stage_items") as batch:
            batch.drop_column("locked_fields")
