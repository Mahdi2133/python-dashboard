"""referrals and approvals on a stage

The workshop's process is a chain of handovers — «ارجاع به کارگاه مکانیک جهت
دمونتاژ», «برگشت به کارتابل بهره‌بردار جهت اقدامات تکمیلی» — so a stage now
says where its work goes when it is finished, and whether somebody has to sign
it off first. A stage entry records the handover that actually happened: who
sent it, to whom, with what note, and how the approver ruled.

Also `is_read_only` on a stage item: what an earlier stage filled can be shown
again, in full and unwritable, wherever the admin wants it.

Revision ID: e7c4a2b91d38
Revises: c3e18a7f45b2
Create Date: 2026-09-19 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e7c4a2b91d38'
down_revision = 'c3e18a7f45b2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('workflow_stages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('referral_mode', sa.String(length=10),
                                      nullable=False, server_default='next'))
        batch_op.add_column(sa.Column('referral_user_id', sa.Integer(),
                                      nullable=True))
        batch_op.add_column(sa.Column('referral_hint', sa.String(length=200),
                                      nullable=True))
        batch_op.add_column(sa.Column('needs_approval', sa.Boolean(),
                                      nullable=False, server_default=sa.text('0')))
        batch_op.add_column(sa.Column('approver_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('reject_to_stage', sa.Integer(),
                                      nullable=True))
        batch_op.create_index(batch_op.f('ix_workflow_stages_referral_user_id'),
                              ['referral_user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_workflow_stages_approver_id'),
                              ['approver_id'], unique=False)
        batch_op.create_foreign_key('fk_wf_stage_referral_user', 'app_users',
                                    ['referral_user_id'], ['id'],
                                    ondelete='SET NULL')
        batch_op.create_foreign_key('fk_wf_stage_approver', 'app_users',
                                    ['approver_id'], ['id'], ondelete='SET NULL')

    with op.batch_alter_table('workflow_stage_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_read_only', sa.Boolean(),
                                      nullable=False, server_default=sa.text('0')))

    with op.batch_alter_table('workflow_stage_entries', schema=None) as batch_op:
        batch_op.add_column(sa.Column('referred_to_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('referred_by_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('referred_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('referral_note', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('approver_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('decided_by_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('decided_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('decision_note', sa.Text(), nullable=True))
        batch_op.create_index(batch_op.f('ix_workflow_stage_entries_referred_to_id'),
                              ['referred_to_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_workflow_stage_entries_approver_id'),
                              ['approver_id'], unique=False)
        for name, column in (('fk_wf_entry_referred_to', 'referred_to_id'),
                             ('fk_wf_entry_referred_by', 'referred_by_id'),
                             ('fk_wf_entry_approver', 'approver_id'),
                             ('fk_wf_entry_decided_by', 'decided_by_id')):
            batch_op.create_foreign_key(name, 'app_users', [column], ['id'])


def downgrade():
    with op.batch_alter_table('workflow_stage_entries', schema=None) as batch_op:
        for name in ('fk_wf_entry_decided_by', 'fk_wf_entry_approver',
                     'fk_wf_entry_referred_by', 'fk_wf_entry_referred_to'):
            batch_op.drop_constraint(name, type_='foreignkey')
        for column in ('decision_note', 'decided_at', 'decided_by_id',
                       'approver_id', 'referral_note', 'referred_at',
                       'referred_by_id', 'referred_to_id'):
            batch_op.drop_column(column)
    with op.batch_alter_table('workflow_stage_items', schema=None) as batch_op:
        batch_op.drop_column('is_read_only')
    with op.batch_alter_table('workflow_stages', schema=None) as batch_op:
        batch_op.drop_constraint('fk_wf_stage_approver', type_='foreignkey')
        batch_op.drop_constraint('fk_wf_stage_referral_user', type_='foreignkey')
        for column in ('reject_to_stage', 'approver_id', 'needs_approval',
                       'referral_hint', 'referral_user_id', 'referral_mode'):
            batch_op.drop_column(column)
