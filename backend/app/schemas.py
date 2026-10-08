from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class SessionOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str


class SessionStart(BaseModel):
    device_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class ProfileIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=160)
    email: EmailStr
    country_iso: str = Field(min_length=2, max_length=2)
    phone: str = Field(min_length=4, max_length=24)

    @field_validator("full_name")
    @classmethod
    def require_non_blank_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Full name is required")
        return normalized


class ProfileOut(BaseModel):
    full_name: str | None
    email: EmailStr | None
    phone: str | None
    country_iso: str | None
    country_code: str | None
    user_id: str


class PhoneIn(BaseModel):
    country_iso: str = Field(min_length=2, max_length=2)
    phone: str = Field(min_length=4, max_length=24)


class PaymentOut(BaseModel):
    country_iso: str
    country_code: str
    phone_last4: str


class AdReservationOut(BaseModel):
    reservation_id: str
    user_id: str
    ad_unit_id: str
    daily_count: int
    daily_limit: int = 10


class DashboardOut(BaseModel):
    user_name: str | None
    user_id: str
    daily_ads: int
    daily_limit: int = 10
    available_balance: Decimal
    currency: str = "USD"


class TransactionOut(BaseModel):
    transaction_id: str
    transaction_type: str
    amount: Decimal
    status: str
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class WalletOut(BaseModel):
    available_balance: Decimal
    currency: str
    transactions: list[TransactionOut]


class WithdrawalIn(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    request_key: UUID


class WithdrawalOut(BaseModel):
    withdrawal_id: str
    amount: Decimal
    status: str
    payment_method: str
    payment_reference: str | None
    created_at: str


class AdminWithdrawalUpdate(BaseModel):
    status: Literal["APPROVED", "REJECTED", "PAID"]
    payment_reference: str | None = Field(default=None, max_length=160)


class SupportIn(BaseModel):
    category: Literal["Withdrawal", "Payment Method", "Wallet", "Account", "Advertisements", "Technical Problem", "Other"]
    description: str = Field(min_length=10, max_length=4000)

    @field_validator("description")
    @classmethod
    def require_non_blank_description(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 10:
            raise ValueError("Description must contain at least 10 non-space characters")
        return normalized


class SupportMessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)

    @field_validator("body")
    @classmethod
    def require_non_blank_body(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Message is required")
        return normalized


class SupportStatusIn(BaseModel):
    status: Literal["IN REVIEW", "WAITING FOR USER", "RESOLVED", "CLOSED"]


class SupportMessageOut(BaseModel):
    sender: str
    body: str
    created_at: str


class SupportTicketOut(BaseModel):
    ticket_id: str
    category: str
    description: str
    status: str
    created_at: str
    messages: list[SupportMessageOut]


class PreferencesIn(BaseModel):
    daily_ads: bool
    withdrawals: bool
    support: bool
    account: bool


class PreferencesOut(PreferencesIn):
    pass


class NotificationOut(BaseModel):
    notification_id: str
    category: str
    title: str
    body: str
    read: bool
    created_at: str
