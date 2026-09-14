"""app meta table

Records facts about the database file itself, so a one-time data repair
(currently the UTC → wall-clock timestamp conversion) can tell an already
converted database from one that still needs it.

Revision ID: a1c4e7b90d31
Revises: 5accc7790812
Create Date: 2026-09-14 10:52:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1c4e7b90d31'
down_revision = '5accc7790812'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'app_meta',
        sa.Column('key', sa.String(length=60), nullable=False),
        sa.Column('value', sa.String(length=200), nullable=True),
        sa.PrimaryKeyConstraint('key'),
    )


def downgrade():
    op.drop_table('app_meta')
