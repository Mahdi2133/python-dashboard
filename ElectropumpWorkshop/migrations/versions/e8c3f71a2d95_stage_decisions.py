# -*- coding: utf-8 -*-
"""Decisions a stage may take besides sending the work on.

A reviewer such as امین بزرگمهر, reading مرکز آبرسانی's report, may decide the
well does not need pulling and stop the run there, or send it back asking for
a photo, a video or any other document first. Which of these a stage offers,
and who may use each, is data the admin sets in the process builder:

* workflow_stages.actions_json — the stage's stop/return actions and who may
  use each;
* workflow_stage_entries.needs_docs, docs_requested_at — a stage sent back for
  documents cannot be submitted again until something is uploaded after the
  request;
* workflow_instances.outcome_note, outcome_by — why, and by whom, a run was
  stopped.

Every column is added only when missing: the startup bootstrap may already
have added it.

Revision ID: e8c3f71a2d95
Revises: d5a19e3b7c42
"""
import sqlalchemy as sa
from alembic import op

revision = 'e8c3f71a2d95'
down_revision = 'd5a19e3b7c42'
branch_labels = None
depends_on = None

COLUMNS = [
    ("workflow_stages", lambda: sa.Column("actions_json", sa.Text(), nullable=True)),
    ("workflow_stage_entries", lambda: sa.Column(
        "needs_docs", sa.Boolean(), nullable=False, server_default=sa.false())),
    ("workflow_stage_entries", lambda: sa.Column(
        "docs_requested_at", sa.DateTime(), nullable=True)),
    ("workflow_instances", lambda: sa.Column("outcome_note", sa.Text(), nullable=True)),
    ("workflow_instances", lambda: sa.Column("outcome_by", sa.Integer(), nullable=True)),
]


def _has(table, column):
    return column in {c["name"] for c in
                      sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    # One column per batch: a single failed add must not take the others with it.
    for table, make in COLUMNS:
        column = make()
        if not _has(table, column.name):
            with op.batch_alter_table(table) as batch:
                batch.add_column(column)


def downgrade():
    for table, make in reversed(COLUMNS):
        name = make().name
        if _has(table, name):
            with op.batch_alter_table(table) as batch:
                batch.drop_column(name)
