"""add education level and course to users

Revision ID: 2f2e4cddad31
Revises: add_rejection_reason
Create Date: 2026-02-20 21:07:33.298367

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '2f2e4cddad31'
down_revision: Union[str, Sequence[str], None] = 'add_rejection_reason'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Сначала явно создаем тип ENUM в базе данных
    education_level_enum = postgresql.ENUM('COLLEGE', 'BACHELOR', 'SPECIALIST', 'MASTER', 'POSTGRADUATE', name='educationlevel')
    education_level_enum.create(op.get_bind(), checkfirst=True)

    # 2. Теперь добавляем колонки, используя созданный тип
    op.add_column('users', sa.Column('education_level', education_level_enum, nullable=True))
    op.add_column('users', sa.Column('course', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Удаляем колонки
    op.drop_column('users', 'course')
    op.drop_column('users', 'education_level')

    # Удаляем сам тип ENUM из базы
    education_level_enum = postgresql.ENUM('COLLEGE', 'BACHELOR', 'SPECIALIST', 'MASTER', 'POSTGRADUATE', name='educationlevel')
    education_level_enum.drop(op.get_bind(), checkfirst=True)