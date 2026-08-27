"""Add Green-compatible pipeline/report metadata without removing Blue columns."""

revision = "0001_green_additive"
down_revision = None


def upgrade() -> None:
    """Applied by migration runner using migration/schema.sql."""


def downgrade() -> None:
    """Downgrade is intentionally empty; operator restores a fresh backup."""
