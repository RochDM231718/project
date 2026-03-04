"""add missing enum values

Revision ID: add_missing_enum_values
Revises: 75b155daab71
Create Date: 2026-03-04

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'add_missing_enum_values'
down_revision: Union[str, Sequence[str], None] = '75b155daab71'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        # AchievementStatus: DB has PENDING, APPROVED, REJECTED — add REVISION and ARCHIVED
        op.execute("ALTER TYPE achievementstatus ADD VALUE IF NOT EXISTS 'REVISION'")
        op.execute("ALTER TYPE achievementstatus ADD VALUE IF NOT EXISTS 'ARCHIVED'")

        # UserStatus: DB has PENDING, ACTIVE, BANNED — add REJECTED and DELETED
        op.execute("ALTER TYPE userstatus ADD VALUE IF NOT EXISTS 'REJECTED'")
        op.execute("ALTER TYPE userstatus ADD VALUE IF NOT EXISTS 'DELETED'")


def downgrade() -> None:
    # PostgreSQL does not support removing values from enum types
    pass
