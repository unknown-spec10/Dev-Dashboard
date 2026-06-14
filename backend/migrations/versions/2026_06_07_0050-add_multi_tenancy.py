"""add multi tenancy

Revision ID: 412b1b583333
Revises: 302c1b582222
Create Date: 2026-06-07 00:50:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '412b1b583333'
down_revision: Union[str, None] = '302c1b582222'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 1. Create tenants table
    op.create_table(
        'tenants',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_tenants_slug', 'tenants', ['slug'], unique=True)

    # Generate a constant UUID for the default tenant so we can use it in backfills reliably
    default_tenant_id = '00000000-0000-0000-0000-000000000000'
    
    # Seed the default tenant
    op.execute(
        f"INSERT INTO tenants (id, name, slug, is_active) VALUES ('{default_tenant_id}', 'Default Tenant', 'default', true);"
    )

    # 2. Add tenant_id columns as nullable first
    op.add_column('api_keys', sa.Column('tenant_id', sa.UUID(), nullable=True))
    op.add_column('jobs', sa.Column('tenant_id', sa.UUID(), nullable=True))
    op.add_column('document_embeddings', sa.Column('tenant_id', sa.UUID(), nullable=True))

    # 3. Backfill existing records to the default tenant
    # Keep the super-admin API key global (tenant_id = NULL)
    op.execute(
        f"UPDATE api_keys SET tenant_id = '{default_tenant_id}' WHERE key != 'dev-dashboard-super-key';"
    )
    op.execute(
        f"UPDATE jobs SET tenant_id = '{default_tenant_id}';"
    )
    op.execute(
        f"UPDATE document_embeddings SET tenant_id = '{default_tenant_id}';"
    )

    # 4. Alter columns to NOT NULL for jobs and document_embeddings after backfill
    op.alter_column('jobs', 'tenant_id', nullable=False)
    op.alter_column('document_embeddings', 'tenant_id', nullable=False)

    # 5. Create constraints and indexes
    op.create_foreign_key('fk_api_keys_tenant_id_tenants', 'api_keys', 'tenants', ['tenant_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_jobs_tenant_id_tenants', 'jobs', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('fk_document_embeddings_tenant_id_tenants', 'document_embeddings', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')

    op.create_index('ix_api_keys_tenant_id', 'api_keys', ['tenant_id'], unique=False)
    op.create_index('ix_jobs_tenant_id', 'jobs', ['tenant_id'], unique=False)
    op.create_index('ix_document_embeddings_tenant_id', 'document_embeddings', ['tenant_id'], unique=False)

def downgrade() -> None:
    # Drop indexes and constraints
    op.drop_index('ix_document_embeddings_tenant_id', table_name='document_embeddings')
    op.drop_index('ix_jobs_tenant_id', table_name='jobs')
    op.drop_index('ix_api_keys_tenant_id', table_name='api_keys')

    op.drop_constraint('fk_document_embeddings_tenant_id_tenants', 'document_embeddings', type_='foreignkey')
    op.drop_constraint('fk_jobs_tenant_id_tenants', 'jobs', type_='foreignkey')
    op.drop_constraint('fk_api_keys_tenant_id_tenants', 'api_keys', type_='foreignkey')

    # Drop columns
    op.drop_column('document_embeddings', 'tenant_id')
    op.drop_column('jobs', 'tenant_id')
    op.drop_column('api_keys', 'tenant_id')

    # Drop tenants table
    op.drop_index('ix_tenants_slug', table_name='tenants')
    op.drop_table('tenants')
