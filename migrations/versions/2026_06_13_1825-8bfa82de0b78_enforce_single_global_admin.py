"""enforce_single_global_admin

Revision ID: 8bfa82de0b78
Revises: a2f46f17bfe0
Create Date: 2026-06-13 18:25:05.337280

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8bfa82de0b78'
down_revision: Union[str, None] = 'a2f46f17bfe0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enforce that all existing users are set to not admin
    op.execute("UPDATE users SET is_admin = false;")
    
    # 2. Create partial unique index guaranteeing at most one admin
    op.create_index(
        'uq_single_global_admin',
        'users',
        ['is_admin'],
        unique=True,
        postgresql_where=sa.text('is_admin = true')
    )
    
    # 3. Seed the new unique global admin user
    op.execute(
        "INSERT INTO users (id, email, is_admin, is_active, created_at) "
        "VALUES (gen_random_uuid(), 'deeppodder57@gmail.com', true, true, now());"
    )

def downgrade() -> None:
    # 1. Remove the seeded admin user
    op.execute("DELETE FROM users WHERE email = 'deeppodder57@gmail.com';")
    
    # 2. Drop the partial unique index
    op.drop_index('uq_single_global_admin', table_name='users', postgresql_where=sa.text('is_admin = true'))
