"""add archive columns to lots

Revision ID: 6aaabedfa046
Revises: 2b93e37362bf
Create Date: 2026-10-20 14:47:08.601392

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6aaabedfa046'
down_revision: Union[str, Sequence[str], None] = '2b93e37362bf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "lots",
        sa.Column("archived_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "lots",
        sa.Column("archived_by_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "lots",
        sa.Column("archive_reason", sa.String(length=500), nullable=True),
    )

    op.create_foreign_key(
        "fk_lots_archived_by_id_users",
        "lots",
        "users",
        ["archived_by_id"],
        ["id"],
    )

    op.create_check_constraint(
        "archive_fields_together",
        "lots",
        """
        (
            archived_at IS NULL
            AND archived_by_id IS NULL
            AND archive_reason IS NULL
        )
        OR
        (
            archived_at IS NOT NULL
            AND archived_by_id IS NOT NULL
            AND archive_reason IS NOT NULL
        )
        """,
    )

    op.create_check_constraint(
        "archived_requires_date",
        "lots",
        "status <> 'archived' OR archived_at IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "archived_requires_date",
        "lots",
        type_="check",
    )
    op.drop_constraint(
        "archive_fields_together",
        "lots",
        type_="check",
    )
    op.drop_constraint(
        "fk_lots_archived_by_id_users",
        "lots",
        type_="foreignkey",
    )

    op.drop_column("lots", "archive_reason")
    op.drop_column("lots", "archived_by_id")
    op.drop_column("lots", "archived_at")