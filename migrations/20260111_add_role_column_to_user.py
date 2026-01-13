from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '03194b3040ab'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # 使用 batch_alter_table 並指定 server_default，這樣 SQLite 才能新增 NOT NULL 欄位
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('role', sa.String(length=20), nullable=False, server_default='student')
        )


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('role')
