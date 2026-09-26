# -*- coding: utf-8 -*-
"""Where a field's suggested value comes from on the well's last operation.

The «…قبلی» fields used to be filled from a fixed list in the engine and picked
out in the browser by their names, so a field that did not match either — or
that appeared on the page after the fill had already run — stayed empty. Now
each field says it itself, and the admin sets it in the form builder.

Revision ID: d5a19e3b7c42
Revises: c7e24a9d1f60
"""
import sqlalchemy as sa
from alembic import op

revision = 'd5a19e3b7c42'
down_revision = 'c7e24a9d1f60'
branch_labels = None
depends_on = None


def _has(table, column):
    return column in {c["name"] for c in
                      sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    if not _has("form_fields", "prefill_from"):
        with op.batch_alter_table("form_fields") as batch:
            batch.add_column(sa.Column("prefill_from", sa.String(length=80),
                                       nullable=True))


def downgrade():
    if _has("form_fields", "prefill_from"):
        with op.batch_alter_table("form_fields") as batch:
            batch.drop_column("prefill_from")
