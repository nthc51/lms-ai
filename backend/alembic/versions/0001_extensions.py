"""extensions and immutable_unaccent

Revision ID: 0001
Revises:
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION immutable_unaccent(text)
        RETURNS text AS $$
          SELECT public.unaccent('public.unaccent'::regdictionary, $1);
        $$ LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS immutable_unaccent(text)")
