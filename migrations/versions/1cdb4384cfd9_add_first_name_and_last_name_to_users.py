"""add first_name and last_name to users

Revision ID: 1cdb4384cfd9
Revises:
Create Date: 2026-06-18 12:29:14.879506

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '1cdb4384cfd9'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: add nullable so existing rows are not rejected
    op.add_column('users', sa.Column('first_name', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('last_name', sa.String(length=100), nullable=True))

    # Step 2: backfill existing rows with a placeholder
    op.execute("UPDATE users SET first_name = 'Unknown', last_name = 'Unknown' WHERE first_name IS NULL")

    # Step 3: enforce NOT NULL now that every row has a value
    op.alter_column('users', 'first_name', nullable=False)
    op.alter_column('users', 'last_name', nullable=False)


def downgrade() -> None:
    op.drop_column('users', 'last_name')
    op.drop_column('users', 'first_name')
