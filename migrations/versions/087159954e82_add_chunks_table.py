"""add chunks table

Revision ID: 087159954e82
Revises: a2287198a475
Create Date: 2026-06-22 14:57:15.520662

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = '087159954e82'
down_revision: Union[str, Sequence[str], None] = 'a2287198a475'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("ingestion_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("ingestions.id", ondelete="CASCADE"), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("block_type", sa.String(20), nullable=True),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(768), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(),
                  server_default=sa.text("NOW()"), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("chunks")
