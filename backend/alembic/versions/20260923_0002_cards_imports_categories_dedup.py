"""cards, statement imports, user categories, transaction dedup

- cards, statement_imports (state machine журнала импорта);
- categories: user_id (NULL = системная), kind, уникальность
  lower(name) в пределах владельца и типа вместо глобального unique;
- transactions: card_id, import_id, merchant, currency, is_recurring,
  external_hash + UNIQUE(user_id, external_hash), индексы по периодам;
- budgets.category_id; профиль пользователя;
- денежные колонки Numeric(12,2) → Numeric(14,2);
- ON DELETE CASCADE от users ко всем пользовательским данным;
- seed: банки Kaspi/Halyk/Freedom и системные категории.

Downgrade lossy: пользовательские категории удаляются, операции без
категории переносятся в системную «Без категории».

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-23 18:18:29.767432

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


BANKS = ("Kaspi Bank", "Halyk Bank", "Freedom Bank")

SYSTEM_CATEGORIES = {
    "expense": (
        ("Продукты", "#16A34A", "cart"),
        ("Кафе и рестораны", "#F97316", "coffee"),
        ("Транспорт", "#0EA5E9", "bus"),
        ("Такси", "#FACC15", "car"),
        ("Коммунальные услуги", "#64748B", "home"),
        ("Связь и интернет", "#6366F1", "wifi"),
        ("Подписки", "#A855F7", "repeat"),
        ("Здоровье", "#EF4444", "heart"),
        ("Одежда", "#EC4899", "shirt"),
        ("Развлечения", "#F59E0B", "film"),
        ("Образование", "#14B8A6", "book"),
        ("Переводы", "#94A3B8", "send"),
        ("Погашение кредитов", "#DC2626", "credit-card"),
        ("Без категории", "#9CA3AF", "wallet"),
    ),
    "income": (
        ("Зарплата", "#22C55E", "briefcase"),
        ("Переводы", "#94A3B8", "send"),
        ("Кэшбэк", "#84CC16", "gift"),
        ("Проценты по вкладам", "#10B981", "percent"),
        ("Без категории", "#9CA3AF", "wallet"),
    ),
}


def _seed() -> None:
    conn = op.get_bind()
    for name in BANKS:
        conn.execute(
            sa.text("INSERT INTO banks (name) VALUES (:name) ON CONFLICT (name) DO NOTHING"),
            {"name": name},
        )
    for kind, items in SYSTEM_CATEGORIES.items():
        for name, color, icon in items:
            conn.execute(
                sa.text(
                    "INSERT INTO categories (name, kind, color, icon, user_id) "
                    "SELECT CAST(:name AS VARCHAR), CAST(:kind AS VARCHAR), "
                    "CAST(:color AS VARCHAR), CAST(:icon AS VARCHAR), NULL "
                    "WHERE NOT EXISTS (SELECT 1 FROM categories WHERE user_id IS NULL "
                    "AND lower(name) = lower(CAST(:name AS VARCHAR)) "
                    "AND kind = CAST(:kind AS VARCHAR))"
                ),
                {"name": name, "kind": kind, "color": color, "icon": icon},
            )


def upgrade() -> None:
    op.create_table('cards',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('bank_id', sa.Integer(), nullable=False),
    sa.Column('last4', sa.String(length=4), nullable=False),
    sa.Column('card_type', sa.Enum('debit', 'credit', name='card_type', native_enum=False, create_constraint=True, length=16), nullable=False),
    sa.Column('credit_limit', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('currency', sa.String(length=3), server_default='KZT', nullable=False),
    sa.Column('nickname', sa.String(length=100), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("last4 ~ '^[0-9]{4}$'", name=op.f('ck_cards_last4_digits')),
    sa.ForeignKeyConstraint(['bank_id'], ['banks.id'], name=op.f('fk_cards_bank_id_banks')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_cards_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_cards'))
    )
    op.create_index(op.f('ix_cards_user_id'), 'cards', ['user_id'], unique=False)
    op.create_table('statement_imports',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('bank_id', sa.Integer(), nullable=False),
    sa.Column('card_id', sa.Integer(), nullable=True),
    sa.Column('parser', sa.String(length=32), nullable=False),
    sa.Column('file_name', sa.String(length=255), nullable=False),
    sa.Column('file_sha256', sa.String(length=64), nullable=False),
    sa.Column('status', sa.Enum('pending', 'processing', 'completed', 'partial', 'failed', name='import_status', native_enum=False, create_constraint=True, length=16), nullable=False),
    sa.Column('rows_total', sa.Integer(), nullable=False),
    sa.Column('rows_imported', sa.Integer(), nullable=False),
    sa.Column('rows_skipped', sa.Integer(), nullable=False),
    sa.Column('rows_failed', sa.Integer(), nullable=False),
    sa.Column('errors', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['bank_id'], ['banks.id'], name=op.f('fk_statement_imports_bank_id_banks')),
    sa.ForeignKeyConstraint(['card_id'], ['cards.id'], name=op.f('fk_statement_imports_card_id_cards'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_statement_imports_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_statement_imports'))
    )
    op.create_index('ix_statement_imports_user_created', 'statement_imports', ['user_id', 'created_at'], unique=False)
    op.add_column('budgets', sa.Column('category_id', sa.Integer(), nullable=True))
    op.alter_column('budgets', 'monthly_limit',
               existing_type=sa.NUMERIC(precision=12, scale=2),
               type_=sa.Numeric(precision=14, scale=2),
               existing_nullable=False)
    op.alter_column('budgets', 'spent',
               existing_type=sa.NUMERIC(precision=12, scale=2),
               type_=sa.Numeric(precision=14, scale=2),
               existing_nullable=False)
    op.create_index(op.f('ix_budgets_user_id'), 'budgets', ['user_id'], unique=False)
    op.drop_constraint(op.f('fk_budgets_user_id_users'), 'budgets', type_='foreignkey')
    op.create_foreign_key(op.f('fk_budgets_category_id_categories'), 'budgets', 'categories', ['category_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(op.f('fk_budgets_user_id_users'), 'budgets', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.add_column('categories', sa.Column('user_id', sa.Integer(), nullable=True))
    op.add_column('categories', sa.Column('kind', sa.Enum('income', 'expense', name='category_kind', native_enum=False, create_constraint=True, length=16), server_default='expense', nullable=False))
    op.drop_constraint(op.f('uq_categories_name'), 'categories', type_='unique')
    op.create_index(op.f('ix_categories_user_id'), 'categories', ['user_id'], unique=False)
    op.create_index('uq_categories_system_name_kind', 'categories', [sa.literal_column('lower(name)'), 'kind'], unique=True, postgresql_where=sa.text('user_id IS NULL'))
    op.create_index('uq_categories_user_name_kind', 'categories', ['user_id', sa.literal_column('lower(name)'), 'kind'], unique=True, postgresql_where=sa.text('user_id IS NOT NULL'))
    op.create_foreign_key(op.f('fk_categories_user_id_users'), 'categories', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.alter_column('deposits', 'amount',
               existing_type=sa.NUMERIC(precision=12, scale=2),
               type_=sa.Numeric(precision=14, scale=2),
               existing_nullable=False)
    op.create_index(op.f('ix_deposits_user_id'), 'deposits', ['user_id'], unique=False)
    op.drop_constraint(op.f('fk_deposits_user_id_users'), 'deposits', type_='foreignkey')
    op.create_foreign_key(op.f('fk_deposits_user_id_users'), 'deposits', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.add_column('transactions', sa.Column('currency', sa.String(length=3), server_default='KZT', nullable=False))
    op.add_column('transactions', sa.Column('merchant', sa.String(length=255), nullable=True))
    op.add_column('transactions', sa.Column('card_id', sa.Integer(), nullable=True))
    op.add_column('transactions', sa.Column('import_id', sa.Integer(), nullable=True))
    op.add_column('transactions', sa.Column('external_hash', sa.String(length=64), nullable=True))
    op.add_column('transactions', sa.Column('is_recurring', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('transactions', sa.Column('category_source', sa.Enum('user', 'memory', 'rule', 'statement', 'default', name='category_source', native_enum=False, create_constraint=True, length=16), nullable=True))
    op.execute("UPDATE transactions SET category_source = 'user'")
    op.alter_column('transactions', 'amount',
               existing_type=sa.NUMERIC(precision=12, scale=2),
               type_=sa.Numeric(precision=14, scale=2),
               existing_nullable=False)
    op.alter_column('transactions', 'category_id',
               existing_type=sa.INTEGER(),
               nullable=True)
    op.create_index(op.f('ix_transactions_import_id'), 'transactions', ['import_id'], unique=False)
    op.create_index('ix_transactions_user_card_date', 'transactions', ['user_id', 'card_id', 'transaction_date'], unique=False)
    op.create_index('ix_transactions_user_category', 'transactions', ['user_id', 'category_id'], unique=False)
    op.create_index('ix_transactions_user_date', 'transactions', ['user_id', 'transaction_date'], unique=False)
    op.create_index('ix_transactions_user_merchant', 'transactions', ['user_id', 'merchant'], unique=False)
    op.create_unique_constraint('uq_transactions_user_external_hash', 'transactions', ['user_id', 'external_hash'])
    op.drop_constraint(op.f('fk_transactions_category_id_categories'), 'transactions', type_='foreignkey')
    op.drop_constraint(op.f('fk_transactions_user_id_users'), 'transactions', type_='foreignkey')
    op.create_foreign_key(op.f('fk_transactions_card_id_cards'), 'transactions', 'cards', ['card_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(op.f('fk_transactions_user_id_users'), 'transactions', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key(op.f('fk_transactions_category_id_categories'), 'transactions', 'categories', ['category_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(op.f('fk_transactions_import_id_statement_imports'), 'transactions', 'statement_imports', ['import_id'], ['id'], ondelete='SET NULL')
    op.add_column('users', sa.Column('monthly_income_declared', sa.Numeric(precision=14, scale=2), nullable=True))
    op.add_column('users', sa.Column('dependents', sa.Integer(), server_default='0', nullable=False))
    op.add_column('users', sa.Column('city', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('consent_at', sa.DateTime(timezone=True), nullable=True))

    _seed()


def downgrade() -> None:
    op.drop_column('users', 'consent_at')
    op.drop_column('users', 'city')
    op.drop_column('users', 'dependents')
    op.drop_column('users', 'monthly_income_declared')
    op.drop_constraint(op.f('fk_transactions_import_id_statement_imports'), 'transactions', type_='foreignkey')
    op.drop_constraint(op.f('fk_transactions_category_id_categories'), 'transactions', type_='foreignkey')
    op.drop_constraint(op.f('fk_transactions_user_id_users'), 'transactions', type_='foreignkey')
    op.drop_constraint(op.f('fk_transactions_card_id_cards'), 'transactions', type_='foreignkey')
    op.create_foreign_key(op.f('fk_transactions_user_id_users'), 'transactions', 'users', ['user_id'], ['id'])
    op.create_foreign_key(op.f('fk_transactions_category_id_categories'), 'transactions', 'categories', ['category_id'], ['id'])
    op.drop_constraint('uq_transactions_user_external_hash', 'transactions', type_='unique')
    op.drop_index('ix_transactions_user_date', table_name='transactions')
    op.drop_index('ix_transactions_user_merchant', table_name='transactions')
    op.drop_index('ix_transactions_user_category', table_name='transactions')
    op.drop_index('ix_transactions_user_card_date', table_name='transactions')
    op.drop_index(op.f('ix_transactions_import_id'), table_name='transactions')
    op.execute(
        "DELETE FROM categories WHERE user_id IS NOT NULL"
    )
    op.execute(
        "DELETE FROM categories c USING categories d "
        "WHERE c.user_id IS NULL AND d.user_id IS NULL "
        "AND lower(c.name) = lower(d.name) AND c.id > d.id"
    )
    op.execute(
        "UPDATE transactions SET category_id = ("
        "SELECT min(id) FROM categories WHERE name = 'Без категории') "
        "WHERE category_id IS NULL"
    )
    op.alter_column('transactions', 'category_id',
               existing_type=sa.INTEGER(),
               nullable=False)
    op.alter_column('transactions', 'amount',
               existing_type=sa.Numeric(precision=14, scale=2),
               type_=sa.NUMERIC(precision=12, scale=2),
               existing_nullable=False)
    op.drop_column('transactions', 'is_recurring')
    op.drop_column('transactions', 'category_source')
    op.drop_column('transactions', 'external_hash')
    op.drop_column('transactions', 'import_id')
    op.drop_column('transactions', 'card_id')
    op.drop_column('transactions', 'merchant')
    op.drop_column('transactions', 'currency')
    op.drop_constraint(op.f('fk_deposits_user_id_users'), 'deposits', type_='foreignkey')
    op.create_foreign_key(op.f('fk_deposits_user_id_users'), 'deposits', 'users', ['user_id'], ['id'])
    op.drop_index(op.f('ix_deposits_user_id'), table_name='deposits')
    op.alter_column('deposits', 'amount',
               existing_type=sa.Numeric(precision=14, scale=2),
               type_=sa.NUMERIC(precision=12, scale=2),
               existing_nullable=False)
    op.drop_constraint(op.f('fk_categories_user_id_users'), 'categories', type_='foreignkey')
    op.drop_index('uq_categories_user_name_kind', table_name='categories', postgresql_where=sa.text('user_id IS NOT NULL'))
    op.drop_index('uq_categories_system_name_kind', table_name='categories', postgresql_where=sa.text('user_id IS NULL'))
    op.drop_index(op.f('ix_categories_user_id'), table_name='categories')
    op.create_unique_constraint(op.f('uq_categories_name'), 'categories', ['name'], postgresql_nulls_not_distinct=False)
    op.drop_column('categories', 'kind')
    op.drop_column('categories', 'user_id')
    op.drop_constraint(op.f('fk_budgets_user_id_users'), 'budgets', type_='foreignkey')
    op.drop_constraint(op.f('fk_budgets_category_id_categories'), 'budgets', type_='foreignkey')
    op.create_foreign_key(op.f('fk_budgets_user_id_users'), 'budgets', 'users', ['user_id'], ['id'])
    op.drop_index(op.f('ix_budgets_user_id'), table_name='budgets')
    op.alter_column('budgets', 'spent',
               existing_type=sa.Numeric(precision=14, scale=2),
               type_=sa.NUMERIC(precision=12, scale=2),
               existing_nullable=False)
    op.alter_column('budgets', 'monthly_limit',
               existing_type=sa.Numeric(precision=14, scale=2),
               type_=sa.NUMERIC(precision=12, scale=2),
               existing_nullable=False)
    op.drop_column('budgets', 'category_id')
    op.drop_index('ix_statement_imports_user_created', table_name='statement_imports')
    op.drop_table('statement_imports')
    op.drop_index(op.f('ix_cards_user_id'), table_name='cards')
    op.drop_table('cards')
