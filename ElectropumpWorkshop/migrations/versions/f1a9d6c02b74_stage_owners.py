# -*- coding: utf-8 -*-
"""A stage's متولی becomes a list, and each operation gets its own door.

Two things the workshop asked for:

* eight مراکز آبرسانی, each with its own user, sharing one stage — so the
  owner of a stage is a list, and a stage may ask to be routed to the owner
  whose مرکز is the well's;
* «کشیدن از مرکز آبرسانی، نصب از کارگاه نصب» said as data rather than as a
  rule in the engine — ``can_start`` on a stage, with ``applies_to`` deciding
  which operation that door admits.

Revision ID: f1a9d6c02b74
Revises: e7c4a2b91d38
"""
import sqlalchemy as sa
from alembic import op

revision = 'f1a9d6c02b74'
down_revision = 'e7c4a2b91d38'
branch_labels = None
depends_on = None


def _has_column(name):
    bind = op.get_bind()
    return name in {c["name"] for c in
                    sa.inspect(bind).get_columns("workflow_stages")}


def _has_table(name):
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade():
    # The app heals its own schema on startup, so by the time this runs on a
    # machine that has already opened the new version, the columns and tables
    # may be there already. Add only what is missing; the data steps below are
    # written to be safe to repeat either way.
    if not _has_column("can_start"):
        with op.batch_alter_table("workflow_stages") as batch:
            batch.add_column(sa.Column("can_start", sa.Boolean(),
                                       nullable=False,
                                       server_default=sa.false()))
    if not _has_column("route_by_center"):
        with op.batch_alter_table("workflow_stages") as batch:
            batch.add_column(sa.Column("route_by_center", sa.Boolean(),
                                       nullable=False,
                                       server_default=sa.false()))

    if not _has_table("workflow_stage_owners"):
        op.create_table(
            "workflow_stage_owners",
            sa.Column("stage_id", sa.Integer(),
                      sa.ForeignKey("workflow_stages.id", ondelete="CASCADE"),
                      primary_key=True),
            sa.Column("user_id", sa.Integer(),
                      sa.ForeignKey("app_users.id", ondelete="CASCADE"),
                      primary_key=True),
        )
    if not _has_table("app_user_centers"):
        op.create_table(
            "app_user_centers",
            sa.Column("user_id", sa.Integer(),
                      sa.ForeignKey("app_users.id", ondelete="CASCADE"),
                      primary_key=True),
            sa.Column("center_id", sa.Integer(),
                      sa.ForeignKey("lookup_items.id", ondelete="CASCADE"),
                      primary_key=True),
        )

    # Every stage that already had a متولی keeps it as the first of its list,
    # so nothing is ownerless the moment this runs.
    op.execute("""
        INSERT INTO workflow_stage_owners (stage_id, user_id)
        SELECT s.id, s.assignee_id FROM workflow_stages s
        WHERE s.assignee_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM workflow_stage_owners o
                          WHERE o.stage_id = s.id AND o.user_id = s.assignee_id)
    """)
    # The doors the engine used to hard-code: کشیدن at stage 1, نصب at stage 3.
    # A stage bound to the other branch is not that branch's door. Processes
    # where somebody has already marked a door are left alone.
    op.execute("""
        UPDATE workflow_stages SET can_start = 1
        WHERE is_active = 1
          AND ((stage_number = 1 AND applies_to <> 'install')
            OR (stage_number = 3 AND applies_to <> 'pull'))
          AND workflow_id NOT IN (SELECT workflow_id FROM workflow_stages
                                  WHERE can_start = 1)
    """)


def downgrade():
    op.drop_table('app_user_centers')
    op.drop_table('workflow_stage_owners')
    with op.batch_alter_table('workflow_stages') as batch:
        batch.drop_column('route_by_center')
    with op.batch_alter_table('workflow_stages') as batch:
        batch.drop_column('can_start')
