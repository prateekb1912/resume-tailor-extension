"""add LinkedIn manual refresh quota

Revision ID: b61c8a2f7d10
Revises: 2595e40fbaa8
Create Date: 2026-08-20 13:45:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b61c8a2f7d10"
down_revision: Union[str, Sequence[str], None] = "2595e40fbaa8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "profiles",
        sa.Column("last_linkedin_refresh_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("profiles", "last_linkedin_refresh_at")
