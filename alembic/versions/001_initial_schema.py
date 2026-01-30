"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-01-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create outlets table
    op.create_table(
        'outlets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('opencritic_id', sa.Integer(), nullable=True),
        sa.Column('website_url', sa.String(length=512), nullable=True),
        sa.Column('logo_url', sa.String(length=512), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_outlets_name', 'outlets', ['name'], unique=False)
    op.create_index(op.f('ix_outlets_opencritic_id'), 'outlets', ['opencritic_id'], unique=True)

    # Create journalists table
    op.create_table(
        'journalists',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('opencritic_id', sa.Integer(), nullable=True),
        sa.Column('image_url', sa.String(length=512), nullable=True),
        sa.Column('bio', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_journalists_name', 'journalists', ['name'], unique=False)
    op.create_index(op.f('ix_journalists_opencritic_id'), 'journalists', ['opencritic_id'], unique=True)

    # Create games table
    op.create_table(
        'games',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=512), nullable=False),
        sa.Column('opencritic_id', sa.Integer(), nullable=True),
        sa.Column('steam_app_id', sa.Integer(), nullable=True),
        sa.Column('metacritic_slug', sa.String(length=255), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('release_date', sa.Date(), nullable=True),
        sa.Column('top_critic_score', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('percent_recommended', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('tier', sa.String(length=50), nullable=True),
        sa.Column('image_url', sa.String(length=512), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_games_release_date', 'games', ['release_date'], unique=False)
    op.create_index(op.f('ix_games_metacritic_slug'), 'games', ['metacritic_slug'], unique=False)
    op.create_index(op.f('ix_games_opencritic_id'), 'games', ['opencritic_id'], unique=True)
    op.create_index(op.f('ix_games_steam_app_id'), 'games', ['steam_app_id'], unique=False)

    # Create reviews table
    op.create_table(
        'reviews',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('journalist_id', sa.Integer(), nullable=False),
        sa.Column('game_id', sa.Integer(), nullable=False),
        sa.Column('outlet_id', sa.Integer(), nullable=True),
        sa.Column('score_raw', sa.String(length=50), nullable=False),
        sa.Column('score_scale', sa.String(length=50), nullable=True),
        sa.Column('score_normalized', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('review_url', sa.String(length=1024), nullable=True),
        sa.Column('snippet', sa.Text(), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('opencritic_review_id', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['game_id'], ['games.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['journalist_id'], ['journalists.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['outlet_id'], ['outlets.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('journalist_id', 'game_id', name='uq_journalist_game'),
        sa.UniqueConstraint('opencritic_review_id')
    )
    op.create_index('idx_reviews_published_at', 'reviews', ['published_at'], unique=False)
    op.create_index('idx_reviews_score_normalized', 'reviews', ['score_normalized'], unique=False)
    op.create_index(op.f('ix_reviews_game_id'), 'reviews', ['game_id'], unique=False)
    op.create_index(op.f('ix_reviews_journalist_id'), 'reviews', ['journalist_id'], unique=False)
    op.create_index(op.f('ix_reviews_outlet_id'), 'reviews', ['outlet_id'], unique=False)

    # Create user_scores table
    op.create_table(
        'user_scores',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('game_id', sa.Integer(), nullable=False),
        sa.Column('source', sa.Enum('STEAM', 'METACRITIC', name='userscoresource'), nullable=False),
        sa.Column('score', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('score_raw', sa.String(length=50), nullable=True),
        sa.Column('sample_size', sa.Integer(), nullable=True),
        sa.Column('positive_count', sa.Integer(), nullable=True),
        sa.Column('negative_count', sa.Integer(), nullable=True),
        sa.Column('review_score_desc', sa.String(length=100), nullable=True),
        sa.Column('scraped_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['game_id'], ['games.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_user_scores_scraped_at', 'user_scores', ['scraped_at'], unique=False)
    op.create_index(op.f('ix_user_scores_game_id'), 'user_scores', ['game_id'], unique=False)
    op.create_index(op.f('ix_user_scores_source'), 'user_scores', ['source'], unique=False)

    # Create disparity_snapshots table
    op.create_table(
        'disparity_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('journalist_id', sa.Integer(), nullable=True),
        sa.Column('outlet_id', sa.Integer(), nullable=True),
        sa.Column('game_id', sa.Integer(), nullable=True),
        sa.Column('snapshot_date', sa.Date(), nullable=False),
        sa.Column('avg_disparity_steam', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('avg_disparity_metacritic', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('avg_disparity_combined', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('review_count', sa.Integer(), nullable=False),
        sa.Column('std_deviation', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('min_disparity', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('max_disparity', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['game_id'], ['games.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['journalist_id'], ['journalists.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['outlet_id'], ['outlets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            """
            (journalist_id IS NOT NULL AND outlet_id IS NULL AND game_id IS NULL) OR
            (journalist_id IS NULL AND outlet_id IS NOT NULL AND game_id IS NULL) OR
            (journalist_id IS NULL AND outlet_id IS NULL AND game_id IS NOT NULL)
            """,
            name='ck_single_entity_type'
        )
    )
    op.create_index('idx_disparity_journalist', 'disparity_snapshots', ['journalist_id', 'snapshot_date'], unique=False)
    op.create_index('idx_disparity_outlet', 'disparity_snapshots', ['outlet_id', 'snapshot_date'], unique=False)
    op.create_index('idx_disparity_game', 'disparity_snapshots', ['game_id', 'snapshot_date'], unique=False)

    # Create sync_logs table
    op.create_table(
        'sync_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source', sa.Enum('OPENCRITIC', 'STEAM', 'METACRITIC', name='syncsource'), nullable=False),
        sa.Column('sync_type', sa.Enum('FULL', 'INCREMENTAL', name='synctype'), nullable=False),
        sa.Column('status', sa.Enum('RUNNING', 'COMPLETED', 'FAILED', name='syncstatus'), nullable=False),
        sa.Column('records_processed', sa.Integer(), server_default='0', nullable=False),
        sa.Column('records_created', sa.Integer(), server_default='0', nullable=False),
        sa.Column('records_updated', sa.Integer(), server_default='0', nullable=False),
        sa.Column('records_failed', sa.Integer(), server_default='0', nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_sync_logs_source', 'sync_logs', ['source', 'started_at'], unique=False)


def downgrade() -> None:
    op.drop_table('sync_logs')
    op.drop_table('disparity_snapshots')
    op.drop_table('user_scores')
    op.drop_table('reviews')
    op.drop_table('games')
    op.drop_table('journalists')
    op.drop_table('outlets')

    # Drop enums
    op.execute('DROP TYPE IF EXISTS syncstatus')
    op.execute('DROP TYPE IF EXISTS synctype')
    op.execute('DROP TYPE IF EXISTS syncsource')
    op.execute('DROP TYPE IF EXISTS userscoresource')
