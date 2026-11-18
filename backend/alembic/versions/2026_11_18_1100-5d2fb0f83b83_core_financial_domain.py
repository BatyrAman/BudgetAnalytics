"""core financial domain

Revision ID: 5d2fb0f83b83
Revises: 86fba8eeb485
Create Date: 2026-11-18 11:00:08.455169

Adds currencies, accounts and financial goals; makes categories user-owned;
adds currency, constraints and indexes to money tables; makes
``transactions.transaction_date`` timezone-aware; extends transaction types.

DATA MIGRATION — read before applying to a database with real data:

* Categories: before this revision every category was global and shared by
  all users (audit finding C2). For every (user, category) pair used by that
  user's transactions a PRIVATE copy is created for the user and the
  transactions are re-pointed to it. The old global rows are then deleted —
  including categories no transaction references, because their creator is
  unknown and keeping them global would keep leaking their names. After the
  upgrade there are no system categories.
* ``transaction_date`` (naive TIMESTAMP) is interpreted as UTC and converted
  to TIMESTAMPTZ. All existing money rows get currency KZT.
* New CHECK constraints are validated against existing rows first; if
  violating rows exist the upgrade aborts with a clear message and changes
  nothing (fix or remove those rows manually, then retry).

Requires PostgreSQL >= 12 (ALTER TYPE ... ADD VALUE inside a transaction).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5d2fb0f83b83"
down_revision: str | Sequence[str] | None = "86fba8eeb485"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_TRANSACTION_TYPES = ("REFUND", "TRANSFER_IN", "TRANSFER_OUT")
ACCOUNT_TYPES = ("cash", "current", "card", "savings", "credit_card", "other")
CAPITALIZATION = ("none", "monthly", "quarterly", "annually")

CURRENCIES = [
    # code, name, symbol, minor_units (ISO 4217)
    ("KZT", "Казахстанский тенге", "₸", 2),
    ("USD", "Доллар США", "$", 2),
    ("EUR", "Евро", "€", 2),
    ("RUB", "Российский рубль", "₽", 2),
]


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def _abort_if_rows(count_sql: str, problem: str) -> None:
    """Abort (rolling back the whole migration) if ``count_sql`` returns > 0.

    Runs inside PostgreSQL as a DO block, so it works both online and in
    offline ``--sql`` mode (the generated script performs the same check).
    ``count_sql`` and ``problem`` are module constants, never user input.
    """

    message = (
        f"Migration 5d2fb0f83b83 aborted: % row(s) {problem}. "
        "Fix or remove them manually, then run the upgrade again."
    ).replace("'", "''")
    op.execute(
        "DO $$ DECLARE n bigint; BEGIN "
        f"{count_sql} INTO n; "
        f"IF n > 0 THEN RAISE EXCEPTION '{message}', n; END IF; "
        "END $$"
    )


def _in_list(values: Sequence[str]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    # ---------------------------------------------------------- pre-checks
    _abort_if_rows(
        "SELECT count(*) FROM transactions WHERE amount <= 0",
        "in transactions have amount <= 0",
    )
    _abort_if_rows(
        "SELECT count(*) FROM budgets WHERE monthly_limit <= 0 OR spent < 0",
        "in budgets have monthly_limit <= 0 or spent < 0",
    )
    _abort_if_rows(
        "SELECT count(*) FROM deposits WHERE amount <= 0 OR interest_rate < 0 "
        "OR interest_rate > 100 OR end_date <= start_date",
        "in deposits have a non-positive amount, a rate outside 0..100 or end_date <= start_date",
    )

    # ---------------------------------------------------------- currencies
    currencies = op.create_table(
        "currencies",
        sa.Column("code", sa.CHAR(3), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("symbol", sa.String(8), nullable=True),
        sa.Column("minor_units", sa.SmallInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_currencies")),
        sa.CheckConstraint("code ~ '^[A-Z]{3}$'", name=op.f("ck_currencies_code_iso4217")),
        sa.CheckConstraint("minor_units = 2", name=op.f("ck_currencies_minor_units_supported")),
    )
    op.bulk_insert(
        currencies,
        [{"code": c, "name": n, "symbol": s, "minor_units": m} for c, n, s, m in CURRENCIES],
    )

    # ---------------------------------------------------------- users
    op.add_column(
        "users",
        sa.Column("default_currency_code", sa.CHAR(3), server_default="KZT", nullable=False),
    )
    op.create_foreign_key(
        op.f("fk_users_default_currency_code_currencies"),
        "users",
        "currencies",
        ["default_currency_code"],
        ["code"],
    )

    # ---------------------------------------------------------- banks
    for column in _timestamps():
        op.add_column("banks", column)

    # ---------------------------------------------------------- categories
    for column in _timestamps():
        op.add_column("categories", column)
    op.add_column("categories", sa.Column("user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_categories_user_id_users"), "categories", "users", ["user_id"], ["id"]
    )
    op.drop_constraint("uq_categories_name", "categories", type_="unique")

    # Rows inserted with explicit ids (manual seeding, partial restores) leave
    # the id sequence behind; re-sync it before inserting the per-user copies.
    op.execute(
        "SELECT setval(pg_get_serial_sequence('categories', 'id'), "
        "COALESCE(MAX(id), 0) + 1, false) FROM categories"
    )
    op.execute(
        """
        INSERT INTO categories (user_id, name, color, icon)
        SELECT DISTINCT t.user_id, c.name, c.color, c.icon
        FROM transactions t
        JOIN categories c ON c.id = t.category_id
        WHERE c.user_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE transactions t
        SET category_id = own.id
        FROM categories legacy, categories own
        WHERE t.category_id = legacy.id
          AND legacy.user_id IS NULL
          AND own.user_id = t.user_id
          AND own.name = legacy.name
        """
    )
    op.execute("DELETE FROM categories WHERE user_id IS NULL")

    op.create_index(
        "uq_categories_user_id_name",
        "categories",
        ["user_id", "name"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    op.create_index(
        "uq_categories_system_name",
        "categories",
        ["name"],
        unique=True,
        postgresql_where=sa.text("user_id IS NULL"),
    )

    # ---------------------------------------------------------- accounts
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("bank_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("account_type", sa.String(20), nullable=False),
        sa.Column("currency_code", sa.CHAR(3), nullable=False),
        sa.Column("last4", sa.String(4), nullable=True),
        sa.Column("is_archived", sa.Boolean(), server_default="false", nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_accounts")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_accounts_user_id_users")),
        sa.ForeignKeyConstraint(["bank_id"], ["banks.id"], name=op.f("fk_accounts_bank_id_banks")),
        sa.ForeignKeyConstraint(
            ["currency_code"],
            ["currencies.code"],
            name=op.f("fk_accounts_currency_code_currencies"),
        ),
        sa.UniqueConstraint("user_id", "name", name="uq_accounts_user_id_name"),
        sa.UniqueConstraint("id", "user_id", name="uq_accounts_id_user_id"),
        sa.CheckConstraint(
            f"account_type IN ({_in_list(ACCOUNT_TYPES)})", name=op.f("ck_accounts_account_type")
        ),
        sa.CheckConstraint(
            "last4 IS NULL OR last4 ~ '^[0-9]{4}$'", name=op.f("ck_accounts_last4_digits")
        ),
        sa.CheckConstraint("length(btrim(name)) > 0", name=op.f("ck_accounts_name_not_blank")),
    )
    op.create_index("ix_accounts_user_id", "accounts", ["user_id"])

    # ---------------------------------------------------------- transactions
    for value in NEW_TRANSACTION_TYPES:
        op.execute(f"ALTER TYPE transactiontype ADD VALUE IF NOT EXISTS '{value}'")

    op.alter_column(
        "transactions",
        "amount",
        type_=sa.Numeric(18, 2),
        existing_type=sa.Numeric(12, 2),
        existing_nullable=False,
    )
    op.alter_column(
        "transactions",
        "transaction_date",
        type_=sa.DateTime(timezone=True),
        existing_type=sa.DateTime(),
        existing_nullable=False,
        postgresql_using="transaction_date AT TIME ZONE 'UTC'",
    )
    op.add_column(
        "transactions",
        sa.Column("currency_code", sa.CHAR(3), server_default="KZT", nullable=False),
    )
    op.add_column("transactions", sa.Column("account_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_transactions_currency_code_currencies"),
        "transactions",
        "currencies",
        ["currency_code"],
        ["code"],
    )
    op.create_foreign_key(
        "fk_transactions_account_id_user_id_accounts",
        "transactions",
        "accounts",
        ["account_id", "user_id"],
        ["id", "user_id"],
    )
    op.create_check_constraint(
        op.f("ck_transactions_amount_positive"), "transactions", "amount > 0"
    )
    op.create_index(
        "ix_transactions_user_id_transaction_date", "transactions", ["user_id", "transaction_date"]
    )
    op.create_index("ix_transactions_category_id", "transactions", ["category_id"])
    op.create_index("ix_transactions_account_id", "transactions", ["account_id"])
    op.create_index("ix_transactions_bank_id", "transactions", ["bank_id"])

    # ---------------------------------------------------------- budgets
    for column in ("monthly_limit", "spent"):
        op.alter_column(
            "budgets",
            column,
            type_=sa.Numeric(18, 2),
            existing_type=sa.Numeric(12, 2),
            existing_nullable=False,
        )
    op.add_column(
        "budgets", sa.Column("currency_code", sa.CHAR(3), server_default="KZT", nullable=False)
    )
    op.add_column("budgets", sa.Column("category_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_budgets_currency_code_currencies"),
        "budgets",
        "currencies",
        ["currency_code"],
        ["code"],
    )
    op.create_foreign_key(
        op.f("fk_budgets_category_id_categories"), "budgets", "categories", ["category_id"], ["id"]
    )
    op.create_check_constraint(
        op.f("ck_budgets_monthly_limit_positive"), "budgets", "monthly_limit > 0"
    )
    op.create_check_constraint(op.f("ck_budgets_spent_non_negative"), "budgets", "spent >= 0")
    op.create_index("ix_budgets_user_id", "budgets", ["user_id"])

    # ---------------------------------------------------------- deposits
    op.alter_column(
        "deposits",
        "amount",
        type_=sa.Numeric(18, 2),
        existing_type=sa.Numeric(12, 2),
        existing_nullable=False,
    )
    op.add_column(
        "deposits", sa.Column("currency_code", sa.CHAR(3), server_default="KZT", nullable=False)
    )
    op.add_column("deposits", sa.Column("effective_rate", sa.Numeric(7, 4), nullable=True))
    op.add_column(
        "deposits",
        sa.Column("capitalization", sa.String(20), server_default="none", nullable=False),
    )
    op.create_foreign_key(
        op.f("fk_deposits_currency_code_currencies"),
        "deposits",
        "currencies",
        ["currency_code"],
        ["code"],
    )
    op.create_check_constraint(
        op.f("ck_deposits_capitalization"),
        "deposits",
        f"capitalization IN ({_in_list(CAPITALIZATION)})",
    )
    op.create_check_constraint(op.f("ck_deposits_amount_positive"), "deposits", "amount > 0")
    op.create_check_constraint(
        op.f("ck_deposits_interest_rate_range"),
        "deposits",
        "interest_rate >= 0 AND interest_rate <= 100",
    )
    op.create_check_constraint(
        op.f("ck_deposits_effective_rate_range"),
        "deposits",
        "effective_rate IS NULL OR (effective_rate >= 0 AND effective_rate <= 1000)",
    )
    op.create_check_constraint(
        op.f("ck_deposits_term_positive"), "deposits", "end_date > start_date"
    )
    op.create_index("ix_deposits_user_id", "deposits", ["user_id"])

    # ---------------------------------------------------------- financial goals
    op.create_table(
        "financial_goals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("target_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("saved_amount", sa.Numeric(18, 2), server_default="0", nullable=False),
        sa.Column("currency_code", sa.CHAR(3), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_financial_goals")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_financial_goals_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["currency_code"],
            ["currencies.code"],
            name=op.f("fk_financial_goals_currency_code_currencies"),
        ),
        sa.UniqueConstraint("user_id", "name", name="uq_financial_goals_user_id_name"),
        sa.CheckConstraint(
            "target_amount > 0", name=op.f("ck_financial_goals_target_amount_positive")
        ),
        sa.CheckConstraint(
            "saved_amount >= 0", name=op.f("ck_financial_goals_saved_amount_non_negative")
        ),
        sa.CheckConstraint(
            "length(btrim(name)) > 0", name=op.f("ck_financial_goals_name_not_blank")
        ),
    )
    op.create_index("ix_financial_goals_user_id", "financial_goals", ["user_id"])


def downgrade() -> None:
    # Refuse to silently lose meaning: rows that the old schema cannot express.
    _abort_if_rows(
        "SELECT count(*) FROM transactions WHERE transaction_type::text IN "  # noqa: S608 - module constants only
        f"({_in_list(NEW_TRANSACTION_TYPES)})",
        "in transactions use refund/transfer types unknown to the previous schema",
    )
    for table in ("transactions", "budgets", "deposits"):
        _abort_if_rows(
            f"SELECT count(*) FROM {table} WHERE currency_code <> 'KZT'",  # noqa: S608
            f"in {table} are not in KZT (the previous schema has no currency)",
        )

    op.drop_index("ix_financial_goals_user_id", table_name="financial_goals")
    op.drop_table("financial_goals")

    # deposits
    op.drop_index("ix_deposits_user_id", table_name="deposits")
    for name in (
        "ck_deposits_term_positive",
        "ck_deposits_effective_rate_range",
        "ck_deposits_interest_rate_range",
        "ck_deposits_amount_positive",
        "ck_deposits_capitalization",
    ):
        op.drop_constraint(op.f(name), "deposits", type_="check")
    op.drop_constraint(op.f("fk_deposits_currency_code_currencies"), "deposits", type_="foreignkey")
    op.drop_column("deposits", "capitalization")
    op.drop_column("deposits", "effective_rate")
    op.drop_column("deposits", "currency_code")
    op.alter_column("deposits", "amount", type_=sa.Numeric(12, 2), existing_type=sa.Numeric(18, 2))

    # budgets
    op.drop_index("ix_budgets_user_id", table_name="budgets")
    op.drop_constraint(op.f("ck_budgets_spent_non_negative"), "budgets", type_="check")
    op.drop_constraint(op.f("ck_budgets_monthly_limit_positive"), "budgets", type_="check")
    op.drop_constraint(op.f("fk_budgets_category_id_categories"), "budgets", type_="foreignkey")
    op.drop_constraint(op.f("fk_budgets_currency_code_currencies"), "budgets", type_="foreignkey")
    op.drop_column("budgets", "category_id")
    op.drop_column("budgets", "currency_code")
    for column in ("spent", "monthly_limit"):
        op.alter_column("budgets", column, type_=sa.Numeric(12, 2), existing_type=sa.Numeric(18, 2))

    # transactions
    for index in (
        "ix_transactions_bank_id",
        "ix_transactions_account_id",
        "ix_transactions_category_id",
        "ix_transactions_user_id_transaction_date",
    ):
        op.drop_index(index, table_name="transactions")
    op.drop_constraint(op.f("ck_transactions_amount_positive"), "transactions", type_="check")
    op.drop_constraint(
        "fk_transactions_account_id_user_id_accounts", "transactions", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_transactions_currency_code_currencies"), "transactions", type_="foreignkey"
    )
    op.drop_column("transactions", "account_id")
    op.drop_column("transactions", "currency_code")
    op.alter_column(
        "transactions",
        "transaction_date",
        type_=sa.DateTime(),
        existing_type=sa.DateTime(timezone=True),
        postgresql_using="transaction_date AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "transactions", "amount", type_=sa.Numeric(12, 2), existing_type=sa.Numeric(18, 2)
    )
    # PostgreSQL cannot drop ENUM values: recreate the type with the old values.
    op.execute("ALTER TYPE transactiontype RENAME TO transactiontype_new")
    op.execute("CREATE TYPE transactiontype AS ENUM ('INCOME', 'EXPENSE')")
    op.execute(
        "ALTER TABLE transactions ALTER COLUMN transaction_type TYPE transactiontype "
        "USING transaction_type::text::transactiontype"
    )
    op.execute("DROP TYPE transactiontype_new")

    # accounts
    op.drop_index("ix_accounts_user_id", table_name="accounts")
    op.drop_table("accounts")

    # categories: back to one global category per name (merge per-user copies).
    op.drop_index("uq_categories_system_name", table_name="categories")
    op.drop_index("uq_categories_user_id_name", table_name="categories")
    op.execute(
        """
        UPDATE transactions t
        SET category_id = keep.id
        FROM categories c,
             (SELECT name, min(id) AS id FROM categories GROUP BY name) keep
        WHERE t.category_id = c.id AND c.name = keep.name AND c.id <> keep.id
        """
    )
    op.execute(
        """
        DELETE FROM categories c
        USING (SELECT name, min(id) AS id FROM categories GROUP BY name) keep
        WHERE c.name = keep.name AND c.id <> keep.id
        """
    )
    op.drop_constraint(op.f("fk_categories_user_id_users"), "categories", type_="foreignkey")
    op.drop_column("categories", "user_id")
    op.create_unique_constraint(op.f("uq_categories_name"), "categories", ["name"])
    op.drop_column("categories", "updated_at")
    op.drop_column("categories", "created_at")

    # banks
    op.drop_column("banks", "updated_at")
    op.drop_column("banks", "created_at")

    # users
    op.drop_constraint(
        op.f("fk_users_default_currency_code_currencies"), "users", type_="foreignkey"
    )
    op.drop_column("users", "default_currency_code")

    op.drop_table("currencies")
