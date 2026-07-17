"""add voice_log table (plan v2, fase 4)

Revision ID: 8c4d2f7a91b3
Revises: 531e052bb60d
Create Date: 2026-07-17 05:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision: str = '8c4d2f7a91b3'
down_revision: Union[str, Sequence[str], None] = '531e052bb60d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('voice_log',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('game_id', sa.Integer(), nullable=False),
    sa.Column('transcript', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('parsed', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('error_detail', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('action_id', sa.Integer(), nullable=True),
    sa.Column('duration_ms', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("status IN ('applied', 'parse_error', 'validation_error', 'empty_audio')", name=op.f('ck_voice_log_voice_log_status_check')),
    sa.ForeignKeyConstraint(['game_id'], ['game.id'], name=op.f('fk_voice_log_game_id_game')),
    sa.ForeignKeyConstraint(['action_id'], ['score_action.id'], name=op.f('fk_voice_log_action_id_score_action')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_voice_log'))
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('voice_log')
