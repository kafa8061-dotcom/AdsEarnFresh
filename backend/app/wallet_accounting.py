from decimal import Decimal
from typing import Protocol

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import AdEvent, Wallet, WalletTransaction, now_utc


class RewardPolicy(Protocol):
    def reward_for_verified_ad(self, event: AdEvent) -> Decimal: ...


REWARD_POLICIES: dict[str, RewardPolicy] = {}


def configured_reward_policy(settings: Settings) -> RewardPolicy | None:
    if not settings.wallet_funding_enabled or not settings.reward_policy_id:
        return None
    return REWARD_POLICIES.get(settings.reward_policy_id)


def post_wallet_entry(
    db: Session,
    *,
    user_id: int,
    amount_delta: Decimal,
    transaction_type: str,
    status: str,
    reference: str,
) -> WalletTransaction:
    if not isinstance(amount_delta, Decimal) or not amount_delta.is_finite():
        raise TypeError("Wallet movements must use finite Decimal values")
    if (
        amount_delta == 0
        or amount_delta.copy_abs() >= Decimal("10000000000000000")
        or amount_delta != amount_delta.quantize(Decimal("0.01"))
    ):
        raise ValueError("Wallet movements must be non-zero amounts with at most two decimal places")
    if not transaction_type or not reference:
        raise ValueError("Wallet movements require a type and auditable reference")

    wallet = db.scalar(select(Wallet).where(Wallet.user_id == user_id).with_for_update())
    if wallet is None:
        raise HTTPException(status_code=409, detail="Wallet record is unavailable")
    existing = db.scalar(select(WalletTransaction).where(
        WalletTransaction.user_id == user_id,
        WalletTransaction.transaction_type == transaction_type,
        WalletTransaction.reference == reference,
    ))
    if existing is not None:
        if existing.amount != amount_delta or existing.status != status:
            raise HTTPException(status_code=409, detail="Wallet movement reference conflicts with an existing entry")
        return existing

    new_balance = wallet.available_balance + amount_delta
    if new_balance < 0:
        raise HTTPException(status_code=409, detail="Insufficient available balance")
    wallet.available_balance = new_balance
    wallet.updated_at = now_utc()
    entry = WalletTransaction(
        user_id=user_id,
        transaction_type=transaction_type,
        amount=amount_delta,
        status=status,
        reference=reference,
    )
    db.add(entry)
    db.flush()
    return entry


def fund_verified_ad(db: Session, event: AdEvent, settings: Settings) -> WalletTransaction | None:
    policy = configured_reward_policy(settings)
    if policy is None:
        return None
    amount = policy.reward_for_verified_ad(event)
    if not isinstance(amount, Decimal) or not amount.is_finite() or amount <= 0:
        raise ValueError("Reward policies must return a positive finite Decimal amount")
    return post_wallet_entry(
        db,
        user_id=event.user_id,
        amount_delta=amount,
        transaction_type="reward_credit",
        status="COMPLETED",
        reference=event.transaction_id or "",
    )
