from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db
from app.core.errors import ErrorResponse
from app.models.user import User
from app.schemas.account import AccountCreate, AccountResponse, AccountUpdate
from app.services.accounts import AccountService, AccountWithBalance

router = APIRouter(prefix="/accounts", tags=["Accounts"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


def _response(item: AccountWithBalance) -> AccountResponse:
    fields = AccountResponse.model_fields.keys() - {"balance"}
    data = {name: getattr(item.account, name) for name in fields}
    return AccountResponse.model_validate({**data, "balance": item.balance})


@router.get("", response_model=list[AccountResponse], responses={401: _ERRORS[401]})
async def list_accounts(
    include_archived: bool = Query(default=False),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[AccountResponse]:
    items = await AccountService(db).list(current_user.id, include_archived)
    return [_response(i) for i in items]


@router.post(
    "", response_model=AccountResponse, status_code=status.HTTP_201_CREATED, responses=_ERRORS
)
async def create_account(
    payload: AccountCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> AccountResponse:
    """Account/card/cash metadata. Store at most the last 4 digits of a number;
    never send full card numbers, CVV, PIN or bank credentials."""

    item = await AccountService(db).create(payload, current_user)
    await db.commit()
    return _response(item)


@router.get("/{account_id}", response_model=AccountResponse, responses=_ERRORS)
async def get_account(
    account_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> AccountResponse:
    return _response(await AccountService(db).get(account_id, current_user.id))


@router.patch("/{account_id}", response_model=AccountResponse, responses=_ERRORS)
async def update_account(
    account_id: int,
    payload: AccountUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> AccountResponse:
    """Currency cannot be changed (linked transactions are in that currency)."""

    item = await AccountService(db).update(account_id, payload, current_user.id)
    await db.commit()
    return _response(item)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS)
async def delete_account(
    account_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Deletes an account without transactions (409 otherwise — archive it)."""

    await AccountService(db).delete(account_id, current_user.id)
    await db.commit()
