"""process (فرایند) layer

Stage definitions, running instances, per-stage entries and attachments, plus
the two columns the rules needed: a locked flag on lookup options and a
process-relevant name on wells is unchanged.

Revision ID: c3e18a7f45b2
Revises: b7f2d9c31a05
Create Date: 2026-09-15 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3e18a7f45b2'
down_revision = 'b7f2d9c31a05'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'workflow_definitions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=60), nullable=False),
        sa.Column('name', sa.String(length=160), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    )
    with op.batch_alter_table('workflow_definitions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_workflow_definitions_is_active'),
                              ['is_active'], unique=False)

    op.create_table(
        'workflow_stages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workflow_id', sa.Integer(), nullable=False),
        sa.Column('stage_number', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('assignee_id', sa.Integer(), nullable=True),
        sa.Column('applies_to', sa.String(length=10), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['workflow_id'], ['workflow_definitions.id'],
                                name='fk_workflow_stages_workflow_id',
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['assignee_id'], ['app_users.id'],
                                name='fk_workflow_stages_assignee_id',
                                ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workflow_id', 'stage_number',
                            name='uq_workflow_stage_number'),
    )
    with op.batch_alter_table('workflow_stages', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_workflow_stages_workflow_id'),
                              ['workflow_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_workflow_stages_assignee_id'),
                              ['assignee_id'], unique=False)

    op.create_table(
        'workflow_stage_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('stage_id', sa.Integer(), nullable=False),
        sa.Column('section_id', sa.Integer(), nullable=True),
        sa.Column('field_id', sa.Integer(), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.Column('applies_to', sa.String(length=10), nullable=False),
        sa.Column('is_optional', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['stage_id'], ['workflow_stages.id'],
                                name='fk_workflow_stage_items_stage_id',
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['section_id'], ['form_sections.id'],
                                name='fk_workflow_stage_items_section_id',
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['field_id'], ['form_fields.id'],
                                name='fk_workflow_stage_items_field_id',
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('workflow_stage_items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_workflow_stage_items_stage_id'),
                              ['stage_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_workflow_stage_items_section_id'),
                              ['section_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_workflow_stage_items_field_id'),
                              ['field_id'], unique=False)

    op.create_table(
        'workflow_instances',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workflow_id', sa.Integer(), nullable=False),
        sa.Column('operation_kind', sa.String(length=10), nullable=True),
        sa.Column('well_id', sa.Integer(), nullable=True),
        sa.Column('well_name_raw', sa.String(length=200), nullable=True),
        sa.Column('current_stage', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('payload_json', sa.Text(), nullable=True),
        sa.Column('record_id', sa.Integer(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['workflow_id'], ['workflow_definitions.id'],
                                name='fk_workflow_instances_workflow_id'),
        sa.ForeignKeyConstraint(['well_id'], ['wells.id'],
                                name='fk_workflow_instances_well_id'),
        sa.ForeignKeyConstraint(['record_id'], ['records.id'],
                                name='fk_workflow_instances_record_id'),
        sa.ForeignKeyConstraint(['created_by'], ['app_users.id'],
                                name='fk_workflow_instances_created_by'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('workflow_instances', schema=None) as batch_op:
        for column in ('workflow_id', 'operation_kind', 'well_id',
                       'current_stage', 'status', 'record_id', 'created_at'):
            batch_op.create_index(
                batch_op.f(f'ix_workflow_instances_{column}'), [column],
                unique=False)

    op.create_table(
        'workflow_stage_entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('instance_id', sa.Integer(), nullable=False),
        sa.Column('stage_id', sa.Integer(), nullable=True),
        sa.Column('stage_number', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('payload_json', sa.Text(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('submitted_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['instance_id'], ['workflow_instances.id'],
                                name='fk_workflow_stage_entries_instance_id',
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['stage_id'], ['workflow_stages.id'],
                                name='fk_workflow_stage_entries_stage_id',
                                ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['app_users.id'],
                                name='fk_workflow_stage_entries_user_id'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('instance_id', 'stage_number',
                            name='uq_instance_stage'),
    )
    with op.batch_alter_table('workflow_stage_entries', schema=None) as batch_op:
        for column in ('instance_id', 'stage_number', 'status'):
            batch_op.create_index(
                batch_op.f(f'ix_workflow_stage_entries_{column}'), [column],
                unique=False)

    op.create_table(
        'workflow_attachments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('instance_id', sa.Integer(), nullable=False),
        sa.Column('stage_number', sa.Integer(), nullable=True),
        sa.Column('filename', sa.String(length=260), nullable=False),
        sa.Column('stored_name', sa.String(length=160), nullable=False),
        sa.Column('content_type', sa.String(length=120), nullable=True),
        sa.Column('size_bytes', sa.Integer(), nullable=True),
        sa.Column('uploaded_by', sa.Integer(), nullable=True),
        sa.Column('uploaded_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['instance_id'], ['workflow_instances.id'],
                                name='fk_workflow_attachments_instance_id',
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['uploaded_by'], ['app_users.id'],
                                name='fk_workflow_attachments_uploaded_by'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('workflow_attachments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_workflow_attachments_instance_id'),
                              ['instance_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_workflow_attachments_stage_number'),
                              ['stage_number'], unique=False)

    # An option that belongs to the process rules rather than to taste.
    with op.batch_alter_table('lookup_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_locked', sa.Boolean(), nullable=False,
                                      server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('lookup_items', schema=None) as batch_op:
        batch_op.drop_column('is_locked')
    op.drop_table('workflow_attachments')
    op.drop_table('workflow_stage_entries')
    op.drop_table('workflow_instances')
    op.drop_table('workflow_stage_items')
    op.drop_table('workflow_stages')
    op.drop_table('workflow_definitions')
