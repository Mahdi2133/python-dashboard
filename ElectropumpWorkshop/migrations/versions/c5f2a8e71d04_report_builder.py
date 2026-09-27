# -*- coding: utf-8 -*-
"""Reports as entities: versions, access, snapshots, schedules, groups; stage SLA.

The report builder keeps definitions only — never a copy of the workshop's
data. A stage may carry an expected duration (SLA hours) so delay can be
reported on.

Revision ID: c5f2a8e71d04
Revises: b9d2e47c1a86
"""
import sqlalchemy as sa
from alembic import op

revision = 'c5f2a8e71d04'
down_revision = 'b9d2e47c1a86'
branch_labels = None
depends_on = None


def _tables():
    return set(sa.inspect(op.get_bind()).get_table_names())


def _has(table, column):
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    have = _tables()
    if not _has("workflow_stages", "sla_hours"):
        with op.batch_alter_table("workflow_stages") as batch:
            batch.add_column(sa.Column("sla_hours", sa.Float(), nullable=True))
    if "report_categories" not in have:
        op.create_table(
            "report_categories",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(120), nullable=False, unique=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"))
    if "reports" not in have:
        op.create_table(
            "reports",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("description", sa.Text()),
            sa.Column("category_id", sa.Integer(),
                      sa.ForeignKey("report_categories.id", ondelete="SET NULL"), index=True),
            sa.Column("status", sa.String(12), nullable=False, server_default="draft", index=True),
            sa.Column("published_version_id", sa.Integer()),
            sa.Column("scope_to_centers", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("template_key", sa.String(60)),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("app_users.id")),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("published_at", sa.DateTime()))
    if "report_versions" not in have:
        op.create_table(
            "report_versions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("report_id", sa.Integer(), sa.ForeignKey("reports.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("number", sa.Integer(), nullable=False),
            sa.Column("definition_json", sa.Text(), nullable=False),
            sa.Column("note", sa.String(300)),
            sa.Column("frozen", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("app_users.id")),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("report_id", "number", name="uq_report_version"))
    if "report_dependencies" not in have:
        op.create_table(
            "report_dependencies",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("version_id", sa.Integer(),
                      sa.ForeignKey("report_versions.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("kind", sa.String(20), nullable=False, index=True),
            sa.Column("ref", sa.String(160), nullable=False, index=True))
    if "report_permissions" not in have:
        op.create_table(
            "report_permissions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("report_id", sa.Integer(), sa.ForeignKey("reports.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("principal_kind", sa.String(10), nullable=False),
            sa.Column("principal", sa.String(80), nullable=False),
            sa.Column("access_json", sa.Text(), nullable=False))
    if "report_favorites" not in have:
        op.create_table(
            "report_favorites",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("report_id", sa.Integer(), sa.ForeignKey("reports.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("app_users.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.UniqueConstraint("report_id", "user_id", name="uq_report_fav"))
    if "report_snapshots" not in have:
        op.create_table(
            "report_snapshots",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("report_id", sa.Integer(), sa.ForeignKey("reports.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("version_id", sa.Integer(),
                      sa.ForeignKey("report_versions.id", ondelete="SET NULL")),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("filters_json", sa.Text()),
            sa.Column("result_json", sa.Text(), nullable=False),
            sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("app_users.id")),
            sa.Column("created_at", sa.DateTime(), nullable=False, index=True),
            sa.Column("source", sa.String(20), nullable=False, server_default="manual"))
    if "report_schedules" not in have:
        op.create_table(
            "report_schedules",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("report_id", sa.Integer(), sa.ForeignKey("reports.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("frequency", sa.String(12), nullable=False),
            sa.Column("hour", sa.Integer(), nullable=False, server_default="7"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("recipients_json", sa.Text()),
            sa.Column("next_run_at", sa.DateTime(), index=True),
            sa.Column("last_run_at", sa.DateTime()),
            sa.Column("last_status", sa.String(200)),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("app_users.id")),
            sa.Column("created_at", sa.DateTime(), nullable=False))
    if "report_export_jobs" not in have:
        op.create_table(
            "report_export_jobs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("report_id", sa.Integer(), sa.ForeignKey("reports.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("app_users.id"), index=True),
            sa.Column("fmt", sa.String(8), nullable=False),
            sa.Column("status", sa.String(12), nullable=False, server_default="queued"),
            sa.Column("message", sa.Text()),
            sa.Column("file_name", sa.String(200)),
            sa.Column("stored_name", sa.String(120)),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("finished_at", sa.DateTime()))
    if "user_groups" not in have:
        op.create_table(
            "user_groups",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(120), nullable=False, unique=True),
            sa.Column("description", sa.String(300)),
            sa.Column("created_at", sa.DateTime(), nullable=False))
    if "user_group_members" not in have:
        op.create_table(
            "user_group_members",
            sa.Column("group_id", sa.Integer(), sa.ForeignKey("user_groups.id", ondelete="CASCADE"),
                      primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("app_users.id", ondelete="CASCADE"),
                      primary_key=True))


def downgrade():
    have = _tables()
    for t in ("user_group_members", "user_groups", "report_export_jobs", "report_schedules",
              "report_snapshots", "report_favorites", "report_permissions",
              "report_dependencies", "report_versions", "reports", "report_categories"):
        if t in have:
            op.drop_table(t)
    if _has("workflow_stages", "sla_hours"):
        with op.batch_alter_table("workflow_stages") as batch:
            batch.drop_column("sla_hours")
