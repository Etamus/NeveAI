"""Index file listings without changing file data or metadata."""

from alembic import op
import sqlalchemy as sa

revision = "d8a91f02c631"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade():
    indexes = sa.inspect(op.get_bind()).get_indexes("file")
    if not any(index["name"] == "file_user_created_id_idx" for index in indexes):
        op.create_index("file_user_created_id_idx", "file", ["user_id", "created_at", "id"])


def downgrade():
    op.drop_index("file_user_created_id_idx", table_name="file")
