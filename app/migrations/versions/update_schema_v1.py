
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'update_schema_v1'
down_revision = '620951dcc34a'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table('achievements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('file_path', sa.String(), nullable=False),
        sa.Column('preview_path', sa.String(), nullable=True),
        sa.Column('status', sa.Enum('PENDING', 'APPROVED', 'REJECTED', name='achievementstatus'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    try:
        bind = op.get_bind()
        if bind.engine.name == 'postgresql':
            status_enum = postgresql.ENUM('PENDING', 'ACTIVE', 'BANNED', name='userstatus')
            status_enum.create(bind)
    except:
        pass

    op.add_column('users', sa.Column('status', sa.Enum('PENDING', 'ACTIVE', 'BANNED', name='userstatus'), nullable=True))
    op.add_column('users', sa.Column('avatar_path', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'avatar_path')
    op.drop_column('users', 'status')
    op.drop_table('achievements')