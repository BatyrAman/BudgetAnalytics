"""debts and debt payments

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-23 18:29:46.201079

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('debts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('bank_id', sa.Integer(), nullable=True),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('debt_type', sa.Enum('consumer_loan', 'installment', 'credit_card', 'mortgage', 'auto_loan', 'microloan', 'personal', name='debt_type', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('principal', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('balance', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('annual_rate', sa.Numeric(precision=7, scale=4), nullable=False),
    sa.Column('gesv', sa.Numeric(precision=7, scale=4), nullable=True),
    sa.Column('monthly_payment', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('payment_day', sa.Integer(), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('end_date', sa.Date(), nullable=True),
    sa.Column('schedule_type', sa.Enum('annuity', 'differential', 'revolving', name='debt_schedule_type', native_enum=False, create_constraint=True, length=16), nullable=False),
    sa.Column('currency', sa.String(length=3), server_default='KZT', nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('annual_rate >= 0', name=op.f('ck_debts_rate_non_negative')),
    sa.CheckConstraint('balance >= 0', name=op.f('ck_debts_balance_non_negative')),
    sa.CheckConstraint('monthly_payment >= 0', name=op.f('ck_debts_payment_non_negative')),
    sa.CheckConstraint('payment_day BETWEEN 1 AND 31', name=op.f('ck_debts_payment_day_range')),
    sa.CheckConstraint('principal > 0', name=op.f('ck_debts_principal_positive')),
    sa.ForeignKeyConstraint(['bank_id'], ['banks.id'], name=op.f('fk_debts_bank_id_banks')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_debts_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_debts'))
    )
    op.create_index('ix_debts_user_active', 'debts', ['user_id', 'is_active'], unique=False)
    op.create_table('debt_payments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('debt_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('due_date', sa.Date(), nullable=False),
    sa.Column('amount', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('principal_part', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('interest_part', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('paid_at', sa.Date(), nullable=False),
    sa.Column('status', sa.Enum('paid', 'reversed', name='debt_payment_status', native_enum=False, create_constraint=True, length=16), nullable=False),
    sa.Column('transaction_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('amount > 0', name=op.f('ck_debt_payments_amount_positive')),
    sa.CheckConstraint('principal_part >= 0 AND interest_part >= 0', name=op.f('ck_debt_payments_parts_non_negative')),
    sa.ForeignKeyConstraint(['debt_id'], ['debts.id'], name=op.f('fk_debt_payments_debt_id_debts'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id'], name=op.f('fk_debt_payments_transaction_id_transactions'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_debt_payments_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_debt_payments')),
    sa.UniqueConstraint('transaction_id', name='uq_debt_payments_transaction_id')
    )
    op.create_index('ix_debt_payments_debt_due', 'debt_payments', ['debt_id', 'due_date'], unique=False)
    op.create_index('ix_debt_payments_user_paid', 'debt_payments', ['user_id', 'paid_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_debt_payments_user_paid', table_name='debt_payments')
    op.drop_index('ix_debt_payments_debt_due', table_name='debt_payments')
    op.drop_table('debt_payments')
    op.drop_index('ix_debts_user_active', table_name='debts')
    op.drop_table('debts')
