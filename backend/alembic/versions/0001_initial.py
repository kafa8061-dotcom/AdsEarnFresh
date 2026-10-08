"""Initial AdsEarn identity, ledger, payout, and activity schema.

Revision ID: 0001_initial
"""
import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "google_ssv_keys",
        sa.Column("key_id", sa.Integer(), nullable=False),
        sa.Column("pem", sa.Text(), nullable=False),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key_id"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=16), nullable=False),
        sa.Column("device_binding", sa.String(length=64), nullable=True),
        sa.Column("device_public_key", sa.String(length=256), nullable=True),
        sa.Column("full_name", sa.String(length=160), nullable=True),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column("phone_e164", sa.String(length=16), nullable=True),
        sa.Column("country_iso", sa.String(length=2), nullable=True),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_device_binding", "users", ["device_binding"], unique=True)
    op.create_index("ix_users_email", "users", ["email"], unique=False)
    op.create_index("ix_users_public_id", "users", ["public_id"], unique=True)
    op.create_table(
        "device_challenges",
        sa.Column("challenge_id", sa.String(length=36), nullable=False),
        sa.Column("device_binding", sa.String(length=64), nullable=False),
        sa.Column("nonce", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("challenge_id"),
    )
    op.create_index("ix_device_challenges_device_binding", "device_challenges", ["device_binding"], unique=False)
    op.create_index("ix_device_challenges_expires_at", "device_challenges", ["expires_at"], unique=False)
    op.create_table(
        "ad_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reservation_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.String(length=64), nullable=False),
        sa.Column("ad_unit_id", sa.String(length=32), nullable=False),
        sa.Column("ad_network", sa.String(length=32), nullable=True),
        sa.Column("calendar_day", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("transaction_id", sa.String(length=160), nullable=True),
        sa.Column("ssv_timestamp_ms", sa.BigInteger(), nullable=True),
        sa.Column("ssv_key_id", sa.Integer(), nullable=True),
        sa.Column("ssv_signature", sa.String(length=512), nullable=True),
        sa.Column("reward_item", sa.String(length=128), nullable=True),
        sa.Column("reward_amount", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("transaction_id"),
    )
    op.create_index("ix_ad_events_calendar_day", "ad_events", ["calendar_day"], unique=False)
    op.create_index("ix_ad_events_reservation_id", "ad_events", ["reservation_id"], unique=True)
    op.create_index("ix_ad_events_user_id", "ad_events", ["user_id"], unique=False)
    op.create_index("ix_ad_user_day_status", "ad_events", ["user_id", "calendar_day", "status"], unique=False)
    op.create_table(
        "notification_preferences",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("daily_ads", sa.Boolean(), nullable=False),
        sa.Column("withdrawals", sa.Boolean(), nullable=False),
        sa.Column("support", sa.Boolean(), nullable=False),
        sa.Column("account", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("notification_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("body", sa.String(length=500), nullable=False),
        sa.Column("read", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("notification_id"),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"], unique=False)
    op.create_table(
        "payment_methods",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("country_iso", sa.String(length=2), nullable=False),
        sa.Column("phone_e164_encrypted", sa.Text(), nullable=False),
        sa.Column("phone_last4", sa.String(length=4), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payment_methods_user_id", "payment_methods", ["user_id"], unique=True)
    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"], unique=False)
    op.create_index("ix_sessions_token_hash", "sessions", ["token_hash"], unique=True)
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"], unique=False)
    op.create_table(
        "support_tickets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticket_id", sa.String(length=24), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_support_tickets_ticket_id", "support_tickets", ["ticket_id"], unique=True)
    op.create_index("ix_support_tickets_user_id", "support_tickets", ["user_id"], unique=False)
    op.create_table(
        "wallet_transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("transaction_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("transaction_type", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reference", sa.String(length=160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_wallet_transactions_transaction_id", "wallet_transactions", ["transaction_id"], unique=True)
    op.create_index("ix_wallet_transactions_user_id", "wallet_transactions", ["user_id"], unique=False)
    op.create_table(
        "wallets",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("available_balance", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "withdrawals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("withdrawal_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("request_key", sa.String(length=36), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("payment_method_snapshot", sa.String(length=64), nullable=False),
        sa.Column("payment_country_iso", sa.String(length=2), nullable=False),
        sa.Column("payment_destination_encrypted", sa.Text(), nullable=False),
        sa.Column("payment_reference", sa.String(length=160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_key"),
    )
    op.create_index("ix_withdrawals_user_id", "withdrawals", ["user_id"], unique=False)
    op.create_index("ix_withdrawals_withdrawal_id", "withdrawals", ["withdrawal_id"], unique=True)
    op.create_table(
        "support_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("sender_role", sa.String(length=16), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["ticket_id"], ["support_tickets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_support_messages_ticket_id", "support_messages", ["ticket_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_support_messages_ticket_id", table_name="support_messages")
    op.drop_table("support_messages")
    op.drop_index("ix_withdrawals_withdrawal_id", table_name="withdrawals")
    op.drop_index("ix_withdrawals_user_id", table_name="withdrawals")
    op.drop_table("withdrawals")
    op.drop_table("wallets")
    op.drop_index("ix_wallet_transactions_user_id", table_name="wallet_transactions")
    op.drop_index("ix_wallet_transactions_transaction_id", table_name="wallet_transactions")
    op.drop_table("wallet_transactions")
    op.drop_index("ix_support_tickets_user_id", table_name="support_tickets")
    op.drop_index("ix_support_tickets_ticket_id", table_name="support_tickets")
    op.drop_table("support_tickets")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_index("ix_sessions_token_hash", table_name="sessions")
    op.drop_index("ix_sessions_expires_at", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("ix_payment_methods_user_id", table_name="payment_methods")
    op.drop_table("payment_methods")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_table("notifications")
    op.drop_table("notification_preferences")
    op.drop_index("ix_ad_user_day_status", table_name="ad_events")
    op.drop_index("ix_ad_events_user_id", table_name="ad_events")
    op.drop_index("ix_ad_events_reservation_id", table_name="ad_events")
    op.drop_index("ix_ad_events_calendar_day", table_name="ad_events")
    op.drop_table("ad_events")
    op.drop_index("ix_users_public_id", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_device_binding", table_name="users")
    op.drop_table("users")
    op.drop_index("ix_device_challenges_expires_at", table_name="device_challenges")
    op.drop_index("ix_device_challenges_device_binding", table_name="device_challenges")
    op.drop_table("device_challenges")
    op.drop_table("google_ssv_keys")
