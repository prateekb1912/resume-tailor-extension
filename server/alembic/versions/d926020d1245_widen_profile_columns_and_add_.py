"""widen profile columns and add preferences

Revision ID: d926020d1245
Revises: 688f8038af08
Create Date: 2026-08-08 01:59:04.158322

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd926020d1245'
down_revision: Union[str, Sequence[str], None] = '688f8038af08'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "profiles", "email",
        existing_type=sa.String(length=32), type_=sa.String(length=255),
        existing_nullable=True,
    )
    op.alter_column(
        "profiles", "name",
        existing_type=sa.String(length=32), type_=sa.String(length=64),
        existing_nullable=True,
    )
    op.add_column(
        "profiles",
        sa.Column(
            "preferences",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_unique_constraint("uq_profiles_email", "profiles", ["email"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("uq_profiles_email", "profiles", type_="unique")
    op.drop_column("profiles", "preferences")
    op.alter_column(
        "profiles", "name",
        existing_type=sa.String(length=64), type_=sa.String(length=32),
        existing_nullable=True,
    )
    op.alter_column(
        "profiles", "email",
        existing_type=sa.String(length=255), type_=sa.String(length=32),
        existing_nullable=True,
    )
