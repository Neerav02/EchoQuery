"""sync_missing_legacy_columns

Revision ID: bb3e66028d93
Revises: a43181a5d516
Create Date: 2026-11-11 16:01:00.495663

"""
from typing import Sequence, Union

from alembic import op, context
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bb3e66028d93'
down_revision: Union[str, Sequence[str], None] = 'a43181a5d516'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema safely checking column existence."""
    if context.is_offline_mode():
        user_cols = []
        job_cols = []
    else:
        bind = op.get_bind()
        inspector = sa.inspect(bind)
        user_cols = [c['name'] for c in inspector.get_columns('users')]
        job_cols = [c['name'] for c in inspector.get_columns('jobs')]

    with op.batch_alter_table('users', schema=None) as batch_op:
        if 'created_at' not in user_cols:
            batch_op.add_column(sa.Column('created_at', sa.DateTime(), nullable=True))

    with op.batch_alter_table('jobs', schema=None) as batch_op:
        if 'retry_count' not in job_cols:
            batch_op.add_column(sa.Column('retry_count', sa.Integer(), server_default='0', nullable=True))
        if 'max_retries' not in job_cols:
            batch_op.add_column(sa.Column('max_retries', sa.Integer(), server_default='3', nullable=True))
        if 'error_message' not in job_cols:
            batch_op.add_column(sa.Column('error_message', sa.Text(), nullable=True))
        if 'execution_time_ms' not in job_cols:
            batch_op.add_column(sa.Column('execution_time_ms', sa.Float(), nullable=True))
        if 'is_dlq' not in job_cols:
            batch_op.add_column(sa.Column('is_dlq', sa.Boolean(), server_default='0', nullable=True))
        if 'lock_acquired' not in job_cols:
            batch_op.add_column(sa.Column('lock_acquired', sa.Boolean(), server_default='0', nullable=True))
        if 'created_at' not in job_cols:
            batch_op.add_column(sa.Column('created_at', sa.DateTime(), nullable=True))
        if 'updated_at' not in job_cols:
            batch_op.add_column(sa.Column('updated_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    pass
