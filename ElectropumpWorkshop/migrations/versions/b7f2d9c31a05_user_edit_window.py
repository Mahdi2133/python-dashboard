"""per-user record edit window

How many hours after a record is written its author may still change it.
NULL means no limit, which is what every existing account keeps.

Revision ID: b7f2d9c31a05
Revises: a1c4e7b90d31
Create Date: 2026-09-14 11:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7f2d9c31a05'
down_revision = 'a1c4e7b90d31'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('app_users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('edit_window_hours', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('app_users', schema=None) as batch_op:
        batch_op.drop_column('edit_window_hours')
