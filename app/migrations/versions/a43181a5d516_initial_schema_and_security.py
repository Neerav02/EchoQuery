"""initial_schema_and_security

Revision ID: a43181a5d516
Revises: 
Create Date: 2026-11-10 23:06:36.807656

"""
from typing import Sequence, Union

from alembic import op, context
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a43181a5d516'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_inspector():
    if context.is_offline_mode():
        return None
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    """Upgrade schema cleanly on both fresh and legacy pre-Alembic databases."""
    inspector = _get_inspector()
    existing_tables = set(inspector.get_table_names()) if inspector else set()

    if 'users' not in existing_tables:
        op.create_table(
            'users',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('email', sa.String(), nullable=True),
            sa.Column('hashed_password', sa.String(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
        op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    if 'jobs' not in existing_tables:
        op.create_table(
            'jobs',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('filename', sa.String(), nullable=True),
            sa.Column('storage_name', sa.String(), nullable=True),
            sa.Column('status', sa.String(), nullable=True),
            sa.Column('transcript', sa.String(), nullable=True),
            sa.Column('summary', sa.String(), nullable=True),
            sa.Column('sentiment', sa.String(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_jobs_id'), 'jobs', ['id'], unique=False)

    if 'refresh_tokens' not in existing_tables:
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
    
    if 'outbox_tasks' not in existing_tables:
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

    # Refresh inspector after base tables are guaranteed to exist
    inspector = _get_inspector()
    job_cols = {c['name'] for c in inspector.get_columns('jobs')} if inspector else set()
    job_indexes = {idx['name'] for idx in inspector.get_indexes('jobs')} if inspector else set()
    job_fks = inspector.get_foreign_keys('jobs') if inspector else []
    has_jobs_user_fk = any(
        fk.get('name') == 'fk_jobs_user_id'
        or (fk.get('constrained_columns') == ['user_id'] and fk.get('referred_table') == 'users')
        for fk in job_fks
    )

    with op.batch_alter_table('jobs', schema=None) as batch_op:
        if 'user_id' not in job_cols:
            batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
        if 'storage_bucket' not in job_cols:
            batch_op.add_column(sa.Column('storage_bucket', sa.String(), nullable=True))
        if 'idempotency_key' not in job_cols:
            batch_op.add_column(sa.Column('idempotency_key', sa.String(length=64), nullable=True))
        if 'lock_token' not in job_cols:
            batch_op.add_column(sa.Column('lock_token', sa.String(length=64), nullable=True))
        if 'ai_provider' not in job_cols:
            batch_op.add_column(sa.Column('ai_provider', sa.String(), nullable=True))
        if 'ai_model' not in job_cols:
            batch_op.add_column(sa.Column('ai_model', sa.String(), nullable=True))
        if 'token_usage' not in job_cols:
            batch_op.add_column(sa.Column('token_usage', sa.Integer(), nullable=True))
        if batch_op.f('ix_jobs_idempotency_key') not in job_indexes:
            batch_op.create_index(batch_op.f('ix_jobs_idempotency_key'), ['idempotency_key'], unique=True)
        if batch_op.f('ix_jobs_user_id') not in job_indexes:
            batch_op.create_index(batch_op.f('ix_jobs_user_id'), ['user_id'], unique=False)
        if not has_jobs_user_fk:
            batch_op.create_foreign_key('fk_jobs_user_id', 'users', ['user_id'], ['id'], ondelete='SET NULL')

    user_cols = {c['name'] for c in inspector.get_columns('users')} if inspector else set()
    user_indexes = {idx['name'] for idx in inspector.get_indexes('users')} if inspector else set()
    user_uniques = inspector.get_unique_constraints('users') if inspector else []
    has_email_unique = (
        'ix_users_email' in user_indexes
        or any(uc.get('column_names') == ['email'] for uc in user_uniques)
    )

    with op.batch_alter_table('users', schema=None) as batch_op:
        if 'is_superuser' not in user_cols:
            batch_op.add_column(sa.Column('is_superuser', sa.Boolean(), server_default='0', nullable=False))
        if 'password_migrated' not in user_cols:
            batch_op.add_column(sa.Column('password_migrated', sa.Boolean(), server_default='0', nullable=False))
        if inspector is not None and not has_email_unique:
            batch_op.create_index(batch_op.f('ix_users_email'), ['email'], unique=True)


def downgrade() -> None:
    """Safely revert columns/tables added by a43181a5d516 without dropping base users/jobs tables."""
    inspector = _get_inspector()
    existing_tables = set(inspector.get_table_names()) if inspector else {'users', 'jobs', 'refresh_tokens', 'outbox_tasks'}

    if 'users' in existing_tables:
        user_cols = {c['name'] for c in inspector.get_columns('users')} if inspector else {'is_superuser', 'password_migrated'}
        with op.batch_alter_table('users', schema=None) as batch_op:
            if 'password_migrated' in user_cols:
                batch_op.drop_column('password_migrated')
            if 'is_superuser' in user_cols:
                batch_op.drop_column('is_superuser')

    if 'jobs' in existing_tables:
        job_cols = {
            c['name'] for c in inspector.get_columns('jobs')
        } if inspector else {
            'user_id', 'storage_bucket', 'idempotency_key', 'lock_token',
            'ai_provider', 'ai_model', 'token_usage'
        }
        job_indexes = {
            idx['name'] for idx in inspector.get_indexes('jobs')
        } if inspector else {'ix_jobs_user_id', 'ix_jobs_idempotency_key'}
        job_fk_names = {
            fk['name'] for fk in inspector.get_foreign_keys('jobs') if fk.get('name')
        } if inspector else {'fk_jobs_user_id'}

        with op.batch_alter_table('jobs', schema=None) as batch_op:
            if 'fk_jobs_user_id' in job_fk_names:
                batch_op.drop_constraint('fk_jobs_user_id', type_='foreignkey')
            if batch_op.f('ix_jobs_user_id') in job_indexes:
                batch_op.drop_index(batch_op.f('ix_jobs_user_id'))
            if batch_op.f('ix_jobs_idempotency_key') in job_indexes:
                batch_op.drop_index(batch_op.f('ix_jobs_idempotency_key'))
            for col in ('token_usage', 'ai_model', 'ai_provider', 'lock_token', 'idempotency_key', 'storage_bucket', 'user_id'):
                if col in job_cols:
                    batch_op.drop_column(col)

    if 'outbox_tasks' in existing_tables:
        outbox_indexes = {
            idx['name'] for idx in inspector.get_indexes('outbox_tasks')
        } if inspector else {'ix_outbox_tasks_status', 'ix_outbox_tasks_job_id', 'ix_outbox_tasks_id'}
        for idx_name in ('ix_outbox_tasks_status', 'ix_outbox_tasks_job_id', 'ix_outbox_tasks_id'):
            if op.f(idx_name) in outbox_indexes:
                op.drop_index(op.f(idx_name), table_name='outbox_tasks')
        op.drop_table('outbox_tasks')

    if 'refresh_tokens' in existing_tables:
        rt_indexes = {
            idx['name'] for idx in inspector.get_indexes('refresh_tokens')
        } if inspector else {'ix_refresh_tokens_user_id', 'ix_refresh_tokens_token', 'ix_refresh_tokens_id'}
        for idx_name in ('ix_refresh_tokens_user_id', 'ix_refresh_tokens_token', 'ix_refresh_tokens_id'):
            if op.f(idx_name) in rt_indexes:
                op.drop_index(op.f(idx_name), table_name='refresh_tokens')
        op.drop_table('refresh_tokens')
