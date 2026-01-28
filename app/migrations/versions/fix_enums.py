
from alembic import op
import sqlalchemy as sa


revision = 'fix_enums'
down_revision = 'update_schema_v1'
branch_labels = None
depends_on = None

def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'GUEST'")
        op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'STUDENT'")
        op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'MODERATOR'")

def downgrade() -> None:
    pass