
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '620951dcc34a'
down_revision: Union[str, Sequence[str], None] = '6c9b81bed305'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('pages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(), nullable=False),
    sa.Column('slug', sa.String(), nullable=False),
    sa.Column('content', sa.Text(), nullable=True),
    sa.Column('published_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_pages_id'), 'pages', ['id'], unique=False)
    op.create_index(op.f('ix_pages_published_at'), 'pages', ['published_at'], unique=False)
    op.create_index(op.f('ix_pages_slug'), 'pages', ['slug'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_pages_slug'), table_name='pages')
    op.drop_index(op.f('ix_pages_published_at'), table_name='pages')
    op.drop_index(op.f('ix_pages_id'), table_name='pages')
    op.drop_table('pages')

