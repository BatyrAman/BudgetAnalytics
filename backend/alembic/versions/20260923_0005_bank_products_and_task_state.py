"""bank products (rates with source + fetched_at), monthly reports, payment reminders

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-23 18:45:13.237424

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('bank_products',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('bank_id', sa.Integer(), nullable=False),
    sa.Column('product_type', sa.Enum('consumer_loan', 'mortgage', 'auto_loan', 'credit_card', 'installment', 'microloan', 'deposit', name='product_type', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('external_key', sa.String(length=100), nullable=False),
    sa.Column('rate_min', sa.Numeric(precision=7, scale=4), nullable=False),
    sa.Column('rate_max', sa.Numeric(precision=7, scale=4), nullable=False),
    sa.Column('gesv', sa.Numeric(precision=7, scale=4), nullable=True),
    sa.Column('term_min', sa.Integer(), nullable=True),
    sa.Column('term_max', sa.Integer(), nullable=True),
    sa.Column('amount_min', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('amount_max', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('currency', sa.String(length=3), server_default='KZT', nullable=False),
    sa.Column('conditions', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('source', sa.String(length=100), nullable=False),
    sa.Column('source_url', sa.String(length=500), nullable=False),
    sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('amount_min IS NULL OR amount_max IS NULL OR amount_max >= amount_min', name=op.f('ck_bank_products_amount_range')),
    sa.CheckConstraint('rate_min >= 0 AND rate_max >= rate_min', name=op.f('ck_bank_products_rate_range')),
    sa.CheckConstraint('term_min IS NULL OR term_max IS NULL OR term_max >= term_min', name=op.f('ck_bank_products_term_range')),
    sa.ForeignKeyConstraint(['bank_id'], ['banks.id'], name=op.f('fk_bank_products_bank_id_banks')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_bank_products')),
    sa.UniqueConstraint('bank_id', 'product_type', 'external_key', name='uq_bank_products_key')
    )
    op.create_index('ix_bank_products_type_active', 'bank_products', ['product_type', 'is_active'], unique=False)
    op.create_table('monthly_reports',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('period_start', sa.Date(), nullable=False),
    sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('generated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_monthly_reports_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_monthly_reports')),
    sa.UniqueConstraint('user_id', 'period_start', name='uq_monthly_reports_user_period')
    )
    op.create_table('payment_reminders',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('debt_id', sa.Integer(), nullable=False),
    sa.Column('due_date', sa.Date(), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('sent_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['debt_id'], ['debts.id'], name=op.f('fk_payment_reminders_debt_id_debts'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_payment_reminders_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_payment_reminders')),
    sa.UniqueConstraint('debt_id', 'due_date', 'kind', name='uq_payment_reminders_once')
    )
    op.create_index(op.f('ix_payment_reminders_user_id'), 'payment_reminders', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_payment_reminders_user_id'), table_name='payment_reminders')
    op.drop_table('payment_reminders')
    op.drop_table('monthly_reports')
    op.drop_index('ix_bank_products_type_active', table_name='bank_products')
    op.drop_table('bank_products')
