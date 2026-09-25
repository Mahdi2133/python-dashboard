# -*- coding: utf-8 -*-
"""Start doors per operation, and referrals to several people at once.

* ``workflow_stages.start_kind`` — which operation a door opens, separate from
  «شامل»: کارگاه مکانیک is passed through by both operations but only a نصب
  starts there.
* ``workflow_instances.entry_stage`` — the door this run was opened at, so a
  نصب started at stage 3 keeps its path even when stage 1 admits both.
* ``referral_user_ids`` / ``refer_all`` on a stage and ``referred_to_ids`` /
  ``refer_all`` / ``done_by_ids`` on an entry — «ارجاع به دفتر فنی و بهره‌بردار»
  sends one piece of work to two کارتابل, and the stage says whether one of
  them is enough or both must record.

Revision ID: c7e24a9d1f60
Revises: b3d81f5ac902
"""
import sqlalchemy as sa
from alembic import op

revision = 'c7e24a9d1f60'
down_revision = 'b3d81f5ac902'
branch_labels = None
depends_on = None

_ADD = [
    ("workflow_stages", "start_kind",
     lambda: sa.Column("start_kind", sa.String(length=10), nullable=True)),
    ("workflow_stages", "referral_user_ids",
     lambda: sa.Column("referral_user_ids", sa.String(length=200), nullable=True)),
    ("workflow_stages", "refer_all",
     lambda: sa.Column("refer_all", sa.Boolean(), nullable=False,
                       server_default=sa.false())),
    ("workflow_instances", "entry_stage",
     lambda: sa.Column("entry_stage", sa.Integer(), nullable=True)),
    ("workflow_stage_entries", "referred_to_ids",
     lambda: sa.Column("referred_to_ids", sa.String(length=200), nullable=True)),
    ("workflow_stage_entries", "refer_all",
     lambda: sa.Column("refer_all", sa.Boolean(), nullable=False,
                       server_default=sa.false())),
    ("workflow_stage_entries", "done_by_ids",
     lambda: sa.Column("done_by_ids", sa.String(length=200), nullable=True)),
]


def _has(table, column):
    return column in {c["name"] for c in
                      sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    # The app heals its own schema on startup; add only what is missing, one
    # column per batch because SQLite rebuilds the table for each.
    for table, column, make in _ADD:
        if not _has(table, column):
            with op.batch_alter_table(table) as batch:
                batch.add_column(make())


def downgrade():
    for table, column, _ in reversed(_ADD):
        if _has(table, column):
            with op.batch_alter_table(table) as batch:
                batch.drop_column(column)
