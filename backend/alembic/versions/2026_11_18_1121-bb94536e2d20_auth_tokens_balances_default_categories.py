"""auth tokens, account balances, default categories

Revision ID: bb94536e2d20
Revises: 5d2fb0f83b83
Create Date: 2026-11-18 11:21:00

* ``refresh_tokens`` (server-side rotation, logout, reuse detection) and
  ``users.token_version`` (instant invalidation of access tokens).
  Refresh tokens issued before this revision carry no ``jti`` and are no
  longer accepted: users sign in again once.
* ``accounts.opening_balance`` / ``opening_balance_at`` for computed balances.
* Transactions linked to an account must use the account's currency:
  the composite FK now also covers ``currency_code``.
* ``transactions.bank_id`` becomes optional (cash has no bank).
* Seeds read-only SYSTEM categories (``user_id IS NULL``). Existing private
  categories are untouched, even if a user has one with the same name.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "bb94536e2d20"
down_revision: str | Sequence[str] | None = "5d2fb0f83b83"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# name, color, icon
DEFAULT_CATEGORIES = [
    ("Продукты", "#22C55E", "shopping-cart"),
    ("Кафе и рестораны", "#F97316", "utensils"),
    ("Транспорт", "#3B82F6", "car"),
    ("Жильё и коммунальные услуги", "#8B5CF6", "home"),
    ("Связь и интернет", "#06B6D4", "wifi"),
    ("Здоровье", "#EF4444", "heart"),
    ("Одежда и обувь", "#EC4899", "shirt"),
    ("Образование", "#6366F1", "book"),
    ("Развлечения", "#EAB308", "film"),
    ("Подарки", "#F43F5E", "gift"),
    ("Платежи по кредитам", "#64748B", "credit-card"),
    ("Прочие расходы", "#94A3B8", "dots"),
    ("Зарплата", "#16A34A", "briefcase"),
    ("Прочие доходы", "#10B981", "plus"),
    ("Переводы между своими счетами", "#0EA5E9", "repeat"),
    ("Без категории", "#9CA3AF", "wallet"),
]


def _abort_if_rows(count_sql: str, problem: str) -> None:
    message = (
        f"Migration bb94536e2d20 aborted: % row(s) {problem}. "
        "Fix or remove them manually, then run the migration again."
    ).replace("'", "''")
    op.execute(
        "DO $$ DECLARE n bigint; BEGIN "
        f"{count_sql} INTO n; "
        f"IF n > 0 THEN RAISE EXCEPTION '{message}', n; END IF; "
        "END $$"
    )


def _in_list(values: Sequence[str]) -> str:
    return ", ".join("'" + v.replace("'", "''") + "'" for v in values)


def upgrade() -> None:
    # users
    op.add_column(
        "users", sa.Column("token_version", sa.Integer(), server_default="0", nullable=False)
    )

    # refresh tokens
    op.create_table(
        "refresh_tokens",
        sa.Column("jti", sa.String(36), nullable=False),
        sa.Column("family_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("jti", name=op.f("pk_refresh_tokens")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_refresh_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])

    # accounts
    op.add_column(
        "accounts",
        sa.Column("opening_balance", sa.Numeric(18, 2), server_default="0", nullable=False),
    )
    op.add_column(
        "accounts",
        sa.Column(
            "opening_balance_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_unique_constraint(
        "uq_accounts_id_user_id_currency_code", "accounts", ["id", "user_id", "currency_code"]
    )

    # transactions: account link must match currency; bank optional
    _abort_if_rows(
        "SELECT count(*) FROM transactions t JOIN accounts a ON a.id = t.account_id "
        "WHERE t.currency_code <> a.currency_code",
        "in transactions are linked to an account in a different currency",
    )
    op.drop_constraint(
        "fk_transactions_account_id_user_id_accounts", "transactions", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_transactions_account_user_currency_accounts",
        "transactions",
        "accounts",
        ["account_id", "user_id", "currency_code"],
        ["id", "user_id", "currency_code"],
    )
    op.alter_column("transactions", "bank_id", existing_type=sa.Integer(), nullable=True)

    # default (system) categories
    categories = sa.table(
        "categories",
        sa.column("user_id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("color", sa.String),
        sa.column("icon", sa.String),
    )
    op.bulk_insert(
        categories,
        [
            {"user_id": None, "name": name, "color": color, "icon": icon}
            for name, color, icon in DEFAULT_CATEGORIES
        ],
    )


def downgrade() -> None:
    _abort_if_rows(
        "SELECT count(*) FROM transactions WHERE bank_id IS NULL",
        "in transactions have no bank (the previous schema requires one)",
    )
    names = _in_list([name for name, _, _ in DEFAULT_CATEGORIES])
    # Keep seeded categories that are in use (the previous schema allows
    # system categories); delete the unused ones.
    op.execute(
        f"DELETE FROM categories c WHERE c.user_id IS NULL AND c.name IN ({names}) "  # noqa: S608 - constants
        "AND NOT EXISTS (SELECT 1 FROM transactions t WHERE t.category_id = c.id) "
        "AND NOT EXISTS (SELECT 1 FROM budgets b WHERE b.category_id = c.id)"
    )

    op.alter_column("transactions", "bank_id", existing_type=sa.Integer(), nullable=False)
    op.drop_constraint(
        "fk_transactions_account_user_currency_accounts", "transactions", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_transactions_account_id_user_id_accounts",
        "transactions",
        "accounts",
        ["account_id", "user_id"],
        ["id", "user_id"],
    )
    op.drop_constraint("uq_accounts_id_user_id_currency_code", "accounts", type_="unique")
    op.drop_column("accounts", "opening_balance_at")
    op.drop_column("accounts", "opening_balance")

    op.drop_index("ix_refresh_tokens_family_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")

    op.drop_column("users", "token_version")
