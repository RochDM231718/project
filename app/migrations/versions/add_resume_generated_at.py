"""add resume_generated_at to users

Revision ID: add_resume_generated_at
Revises: add_support_tables
Create Date: 2026-03-15 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'add_resume_generated_at'
down_revision: Union[str, Sequence[str], None] = 'add_support_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('resume_generated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'resume_generated_at')
