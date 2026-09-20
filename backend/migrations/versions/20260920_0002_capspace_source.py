"""Register CapSpace as the free historical contract source.

Revision ID: 20260920_0002
Revises: 20260910_0001
"""

from __future__ import annotations

from alembic import op


revision = "20260920_0002"
down_revision = "20260910_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """INSERT INTO data_sources (code, display_name, base_url)
           VALUES ('capspace', 'CapSpace', 'https://cap-space.com')
           ON CONFLICT (code) DO UPDATE SET
               display_name = EXCLUDED.display_name,
               base_url = EXCLUDED.base_url"""
    )


def downgrade() -> None:
    op.execute("DELETE FROM data_sources WHERE code = 'capspace'")
