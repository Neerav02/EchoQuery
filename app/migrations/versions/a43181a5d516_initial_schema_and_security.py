"""initial_schema_and_security

Revision ID: a43181a5d516
Revises: 
Create Date: 2026-11-10 23:06:36.807656

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a43181a5d516'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('refresh_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('revoked', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_refresh_tokens_id'), 'refresh_tokens', ['id'], unique=False)
    op.create_index(op.f('ix_refresh_tokens_token'), 'refresh_tokens', ['token'], unique=True)
    op.create_index(op.f('ix_refresh_tokens_user_id'), 'refresh_tokens', ['user_id'], unique=False)
    
    op.create_table('outbox_tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=False),
        sa.Column('topic', sa.String(), nullable=False),
        sa.Column('payload', sa.Text(), nullable=False),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('dispatched_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_outbox_tasks_id'), 'outbox_tasks', ['id'], unique=False)
    op.create_index(op.f('ix_outbox_tasks_job_id'), 'outbox_tasks', ['job_id'], unique=False)
    op.create_index(op.f('ix_outbox_tasks_status'), 'outbox_tasks', ['status'], unique=False)

    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('storage_bucket', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('idempotency_key', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('lock_token', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('ai_provider', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('ai_model', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('token_usage', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_jobs_idempotency_key'), ['idempotency_key'], unique=True)
        batch_op.create_index(batch_op.f('ix_jobs_user_id'), ['user_id'], unique=False)
        batch_op.create_foreign_key('fk_jobs_user_id', 'users', ['user_id'], ['id'], ondelete='SET NULL')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_superuser', sa.Boolean(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('password_migrated', sa.Boolean(), server_default='0', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('password_migrated')
        batch_op.drop_column('is_superuser')

    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.drop_constraint('fk_jobs_user_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_jobs_user_id'))
        batch_op.drop_index(batch_op.f('ix_jobs_idempotency_key'))
        batch_op.drop_column('token_usage')
        batch_op.drop_column('ai_model')
        batch_op.drop_column('ai_provider')
        batch_op.drop_column('lock_token')
        batch_op.drop_column('idempotency_key')
        batch_op.drop_column('storage_bucket')
        batch_op.drop_column('user_id')

    op.drop_index(op.f('ix_outbox_tasks_status'), table_name='outbox_tasks')
    op.drop_index(op.f('ix_outbox_tasks_job_id'), table_name='outbox_tasks')
    op.drop_index(op.f('ix_outbox_tasks_id'), table_name='outbox_tasks')
    op.drop_table('outbox_tasks')

    op.drop_index(op.f('ix_refresh_tokens_user_id'), table_name='refresh_tokens')
    op.drop_index(op.f('ix_refresh_tokens_token'), table_name='refresh_tokens')
    op.drop_index(op.f('ix_refresh_tokens_id'), table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
