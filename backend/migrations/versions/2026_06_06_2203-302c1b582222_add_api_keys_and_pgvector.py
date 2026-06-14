"""add_api_keys_and_pgvector

Revision ID: 302c1b582222
Revises: 99e3900a477d
Create Date: 2026-06-06 22:03:20.783791

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '302c1b582222'
down_revision: Union[str, None] = '99e3900a477d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

def upgrade() -> None:
    # 1. Enable the pgvector extension before configuring vector columns
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # 2. Create api_keys table
    op.create_table(
        'api_keys',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('key', sa.String(length=255), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('scopes', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_api_keys_key', 'api_keys', ['key'], unique=True)

    # 3. Create document_embeddings table
    op.create_table(
        'document_embeddings',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('job_id', sa.UUID(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('embedding', Vector(dim=1536), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_document_embeddings_job_id', 'document_embeddings', ['job_id'], unique=False)

    # 4. Add priority column to jobs table
    op.add_column('jobs', sa.Column('priority', sa.String(length=50), server_default='default', nullable=False))


def downgrade() -> None:
    # 1. Drop priority column from jobs table
    op.drop_column('jobs', 'priority')

    # 2. Drop document_embeddings table & index
    op.drop_index('ix_document_embeddings_job_id', table_name='document_embeddings')
    op.drop_table('document_embeddings')

    # 3. Drop api_keys table & index
    op.drop_index('ix_api_keys_key', table_name='api_keys')
    op.drop_table('api_keys')

    # 4. Drop vector extension (optional but clean for complete tear-down)
    op.execute("DROP EXTENSION IF EXISTS vector;")

