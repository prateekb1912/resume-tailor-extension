"""remove users

Revision ID: 71353a403e76
Revises: e1b972a1f136
Create Date: 2026-07-15 04:34:32.909677

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '71353a403e76'
down_revision: Union[str, Sequence[str], None] = 'e1b972a1f136'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Drop everything that references users BEFORE dropping users itself.
    # profiles: remove the user_id FK + column
    op.drop_index(op.f('ix_profiles_user_id'), table_name='profiles')
    op.drop_constraint(op.f('profiles_user_id_fkey'), 'profiles', type_='foreignkey')
    op.drop_column('profiles', 'user_id')

    # tailor_jobs: swap user_id -> profile_id
    op.add_column('tailor_jobs', sa.Column('profile_id', sa.UUID(), nullable=False))
    op.drop_constraint(op.f('tailor_jobs_user_id_fkey'), 'tailor_jobs', type_='foreignkey')
    op.drop_index(op.f('ix_tailor_jobs_user_id'), table_name='tailor_jobs')
    op.drop_column('tailor_jobs', 'user_id')
    op.create_index(op.f('ix_tailor_jobs_profile_id'), 'tailor_jobs', ['profile_id'], unique=False)
    op.create_foreign_key(
        op.f('tailor_jobs_profile_id_fkey'), 'tailor_jobs', 'profiles',
        ['profile_id'], ['id'], ondelete='CASCADE',
    )

    # users now has no dependents -> safe to drop
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')


def downgrade() -> None:
    """Downgrade schema."""
    # Recreate users FIRST so the FKs below have something to reference.
    op.create_table(
        'users',
        sa.Column('email', sa.VARCHAR(length=255), autoincrement=False, nullable=False),
        sa.Column('password_hash', sa.VARCHAR(length=255), autoincrement=False, nullable=False),
        sa.Column('id', sa.UUID(), autoincrement=False, nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('users_pkey')),
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    # tailor_jobs: profile_id -> user_id
    op.drop_constraint(op.f('tailor_jobs_profile_id_fkey'), 'tailor_jobs', type_='foreignkey')
    op.drop_index(op.f('ix_tailor_jobs_profile_id'), table_name='tailor_jobs')
    op.drop_column('tailor_jobs', 'profile_id')
    op.add_column('tailor_jobs', sa.Column('user_id', sa.UUID(), autoincrement=False, nullable=False))
    op.create_index(op.f('ix_tailor_jobs_user_id'), 'tailor_jobs', ['user_id'], unique=False)
    op.create_foreign_key(op.f('tailor_jobs_user_id_fkey'), 'tailor_jobs', 'users', ['user_id'], ['id'], ondelete='CASCADE')

    # profiles: re-add user_id
    op.add_column('profiles', sa.Column('user_id', sa.UUID(), autoincrement=False, nullable=False))
    op.create_index(op.f('ix_profiles_user_id'), 'profiles', ['user_id'], unique=True)
    op.create_foreign_key(op.f('profiles_user_id_fkey'), 'profiles', 'users', ['user_id'], ['id'], ondelete='CASCADE')
