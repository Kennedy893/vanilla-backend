"""Add sequences used to generate lot and event codes.

Revision ID: 7b4f1c2d8e90
Revises: e52e228d7ac0
Create Date: 2026-10-14
"""
from typing import Sequence, Union

from alembic import op


revision: str = "7b4f1c2d8e90"
down_revision: Union[str, Sequence[str], None] = "e52e228d7ac0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS lot_code_seq")
    op.execute("CREATE SEQUENCE IF NOT EXISTS event_code_seq")

    # Start after existing generated codes so an upgrade cannot create duplicates.
    op.execute(
        """
        SELECT setval(
            'lot_code_seq',
            COALESCE(
                (
                    SELECT MAX(CAST(SUBSTRING(lot_code FROM '^LOT-([0-9]+)$') AS BIGINT)) + 1
                    FROM lots
                    WHERE lot_code ~ '^LOT-[0-9]+$'
                ),
                1
            ),
            false
        )
        """
    )
    op.execute(
        """
        SELECT setval(
            'event_code_seq',
            COALESCE(
                (
                    SELECT MAX(CAST(SUBSTRING(event_code FROM '^EVT-([0-9]+)$') AS BIGINT)) + 1
                    FROM traceability_events
                    WHERE event_code ~ '^EVT-[0-9]+$'
                ),
                1
            ),
            false
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP SEQUENCE IF EXISTS event_code_seq")
    op.execute("DROP SEQUENCE IF EXISTS lot_code_seq")
