"""auth: refresh token store (rotation, reuse detection), token_version

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-23 18:39:01.543273

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('refresh_tokens',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('jti', sa.String(length=64), nullable=False),
    sa.Column('family_id', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('replaced_by', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_refresh_tokens_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_refresh_tokens')),
    sa.UniqueConstraint('jti', name=op.f('uq_refresh_tokens_jti'))
    )
    op.create_index('ix_refresh_tokens_user_family', 'refresh_tokens', ['user_id', 'family_id'], unique=False)
    op.add_column('users', sa.Column('token_version', sa.Integer(), server_default='0', nullable=False))
    op.create_index('ix_users_email_lower', 'users', [sa.literal_column('lower(email)')], unique=False)


def downgrade() -> None:
    op.drop_index('ix_users_email_lower', table_name='users')
    op.drop_column('users', 'token_version')
    op.drop_index('ix_refresh_tokens_user_family', table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
