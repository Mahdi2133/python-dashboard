# -*- coding: utf-8 -*-
"""A blocking approval, a scope for what the approver reads, and section rules.

Three things the workshop asked for:

* «تا زمانی که ایکس تأیید نکند نمی‌توان ادامه داد» — per stage, the admin's
  choice, so the stage carries the flag rather than the engine carrying a rule;
* the sender saying which recorded stages the approver may read, stored on the
  referral itself because it is a decision about that one hand-off;
* a visibility rule on a whole form section, which is what lets one علت خرابی
  bring its own block of readings with it.

Revision ID: b3d81f5ac902
Revises: f1a9d6c02b74
"""
import sqlalchemy as sa
from alembic import op

revision = 'b3d81f5ac902'
down_revision = 'f1a9d6c02b74'
branch_labels = None
depends_on = None

# One column per batch: SQLite rebuilds the table for each, and alembic cannot
# order two additions inside a single rebuild.
_ADD = [
    ("workflow_stages", "approval_blocks",
     lambda: sa.Column("approval_blocks", sa.Boolean(), nullable=False,
                       server_default=sa.false())),
    ("workflow_stages", "approval_sees",
     lambda: sa.Column("approval_sees", sa.String(length=10), nullable=False,
                       server_default="all")),
    ("workflow_stage_entries", "shared_stages",
     lambda: sa.Column("shared_stages", sa.String(length=120), nullable=True)),
    ("form_sections", "visible_when",
     lambda: sa.Column("visible_when", sa.String(length=120), nullable=True)),
]


def _has(table, column):
    bind = op.get_bind()
    return column in {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade():
    # The app heals its own schema on startup, so on a machine that already
    # opened this version the columns may be here. Add only what is missing.
    for table, column, make in _ADD:
        if not _has(table, column):
            with op.batch_alter_table(table) as batch:
                batch.add_column(make())


def downgrade():
    for table, column, _ in reversed(_ADD):
        if _has(table, column):
            with op.batch_alter_table(table) as batch:
                batch.drop_column(column)
