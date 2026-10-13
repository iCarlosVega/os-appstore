"""Add anonymous community suggestions without converting historical requests."""
from alembic import op
import sqlalchemy as sa

revision = "0003_community_requests"
down_revision = "0002_telegram_reviews"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "community_suggestions",
        sa.Column("repo_id", sa.Text(), primary_key=True, nullable=False),
        sa.Column("repo_url", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.CheckConstraint("state IN ('pending','queued')", name="community_suggestion_state"),
    )
    op.create_table(
        "community_contributions",
        sa.Column("repo_id", sa.Text(), sa.ForeignKey("community_suggestions.repo_id"), primary_key=True, nullable=False),
        sa.Column("visitor_key", sa.Text(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_index("community_contributions_cutoff", "community_contributions", ["created_at", "repo_id"])


def downgrade():
    raise RuntimeError(
        "Community request downgrade is disabled to preserve suggestion history. "
        "Disable the feature and restore a verified backup into a separate database instead."
    )
