"""the process map: nodes, arrows, principals, events and versioning

Turns the six fixed stages into a graph the admin draws. Every stage row
becomes a node (``node_key``, ``node_type``, a position and a size), stages
gain as many owners and approvers as the process needs, and the arrows between
them — with their conditions — become rows of their own. A template now carries
a version, and a run carries a snapshot of the map it started on, so redrawing
the process leaves running instances alone.

Nothing is dropped: ``stage_number`` stays as the display order the کارتابل,
exports and attachments already read, and ``assignee_id`` stays as the
single-owner column the first process builder wrote.

Revision ID: d4a91b6c27e0
Revises: c3e18a7f45b2
Create Date: 2026-09-16 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd4a91b6c27e0'
down_revision = 'c3e18a7f45b2'
branch_labels = None
depends_on = None


def upgrade():
    _foreign_keys(False)

    # ── templates: versioned, with a status and a canvas ────────────────────
    # A code may now exist at several versions, so the UNIQUE on `code` alone
    # has to go. SQLite wrote it without a name; a naming convention gives the
    # rebuild something to refer to it by.
    with op.batch_alter_table('workflow_definitions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('version', sa.Integer(), nullable=False,
                                      server_default='1'))
        batch_op.add_column(sa.Column('status', sa.String(length=16),
                                      nullable=False,
                                      server_default='published'))
        batch_op.add_column(sa.Column('canvas_json', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('config_json', sa.Text(), nullable=True))
    # Dropping the constraint is its own rebuild: alembic cannot reorder new
    # columns and drop a constraint in the same batch.
    naming = {"uq": "uq_%(table_name)s_%(column_0_name)s"}
    if _has_unnamed_unique('workflow_definitions', ['code']):
        with op.batch_alter_table('workflow_definitions', schema=None,
                                  naming_convention=naming) as batch_op:
            batch_op.drop_constraint('uq_workflow_definitions_code',
                                     type_='unique')
    with op.batch_alter_table('workflow_definitions', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_workflow_code_version',
                                          ['code', 'version'])
        batch_op.create_index(batch_op.f('ix_workflow_definitions_status'),
                              ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_workflow_definitions_code'),
                              ['code'], unique=False)

    # ── stages become nodes ─────────────────────────────────────────────────
    with op.batch_alter_table('workflow_stages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('node_key', sa.String(length=60),
                                      nullable=True))
        batch_op.add_column(sa.Column('node_type', sa.String(length=16),
                                      nullable=False, server_default='phase'))
        batch_op.add_column(sa.Column('icon', sa.String(length=16),
                                      nullable=True))
        batch_op.add_column(sa.Column('pos_x', sa.Float(), nullable=False,
                                      server_default='0'))
        batch_op.add_column(sa.Column('pos_y', sa.Float(), nullable=False,
                                      server_default='0'))
        batch_op.add_column(sa.Column('width', sa.Float(), nullable=False,
                                      server_default='210'))
        batch_op.add_column(sa.Column('height', sa.Float(), nullable=False,
                                      server_default='90'))
        batch_op.add_column(sa.Column('config_json', sa.Text(), nullable=True))
        batch_op.create_index(batch_op.f('ix_workflow_stages_node_key'),
                              ['node_key'], unique=False)
        batch_op.create_index(batch_op.f('ix_workflow_stages_node_type'),
                              ['node_type'], unique=False)

    # Give the stages that already exist a key and a place on the canvas, in
    # the order they were numbered. The seed rewrites the rest.
    op.execute("UPDATE workflow_stages SET node_key = 's' || stage_number "
               "WHERE node_key IS NULL")
    op.execute("UPDATE workflow_stages SET pos_x = 80 + (stage_number % 3) * 300, "
               "pos_y = 60 + (stage_number / 3) * 190")
    op.execute("UPDATE workflow_stages SET node_type = 'start' "
               "WHERE stage_number = 0")

    with op.batch_alter_table('workflow_stage_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_read_only', sa.Boolean(),
                                      nullable=False,
                                      server_default=sa.text('0')))

    # ── who a node belongs to ───────────────────────────────────────────────
    op.create_table(
        'workflow_node_principals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('node_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=16), nullable=False),
        sa.Column('principal_kind', sa.String(length=16), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('role_code', sa.String(length=40), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['node_id'], ['workflow_stages.id'],
                                name='fk_wf_principal_node',
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['app_users.id'],
                                name='fk_wf_principal_user',
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('workflow_node_principals', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_workflow_node_principals_node_id'),
                              ['node_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_workflow_node_principals_role'),
                              ['role'], unique=False)
        batch_op.create_index(batch_op.f('ix_workflow_node_principals_user_id'),
                              ['user_id'], unique=False)
    # The owner each stage already had becomes its first principal.
    op.execute("INSERT INTO workflow_node_principals "
               "(node_id, role, principal_kind, user_id, sort_order) "
               "SELECT id, 'assignee', 'user', assignee_id, 0 "
               "FROM workflow_stages WHERE assignee_id IS NOT NULL")

    # ── arrows ──────────────────────────────────────────────────────────────
    op.create_table(
        'workflow_edges',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workflow_id', sa.Integer(), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('target_id', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=160), nullable=True),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('condition_json', sa.Text(), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['workflow_id'], ['workflow_definitions.id'],
                                name='fk_wf_edge_workflow', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_id'], ['workflow_stages.id'],
                                name='fk_wf_edge_source', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['target_id'], ['workflow_stages.id'],
                                name='fk_wf_edge_target', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('workflow_edges', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_workflow_edges_workflow_id'),
                              ['workflow_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_workflow_edges_source_id'),
                              ['source_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_workflow_edges_target_id'),
                              ['target_id'], unique=False)

    # ── runs: a snapshot, a position on the map, a version ──────────────────
    with op.batch_alter_table('workflow_instances', schema=None) as batch_op:
        batch_op.add_column(sa.Column('template_version', sa.Integer(),
                                      nullable=False, server_default='1'))
        batch_op.add_column(sa.Column('graph_json', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('current_node', sa.String(length=60),
                                      nullable=True))
        batch_op.create_index(batch_op.f('ix_workflow_instances_current_node'),
                              ['current_node'], unique=False)
    op.execute("UPDATE workflow_instances SET status = 'running' "
               "WHERE status = 'open'")

    # ── entries become tasks ────────────────────────────────────────────────
    with op.batch_alter_table('workflow_stage_entries', schema=None) as batch_op:
        batch_op.add_column(sa.Column('node_key', sa.String(length=60),
                                      nullable=True))
        batch_op.add_column(sa.Column('task_kind', sa.String(length=12),
                                      nullable=False, server_default='fill'))
        batch_op.add_column(sa.Column('assignee_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('comment', sa.Text(), nullable=True))
        batch_op.create_index(batch_op.f('ix_workflow_stage_entries_node_key'),
                              ['node_key'], unique=False)
        batch_op.create_index(batch_op.f('ix_workflow_stage_entries_task_kind'),
                              ['task_kind'], unique=False)
        batch_op.create_index(batch_op.f('ix_workflow_stage_entries_assignee_id'),
                              ['assignee_id'], unique=False)
        batch_op.create_foreign_key('fk_wf_entry_assignee', 'app_users',
                                    ['assignee_id'], ['id'])
    op.execute("UPDATE workflow_stage_entries SET node_key = "
               "(SELECT node_key FROM workflow_stages "
               " WHERE workflow_stages.id = workflow_stage_entries.stage_id) "
               "WHERE node_key IS NULL AND stage_id IS NOT NULL")
    op.execute("UPDATE workflow_stage_entries SET node_key = 's' || stage_number "
               "WHERE node_key IS NULL")

    with op.batch_alter_table('workflow_attachments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('node_key', sa.String(length=60),
                                      nullable=True))

    # ── the audit trail ─────────────────────────────────────────────────────
    op.create_table(
        'workflow_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('instance_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(length=40), nullable=False),
        sa.Column('from_node', sa.String(length=60), nullable=True),
        sa.Column('to_node', sa.String(length=60), nullable=True),
        sa.Column('status', sa.String(length=24), nullable=True),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('payload_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['instance_id'], ['workflow_instances.id'],
                                name='fk_wf_event_instance', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['app_users.id'],
                                name='fk_wf_event_user'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('workflow_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_workflow_events_instance_id'),
                              ['instance_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_workflow_events_created_at'),
                              ['created_at'], unique=False)

    _foreign_keys(True)


def _foreign_keys(on: bool):
    """Let SQLite rebuild a table that other tables point at.

    ``workflow_definitions`` has children, and a batch rebuild drops the old
    copy before renaming the new one into its place — which trips the foreign
    keys the app turns on. They go off for the length of this migration and
    straight back on at the end; the ids never change, so nothing is orphaned
    in between.
    """
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        bind.exec_driver_sql(f"PRAGMA foreign_keys={'ON' if on else 'OFF'}")


def _has_unnamed_unique(table, columns) -> bool:
    """Whether the old single-column UNIQUE is still on the table."""
    inspector = sa.inspect(op.get_bind())
    return any(list(c.get('column_names') or []) == list(columns)
               for c in inspector.get_unique_constraints(table))


def downgrade():
    op.drop_table('workflow_events')
    with op.batch_alter_table('workflow_attachments', schema=None) as batch_op:
        batch_op.drop_column('node_key')
    with op.batch_alter_table('workflow_stage_entries', schema=None) as batch_op:
        batch_op.drop_constraint('fk_wf_entry_assignee', type_='foreignkey')
        batch_op.drop_column('comment')
        batch_op.drop_column('assignee_id')
        batch_op.drop_column('task_kind')
        batch_op.drop_column('node_key')
    with op.batch_alter_table('workflow_instances', schema=None) as batch_op:
        batch_op.drop_column('current_node')
        batch_op.drop_column('graph_json')
        batch_op.drop_column('template_version')
    op.drop_table('workflow_edges')
    op.drop_table('workflow_node_principals')
    with op.batch_alter_table('workflow_stage_items', schema=None) as batch_op:
        batch_op.drop_column('is_read_only')
    with op.batch_alter_table('workflow_stages', schema=None) as batch_op:
        batch_op.drop_column('config_json')
        batch_op.drop_column('height')
        batch_op.drop_column('width')
        batch_op.drop_column('pos_y')
        batch_op.drop_column('pos_x')
        batch_op.drop_column('icon')
        batch_op.drop_column('node_type')
        batch_op.drop_column('node_key')
    with op.batch_alter_table('workflow_definitions', schema=None) as batch_op:
        batch_op.drop_constraint('uq_workflow_code_version', type_='unique')
        batch_op.drop_column('config_json')
        batch_op.drop_column('canvas_json')
        batch_op.drop_column('status')
        batch_op.drop_column('version')
        batch_op.create_unique_constraint('uq_workflow_code', ['code'])
