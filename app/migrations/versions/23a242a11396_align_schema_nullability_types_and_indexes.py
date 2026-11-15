"""align_schema_nullability_types_and_indexes

Revision ID: 23a242a11396
Revises: bb3e66028d93
Create Date: 2026-11-11 16:55:00.000000

"""
from typing import Sequence, Union

from alembic import op, context
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '23a242a11396'
down_revision: Union[str, Sequence[str], None] = 'bb3e66028d93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Align schema nullability, text types, and missing indexes with SQLAlchemy models."""
    offline = context.is_offline_mode()
    if not offline:
        bind = op.get_bind()
        inspector = sa.inspect(bind)

        # 1. Pre-flight check: Verify no NULL values exist before enforcing NOT NULL.
        # Do NOT insert placeholder data or overwrite records. Fail explicitly if unexpected NULLs exist.
        null_user_emails = bind.execute(sa.text("SELECT COUNT(*) FROM users WHERE email IS NULL")).scalar() or 0
        null_user_pws = bind.execute(sa.text("SELECT COUNT(*) FROM users WHERE hashed_password IS NULL")).scalar() or 0
        null_job_files = bind.execute(sa.text("SELECT COUNT(*) FROM jobs WHERE filename IS NULL")).scalar() or 0
        null_job_storage = bind.execute(sa.text("SELECT COUNT(*) FROM jobs WHERE storage_name IS NULL")).scalar() or 0

        if null_user_emails > 0 or null_user_pws > 0 or null_job_files > 0 or null_job_storage > 0:
            raise RuntimeError(
                f"Migration 23a242a11396 aborted: Cannot enforce NOT NULL constraint because existing records "
                f"contain NULL values (users.email: {null_user_emails}, users.hashed_password: {null_user_pws}, "
                f"jobs.filename: {null_job_files}, jobs.storage_name: {null_job_storage}). "
                f"Manual data remediation is required before applying this migration."
            )

        existing_user_indexes = {idx['name']: idx for idx in inspector.get_indexes('users')}
        existing_user_uniques = inspector.get_unique_constraints('users')
        has_email_unique = (
            any(idx.get('column_names') == ['email'] and idx.get('unique') for idx in existing_user_indexes.values())
            or any(uc.get('column_names') == ['email'] for uc in existing_user_uniques)
        )
        has_user_id_index = any(idx.get('column_names') == ['id'] for idx in existing_user_indexes.values())
        existing_job_indexes = {idx['name']: idx for idx in inspector.get_indexes('jobs')}
        has_job_id_index = any(idx.get('column_names') == ['id'] for idx in existing_job_indexes.values())
    else:
        has_email_unique = True
        has_user_id_index = True
        existing_job_indexes = {}
        has_job_id_index = True

    # 2. Update users table: email and hashed_password -> NOT NULL + parity indexes
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('email',
                              existing_type=sa.String(),
                              nullable=False)
        batch_op.alter_column('hashed_password',
                              existing_type=sa.String(),
                              nullable=False)
        if not offline and not has_user_id_index:
            batch_op.create_index(batch_op.f('ix_users_id'), ['id'], unique=False)
        if not offline and not has_email_unique:
            batch_op.create_index(batch_op.f('ix_users_email'), ['email'], unique=True)

    # 3. Update jobs table: filename, storage_name -> NOT NULL; transcript, summary -> TEXT
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.alter_column('filename',
                              existing_type=sa.String(),
                              nullable=False)
        batch_op.alter_column('storage_name',
                              existing_type=sa.String(),
                              nullable=False)
        batch_op.alter_column('transcript',
                              existing_type=sa.String(),
                              type_=sa.Text(),
                              existing_nullable=True)
        batch_op.alter_column('summary',
                              existing_type=sa.String(),
                              type_=sa.Text(),
                              existing_nullable=True)
        if not offline and not has_job_id_index:
            batch_op.create_index(batch_op.f('ix_jobs_id'), ['id'], unique=False)
        if 'ix_jobs_status' not in existing_job_indexes:
            batch_op.create_index(batch_op.f('ix_jobs_status'), ['status'], unique=False)


def downgrade() -> None:
    """Revert schema alignment changes."""
    if context.is_offline_mode():
        existing_job_indexes = ['ix_jobs_status']
    else:
        bind = op.get_bind()
        inspector = sa.inspect(bind)
        existing_job_indexes = [idx['name'] for idx in inspector.get_indexes('jobs')]

    # 1. Revert jobs columns back to nullable VARCHAR and drop index if present
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        if 'ix_jobs_status' in existing_job_indexes:
            batch_op.drop_index(batch_op.f('ix_jobs_status'))
        batch_op.alter_column('summary',
                              existing_type=sa.Text(),
                              type_=sa.String(),
                              existing_nullable=True)
        batch_op.alter_column('transcript',
                              existing_type=sa.Text(),
                              type_=sa.String(),
                              existing_nullable=True)
        batch_op.alter_column('storage_name',
                              existing_type=sa.String(),
                              nullable=True)
        batch_op.alter_column('filename',
                              existing_type=sa.String(),
                              nullable=True)

    # 2. Revert users columns back to nullable
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('hashed_password',
                              existing_type=sa.String(),
                              nullable=True)
        batch_op.alter_column('email',
                              existing_type=sa.String(),
                              nullable=True)

