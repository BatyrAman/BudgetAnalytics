"""category kinds and bank reference seed

Additive only:
* ``categories.kind`` ('income' | 'expense' | 'any', default 'any'). Existing
  user categories become 'any', so no existing transaction or budget becomes
  invalid. Only **system** categories (user_id IS NULL) get a specific kind.
* Seeds the bank reference list. ``ON CONFLICT (name) DO NOTHING`` keeps banks
  that already exist (for example ones created by statement imports).

Downgrade removes only seeded banks that nothing references, then drops the
column.

Revision ID: a1c3e5f7b9d2
Revises: 574bc3f5dbfd
Create Date: 2026-11-18 17:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1c3e5f7b9d2"
down_revision: str | Sequence[str] | None = "574bc3f5dbfd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INCOME_SYSTEM_CATEGORIES = ("Зарплата", "Прочие доходы")
# Everything else seeded by bb94536e2d20 is a spending category, except these
# two, which stay 'any' (transfers and the import fallback).
ANY_SYSTEM_CATEGORIES = ("Переводы между своими счетами", "Без категории")

BANKS = (
    "Kaspi Bank",
    "Halyk Bank",
    "Freedom Bank",
    "Jusan Bank",
    "ForteBank",
    "Bank CenterCredit",
    "Home Credit Bank",
    "Eurasian Bank",
    "Bereke Bank",
    "Otbasy Bank",
    "Altyn Bank",
    "Nurbank",
    "Bank RBK",
    "Shinhan Bank Kazakhstan",
    "Другой банк",
)


def _in_list(values: Sequence[str]) -> str:
    return ", ".join("'" + v.replace("'", "''") + "'" for v in values)


def upgrade() -> None:
    op.add_column(
        "categories",
        sa.Column(
            "kind",
            sa.Enum(
                "income",
                "expense",
                "any",
                name="category_kind",
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            server_default="any",
            nullable=False,
        ),
    )
    income = _in_list(INCOME_SYSTEM_CATEGORIES)
    neutral = _in_list(ANY_SYSTEM_CATEGORIES)
    op.execute(
        f"UPDATE categories SET kind = 'income' WHERE user_id IS NULL AND name IN ({income})"  # noqa: S608 - constants
    )
    op.execute(
        "UPDATE categories SET kind = 'expense' WHERE user_id IS NULL "  # noqa: S608 - constants
        f"AND name NOT IN ({income}) AND name NOT IN ({neutral})"
    )

    values = ", ".join(f"({_in_list([b])}, now(), now())" for b in BANKS)
    op.execute(
        f"INSERT INTO banks (name, created_at, updated_at) VALUES {values} "  # noqa: S608 - constants
        "ON CONFLICT (name) DO NOTHING"
    )


def downgrade() -> None:
    op.execute(
        f"DELETE FROM banks b WHERE b.name IN ({_in_list(BANKS)}) "  # noqa: S608 - constants
        "AND NOT EXISTS (SELECT 1 FROM transactions t WHERE t.bank_id = b.id) "
        "AND NOT EXISTS (SELECT 1 FROM deposits d WHERE d.bank_id = b.id) "
        "AND NOT EXISTS (SELECT 1 FROM accounts a WHERE a.bank_id = b.id)"
    )
    op.drop_column("categories", "kind")
