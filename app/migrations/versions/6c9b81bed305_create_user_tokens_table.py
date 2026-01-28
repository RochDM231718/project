
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '6c9b81bed305'
down_revision: Union[str, Sequence[str], None] = '3fb740c4328e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('user_tokens',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('token', sa.String(), nullable=False),
    sa.Column('type', sa.Enum('RESET_PASSWORD', 'EMAIL_VERIFICATION', name='user_token_type'), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token')
    )
    op.create_index(op.f('ix_user_tokens_id'), 'user_tokens', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_user_tokens_id'), table_name='user_tokens')
    op.drop_table('user_tokens')
