from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from phonenumbers import parse as parse_phone
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.admob import verify_google_ssv
from app.config import get_settings
from app.database import get_db
from app.models import (
    AdEvent, Notification, NotificationPreference, PaymentMethod, SupportMessage,
    SupportTicket, User, UserSession, Wallet, WalletTransaction, Withdrawal, now_utc,
)
from app.phones import normalize_phone
from app.schemas import (
    AdReservationOut, AdminWithdrawalUpdate, DashboardOut, NotificationOut, SessionStart,
    PaymentOut, PhoneIn, PreferencesIn, PreferencesOut, ProfileIn, ProfileOut, SessionOut,
    SupportIn, SupportMessageIn, SupportMessageOut, SupportStatusIn,
    SupportTicketOut, TransactionOut, WalletOut, WithdrawalIn, WithdrawalOut,
)
from app.security import (
    create_session, current_user, decrypt_payment_number, digest_token,
    encrypt_payment_number, require_admin,
)

settings = get_settings()
app = FastAPI(title="AdsEarn API", version="1.0.0", docs_url=None if settings.environment == "production" else "/docs")
if settings.origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
api = APIRouter(prefix="/v1")
AD_DAILY_LIMIT = 10
AD_RESERVATION_TTL_MINUTES = 15


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def _withdrawal_out(item: Withdrawal) -> WithdrawalOut:
    return WithdrawalOut(
        withdrawal_id=item.withdrawal_id,
        amount=item.amount,
        status=item.status,
        payment_method=item.payment_method_snapshot,
        payment_reference=item.payment_reference,
        created_at=item.created_at.isoformat(),
    )


def _notification(db: Session, user_id: int, category: str, title: str, body: str) -> None:
    preference = db.get(NotificationPreference, user_id)
    if preference is None or getattr(preference, category, False):
        db.add(Notification(user_id=user_id, category=category, title=title, body=body))


def _support_ticket_out(db: Session, ticket: SupportTicket) -> SupportTicketOut:
    messages = db.scalars(
        select(SupportMessage).where(SupportMessage.ticket_id == ticket.id)
        .order_by(SupportMessage.created_at.asc())
    ).all()
    return SupportTicketOut(
        ticket_id=ticket.ticket_id,
        category=ticket.category,
        description=ticket.description,
        status=ticket.status,
        created_at=ticket.created_at.isoformat(),
        messages=[
            SupportMessageOut(sender=item.sender_role, body=item.body, created_at=item.created_at.isoformat())
            for item in messages
        ],
    )


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@api.post("/session", response_model=SessionOut)
def start_session(payload: SessionStart, db: Session = Depends(get_db)) -> SessionOut:
    user, token = create_session(db, payload.device_fingerprint)
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    wallet = db.get(Wallet, user.id)
    preferences = db.get(NotificationPreference, user.id)
    if wallet is None:
        db.add(Wallet(user_id=user.id))
    if preferences is None:
        db.add(NotificationPreference(user_id=user.id))
    db.commit()
    return SessionOut(access_token=token, user_id=user.public_id)


@api.post("/session/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> None:
    from fastapi.security.utils import get_authorization_scheme_param

    scheme, token = get_authorization_scheme_param(request.headers.get("Authorization", ""))
    if scheme.lower() == "bearer" and token:
        session = db.scalar(select(UserSession).where(UserSession.token_hash == digest_token(token), UserSession.user_id == user.id))
        if session is not None:
            session.revoked_at = now_utc()
            db.commit()


@api.get("/profile", response_model=ProfileOut)
def get_profile(user: User = Depends(current_user)) -> ProfileOut:
    country_code = None
    if user.phone_e164:
        parsed = parse_phone(user.phone_e164, None)
        country_code = f"+{parsed.country_code}"
    return ProfileOut(
        full_name=user.full_name,
        email=user.email,
        phone=user.phone_e164,
        country_iso=user.country_iso,
        country_code=country_code,
        user_id=user.public_id,
    )


@api.put("/profile", response_model=ProfileOut)
def save_profile(payload: ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> ProfileOut:
    region = payload.country_iso.upper()
    e164, country_code = normalize_phone(region, payload.phone)
    user.full_name = payload.full_name.strip()
    user.email = str(payload.email).strip().casefold()
    user.country_iso = region
    user.phone_e164 = e164
    db.commit()
    return ProfileOut(
        full_name=user.full_name, email=user.email, phone=e164,
        country_iso=region, country_code=country_code, user_id=user.public_id,
    )


@api.get("/dashboard", response_model=DashboardOut)
def dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)) -> DashboardOut:
    today = datetime.now(timezone.utc).date()
    count = db.scalar(select(func.count(AdEvent.id)).where(
        AdEvent.user_id == user.id, AdEvent.calendar_day == today, AdEvent.status == "completed"
    )) or 0
    wallet = db.get(Wallet, user.id)
    return DashboardOut(
        user_name=user.full_name,
        user_id=user.public_id,
        daily_ads=count,
        available_balance=wallet.available_balance if wallet else Decimal("0.00"),
        currency=wallet.currency if wallet else "USD",
    )


@api.post("/ads/reservations", response_model=AdReservationOut, status_code=status.HTTP_201_CREATED)
def reserve_ad(user: User = Depends(current_user), db: Session = Depends(get_db)) -> AdReservationOut:
    if settings.environment == "production" and not settings.admob_ssv_verified:
        raise HTTPException(status_code=503, detail="Rewarded ads are not enabled until live SSV verification is complete")
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    today = datetime.now(timezone.utc).date()
    active_after = now_utc() - timedelta(minutes=AD_RESERVATION_TTL_MINUTES)
    db.query(AdEvent).filter(
        AdEvent.user_id == user.id, AdEvent.status == "reserved", AdEvent.created_at < active_after
    ).update({AdEvent.status: "expired"})
    active_reservation = db.scalar(select(AdEvent).where(
        AdEvent.user_id == user.id,
        AdEvent.calendar_day == today,
        AdEvent.status == "reserved",
    ).order_by(AdEvent.created_at.desc()).limit(1))
    if active_reservation is not None:
        completed = db.scalar(select(func.count(AdEvent.id)).where(
            AdEvent.user_id == user.id, AdEvent.calendar_day == today, AdEvent.status == "completed"
        )) or 0
        db.commit()
        return AdReservationOut(
            reservation_id=active_reservation.reservation_id,
            user_id=user.public_id,
            ad_unit_id=active_reservation.ad_unit_id,
            daily_count=completed,
        )
    used = db.scalar(select(func.count(AdEvent.id)).where(
        AdEvent.user_id == user.id, AdEvent.calendar_day == today,
        AdEvent.status.in_(("completed", "reserved")),
    )) or 0
    if used >= AD_DAILY_LIMIT:
        raise HTTPException(status_code=429, detail="You've reached today's limit. Come back tomorrow.")
    event = AdEvent(
        user_id=user.id,
        application_id=settings.admob_app_id,
        ad_unit_id=settings.admob_rewarded_unit_id,
        calendar_day=today,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    completed = db.scalar(select(func.count(AdEvent.id)).where(
        AdEvent.user_id == user.id, AdEvent.calendar_day == today, AdEvent.status == "completed"
    )) or 0
    return AdReservationOut(
        reservation_id=event.reservation_id,
        user_id=user.public_id,
        ad_unit_id=event.ad_unit_id,
        daily_count=completed,
    )


@api.delete("/ads/reservations/{reservation_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_ad_reservation(
    reservation_id: str, user: User = Depends(current_user), db: Session = Depends(get_db),
) -> None:
    event = db.scalar(select(AdEvent).where(
        AdEvent.reservation_id == reservation_id, AdEvent.user_id == user.id, AdEvent.status == "reserved",
    ))
    if event is not None:
        db.scalar(select(User).where(User.id == user.id).with_for_update())
        db.refresh(event)
        if event.status == "reserved":
            event.status = "expired"
            db.commit()


@api.get("/admob/ssv", status_code=status.HTTP_200_OK)
async def admob_ssv(request: Request, db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        raw_query = request.scope["query_string"].decode("ascii")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="Malformed SSV query") from exc
    params, event = verify_google_ssv(db, raw_query)
    if event.status == "completed" and event.transaction_id == params["transaction_id"]:
        return {"status": "verified"}
    event.status = "completed"
    event.transaction_id = params["transaction_id"]
    event.ssv_timestamp_ms = int(params["timestamp"])
    event.ssv_key_id = int(params["key_id"])
    event.ssv_signature = params["signature"]
    event.ad_network = params["ad_network"]
    event.reward_item = params.get("reward_item")
    event.reward_amount = int(params["reward_amount"]) if params.get("reward_amount", "").isdigit() else None
    event.calendar_day = datetime.fromtimestamp(event.ssv_timestamp_ms / 1000, timezone.utc).date()
    event.completed_at = now_utc()
    _notification(db, event.user_id, "daily_ads", "Ad completion verified", "A rewarded ad completion was verified.")
    db.commit()
    return {"status": "verified"}


@api.get("/wallet", response_model=WalletOut)
def get_wallet(user: User = Depends(current_user), db: Session = Depends(get_db)) -> WalletOut:
    wallet = db.get(Wallet, user.id)
    transactions = db.scalars(
        select(WalletTransaction).where(WalletTransaction.user_id == user.id)
        .order_by(WalletTransaction.created_at.desc()).limit(100)
    ).all()
    return WalletOut(
        available_balance=wallet.available_balance if wallet else Decimal("0.00"),
        currency=wallet.currency if wallet else "USD",
        transactions=[
            TransactionOut(
                transaction_id=item.transaction_id, transaction_type=item.transaction_type,
                amount=item.amount, status=item.status, created_at=item.created_at.isoformat(),
            ) for item in transactions
        ],
    )


@api.put("/payment-method", response_model=PaymentOut)
def save_payment_method(payload: PhoneIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> PaymentOut:
    e164, country_code = normalize_phone(payload.country_iso, payload.phone)
    existing = db.scalar(select(PaymentMethod).where(PaymentMethod.user_id == user.id))
    if existing is None:
        existing = PaymentMethod(
            user_id=user.id, country_iso=payload.country_iso.upper(),
            phone_e164_encrypted=encrypt_payment_number(e164), phone_last4=e164[-4:],
        )
        db.add(existing)
    else:
        existing.country_iso = payload.country_iso.upper()
        existing.phone_e164_encrypted = encrypt_payment_number(e164)
        existing.phone_last4 = e164[-4:]
    db.commit()
    return PaymentOut(country_iso=existing.country_iso, country_code=country_code, phone_last4=existing.phone_last4)


@api.get("/payment-method", response_model=PaymentOut | None)
def get_payment_method(user: User = Depends(current_user), db: Session = Depends(get_db)) -> PaymentOut | None:
    item = db.scalar(select(PaymentMethod).where(PaymentMethod.user_id == user.id))
    if item is None:
        return None
    import phonenumbers

    calling_code = phonenumbers.country_code_for_region(item.country_iso)
    country_code = f"+{calling_code}" if calling_code else ""
    return PaymentOut(country_iso=item.country_iso, country_code=country_code, phone_last4=item.phone_last4)


@api.post("/withdrawals", response_model=WithdrawalOut, status_code=status.HTTP_201_CREATED)
def request_withdrawal(payload: WithdrawalIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> WithdrawalOut:
    if payload.amount != _money(payload.amount):
        raise HTTPException(status_code=422, detail="Amount must use at most two decimal places")
    if payload.amount < settings.withdrawal_minimum:
        raise HTTPException(status_code=422, detail="Withdrawal amount is below the minimum")
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    existing = db.scalar(select(Withdrawal).where(
        Withdrawal.user_id == user.id,
        Withdrawal.request_key == str(payload.request_key),
    ))
    if existing is not None:
        if existing.amount != payload.amount:
            raise HTTPException(status_code=409, detail="This request key was already used for a different amount")
        return _withdrawal_out(existing)
    wallet = db.scalar(select(Wallet).where(Wallet.user_id == user.id).with_for_update())
    payment = db.scalar(select(PaymentMethod).where(PaymentMethod.user_id == user.id))
    if payment is None:
        raise HTTPException(status_code=409, detail="Save a WAAFI payment method before requesting a withdrawal")
    if wallet is None or wallet.available_balance < payload.amount:
        raise HTTPException(status_code=409, detail="Insufficient available balance")
    wallet.available_balance -= payload.amount
    wallet.updated_at = now_utc()
    withdrawal = Withdrawal(
        user_id=user.id, amount=payload.amount,
        request_key=str(payload.request_key),
        payment_method_snapshot=f"WAAFI •••• {payment.phone_last4}",
        payment_country_iso=payment.country_iso,
        payment_destination_encrypted=payment.phone_e164_encrypted,
    )
    db.add(withdrawal)
    db.flush()
    db.add(WalletTransaction(
        user_id=user.id, transaction_type="withdrawal", amount=-payload.amount,
        status="PENDING", reference=withdrawal.withdrawal_id,
    ))
    _notification(db, user.id, "withdrawals", "Withdrawal submitted", "Your withdrawal request is pending review.")
    db.commit()
    db.refresh(withdrawal)
    return _withdrawal_out(withdrawal)


@api.get("/withdrawals", response_model=list[WithdrawalOut])
def withdrawal_history(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[WithdrawalOut]:
    items = db.scalars(select(Withdrawal).where(Withdrawal.user_id == user.id).order_by(Withdrawal.created_at.desc())).all()
    return [_withdrawal_out(item) for item in items]


@api.post("/support", status_code=status.HTTP_201_CREATED)
def create_support_ticket(payload: SupportIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, str]:
    ticket = SupportTicket(
        ticket_id=f"TKT-{now_utc():%Y%m%d}-{uuid4().hex[:8].upper()}",
        user_id=user.id, category=payload.category, description=payload.description.strip(),
    )
    db.add(ticket)
    _notification(db, user.id, "support", "Support ticket created", "Your support ticket has been created successfully.")
    db.commit()
    db.refresh(ticket)
    return {"ticket_id": ticket.ticket_id, "status": ticket.status}


@api.get("/support/tickets", response_model=list[SupportTicketOut])
def user_support_tickets(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[SupportTicketOut]:
    tickets = db.scalars(
        select(SupportTicket).where(SupportTicket.user_id == user.id)
        .order_by(SupportTicket.created_at.desc()).limit(100)
    ).all()
    return [_support_ticket_out(db, ticket) for ticket in tickets]


@api.post("/support/tickets/{ticket_id}/messages", status_code=status.HTTP_201_CREATED)
def add_user_support_message(
    ticket_id: str, payload: SupportMessageIn,
    user: User = Depends(current_user), db: Session = Depends(get_db),
) -> dict[str, str]:
    ticket = db.scalar(select(SupportTicket).where(
        SupportTicket.ticket_id == ticket_id, SupportTicket.user_id == user.id,
    ).with_for_update())
    if ticket is None:
        raise HTTPException(status_code=404, detail="Support ticket not found")
    if ticket.status in {"RESOLVED", "CLOSED"}:
        raise HTTPException(status_code=409, detail="This support ticket is closed")
    db.add(SupportMessage(ticket_id=ticket.id, sender_role="user", body=payload.body))
    if ticket.status == "WAITING FOR USER":
        ticket.status = "IN REVIEW"
    db.commit()
    return {"ticket_id": ticket.ticket_id, "status": ticket.status}


@api.get("/admin/support/tickets", response_model=list[SupportTicketOut])
def admin_support_tickets(
    status_filter: str = "OPEN",
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[SupportTicketOut]:
    allowed_statuses = {"OPEN", "IN REVIEW", "WAITING FOR USER", "RESOLVED", "CLOSED"}
    normalized_status = status_filter.upper()
    if normalized_status not in allowed_statuses:
        raise HTTPException(status_code=422, detail="Unsupported support ticket status")
    tickets = db.scalars(
        select(SupportTicket).where(SupportTicket.status == normalized_status)
        .order_by(SupportTicket.created_at.asc()).limit(500)
    ).all()
    return [_support_ticket_out(db, ticket) for ticket in tickets]


@api.post("/admin/support/tickets/{ticket_id}/messages", status_code=status.HTTP_201_CREATED)
def add_admin_support_message(
    ticket_id: str, payload: SupportMessageIn,
    _admin: User = Depends(require_admin), db: Session = Depends(get_db),
) -> dict[str, str]:
    ticket = db.scalar(select(SupportTicket).where(
        SupportTicket.ticket_id == ticket_id,
    ).with_for_update())
    if ticket is None:
        raise HTTPException(status_code=404, detail="Support ticket not found")
    if ticket.status == "CLOSED":
        raise HTTPException(status_code=409, detail="This support ticket is closed")
    db.add(SupportMessage(ticket_id=ticket.id, sender_role="admin", body=payload.body))
    _notification(db, ticket.user_id, "support", "Support reply", "The AdsEarn support team replied to your ticket.")
    db.commit()
    return {"ticket_id": ticket.ticket_id, "status": ticket.status}


@api.put("/admin/support/tickets/{ticket_id}", response_model=SupportTicketOut)
def update_support_status(
    ticket_id: str, payload: SupportStatusIn,
    _admin: User = Depends(require_admin), db: Session = Depends(get_db),
) -> SupportTicketOut:
    ticket = db.scalar(select(SupportTicket).where(
        SupportTicket.ticket_id == ticket_id,
    ).with_for_update())
    if ticket is None:
        raise HTTPException(status_code=404, detail="Support ticket not found")
    transitions = {
        "OPEN": {"IN REVIEW", "WAITING FOR USER", "RESOLVED", "CLOSED"},
        "IN REVIEW": {"WAITING FOR USER", "RESOLVED", "CLOSED"},
        "WAITING FOR USER": {"IN REVIEW", "RESOLVED", "CLOSED"},
        "RESOLVED": {"IN REVIEW", "CLOSED"},
        "CLOSED": set(),
    }
    if payload.status not in transitions[ticket.status]:
        raise HTTPException(status_code=409, detail="Invalid support ticket status transition")
    ticket.status = payload.status
    if payload.status in {"RESOLVED", "CLOSED", "WAITING FOR USER"}:
        _notification(
            db, ticket.user_id, "support",
            "Support ticket updated",
            f"Your support ticket is now {payload.status.lower()}.",
        )
    db.commit()
    db.refresh(ticket)
    return _support_ticket_out(db, ticket)


@api.get("/notifications", response_model=list[NotificationOut])
def get_notifications(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[NotificationOut]:
    items = db.scalars(
        select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(100)
    ).all()
    return [
        NotificationOut(
            notification_id=item.notification_id, category=item.category, title=item.title,
            body=item.body, read=item.read, created_at=item.created_at.isoformat(),
        ) for item in items
    ]


@api.get("/notification-preferences", response_model=PreferencesOut)
def get_preferences(user: User = Depends(current_user), db: Session = Depends(get_db)) -> PreferencesOut:
    prefs = db.get(NotificationPreference, user.id)
    if prefs is None:
        prefs = NotificationPreference(user_id=user.id)
        db.add(prefs)
        db.commit()
    return PreferencesOut(
        daily_ads=prefs.daily_ads, withdrawals=prefs.withdrawals,
        support=prefs.support, account=prefs.account,
    )


@api.put("/notification-preferences", response_model=PreferencesOut)
def set_preferences(payload: PreferencesIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> PreferencesOut:
    prefs = db.get(NotificationPreference, user.id)
    if prefs is None:
        prefs = NotificationPreference(user_id=user.id)
        db.add(prefs)
    prefs.daily_ads = payload.daily_ads
    prefs.withdrawals = payload.withdrawals
    prefs.support = payload.support
    prefs.account = payload.account
    db.commit()
    return PreferencesOut.model_validate(payload.model_dump())


@api.put("/admin/withdrawals/{withdrawal_id}", response_model=WithdrawalOut)
def update_withdrawal(
    withdrawal_id: str, payload: AdminWithdrawalUpdate,
    _admin: User = Depends(require_admin), db: Session = Depends(get_db),
) -> WithdrawalOut:
    item = db.scalar(select(Withdrawal).where(Withdrawal.withdrawal_id == withdrawal_id).with_for_update())
    if item is None:
        raise HTTPException(status_code=404, detail="Withdrawal not found")
    allowed = {"PENDING": {"APPROVED", "REJECTED"}, "APPROVED": {"PAID"}, "PAID": set(), "REJECTED": set()}
    if payload.status not in allowed[item.status]:
        raise HTTPException(status_code=409, detail="Invalid withdrawal status transition")
    if payload.status == "PAID" and not (payload.payment_reference and payload.payment_reference.strip()):
        raise HTTPException(status_code=422, detail="An actual payment reference is required to mark a withdrawal paid")
    if payload.status != "PAID" and payload.payment_reference:
        raise HTTPException(status_code=422, detail="A payment reference is accepted only after payment")
    item.status = payload.status
    if payload.status == "PAID":
        item.payment_reference = payload.payment_reference.strip()
    ledger_entry = db.scalar(select(WalletTransaction).where(
        WalletTransaction.user_id == item.user_id,
        WalletTransaction.reference == item.withdrawal_id,
        WalletTransaction.transaction_type == "withdrawal",
    ))
    if ledger_entry is not None:
        ledger_entry.status = payload.status
    if payload.status == "REJECTED":
        wallet = db.scalar(select(Wallet).where(Wallet.user_id == item.user_id).with_for_update())
        if wallet is None:
            raise HTTPException(status_code=409, detail="Wallet record is unavailable")
        wallet.available_balance += item.amount
        wallet.updated_at = now_utc()
        db.add(WalletTransaction(
            user_id=item.user_id, transaction_type="withdrawal_reversal", amount=item.amount,
            status="COMPLETED", reference=item.withdrawal_id,
        ))
    _notification(
        db, item.user_id, "withdrawals",
        f"Withdrawal {payload.status.lower()}",
        "Your withdrawal status has been updated by the review team.",
    )
    db.commit()
    db.refresh(item)
    return _withdrawal_out(item)


@api.get("/admin/withdrawals/{withdrawal_id}/payment-destination")
def get_withdrawal_destination(
    withdrawal_id: str, _admin: User = Depends(require_admin), db: Session = Depends(get_db),
) -> dict[str, str]:
    item = db.scalar(select(Withdrawal).where(Withdrawal.withdrawal_id == withdrawal_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Withdrawal not found")
    return {
        "country_iso": item.payment_country_iso,
        "waafi_phone": decrypt_payment_number(item.payment_destination_encrypted),
    }


@api.get("/admin/withdrawals", response_model=list[WithdrawalOut])
def admin_withdrawal_queue(
    status_filter: str = "PENDING",
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[WithdrawalOut]:
    normalized_status = status_filter.upper()
    if normalized_status not in {"PENDING", "APPROVED", "PAID", "REJECTED"}:
        raise HTTPException(status_code=422, detail="Unsupported withdrawal status")
    items = db.scalars(
        select(Withdrawal).where(Withdrawal.status == normalized_status)
        .order_by(Withdrawal.created_at.asc()).limit(500)
    ).all()
    return [_withdrawal_out(item) for item in items]


app.include_router(api)
