from functools import lru_cache
import base64
import binascii
from decimal import Decimal
from ipaddress import ip_address
from urllib.parse import urlparse

from cryptography.fernet import Fernet
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = "sqlite:///./adsearn-dev.db"
    session_hmac_secret: str = "development-only-session-secret-change-before-production"
    device_binding_secret: str = "development-only-device-binding-secret-change"
    payment_encryption_key: str = ""
    public_base_url: str = "https://example.invalid/"
    admin_emails: str = ""
    cors_origins: str = ""
    db_connect_timeout_seconds: int = 5
    admob_ssv_verified: bool = False
    admob_app_id: str = "ca-app-pub-4973946737213196~3854510671"
    admob_rewarded_unit_id: str = "2667340525"
    admob_ssv_key_url: str = "https://www.gstatic.com/admob/reward/verifier-keys.json"
    play_integrity_cloud_project_number: int = 0
    play_integrity_package_name: str = "com.adsearn.mobile"
    play_integrity_certificate_sha256: str = ""
    session_ttl_days: int = 30
    withdrawal_minimum: Decimal = Decimal("0.00")

    @field_validator("session_hmac_secret")
    @classmethod
    def production_secret_is_strong(cls, value: str) -> str:
        from os import environ

        if environ.get("ENVIRONMENT", "development").lower() == "production" and len(value) < 32:
            raise ValueError("SESSION_HMAC_SECRET must contain at least 32 characters")
        return value

    @property
    def admins(self) -> set[str]:
        return {email.strip().casefold() for email in self.admin_emails.split(",") if email.strip()}

    @property
    def origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def play_integrity_certificate_digests(self) -> set[str]:
        return {
            value.strip()
            for value in self.play_integrity_certificate_sha256.split(",")
            if value.strip()
        }

    def validate_deployment(self) -> None:
        if self.environment.lower() == "production":
            if not self.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
                raise ValueError("Production requires persistent PostgreSQL")
            database_host = (urlparse(self.database_url).hostname or "").casefold().rstrip(".")
            if not database_host or database_host == "localhost" or database_host.endswith(".localhost"):
                raise ValueError("Production PostgreSQL must use a remote persistent database host")
            try:
                database_address = ip_address(database_host)
            except ValueError:
                database_address = None
            if database_address is not None and database_address.is_loopback:
                raise ValueError("Production PostgreSQL must not use a loopback address")
            public_url = urlparse(self.public_base_url)
            host = (public_url.hostname or "").casefold().rstrip(".")
            local_host = (
                not host
                or host == "localhost"
                or host.endswith((".localhost", ".local", ".internal", ".invalid", ".test", ".example"))
                or host in {"example.com", "example.net", "example.org"}
                or any(host.endswith(f".{domain}") for domain in ("example.com", "example.net", "example.org"))
            )
            if host:
                try:
                    address = ip_address(host)
                    local_host = local_host or any((
                        address.is_private, address.is_loopback, address.is_link_local,
                        address.is_reserved, address.is_unspecified,
                    ))
                except ValueError:
                    pass
            if (
                public_url.scheme != "https"
                or local_host
                or not public_url.path.endswith("/")
                or public_url.query
                or public_url.fragment
                or public_url.username
                or public_url.password
            ):
                raise ValueError("Production requires the real HTTPS public API URL")
            if len(self.session_hmac_secret) < 32:
                raise ValueError("SESSION_HMAC_SECRET must contain at least 32 characters")
            if len(self.device_binding_secret) < 32:
                raise ValueError("DEVICE_BINDING_SECRET must contain at least 32 characters")
            if not self.payment_encryption_key:
                raise ValueError("PAYMENT_ENCRYPTION_KEY is required in production")
            try:
                Fernet(self.payment_encryption_key.encode())
            except (TypeError, ValueError) as exc:
                raise ValueError("PAYMENT_ENCRYPTION_KEY must be a valid Fernet key") from exc
            if self.admob_app_id != "ca-app-pub-4973946737213196~3854510671":
                raise ValueError("Production AdMob App ID does not match the configured publisher app")
            if self.admob_rewarded_unit_id != "2667340525":
                raise ValueError("Production AdMob rewarded unit ID does not match the configured unit")
            if self.play_integrity_cloud_project_number <= 0:
                raise ValueError("PLAY_INTEGRITY_CLOUD_PROJECT_NUMBER is required in production")
            if self.play_integrity_package_name != "com.adsearn.mobile":
                raise ValueError("PLAY_INTEGRITY_PACKAGE_NAME does not match the production Android app")
            if not self.play_integrity_certificate_digests:
                raise ValueError("PLAY_INTEGRITY_CERTIFICATE_SHA256 must include the production signing certificate")
            for digest in self.play_integrity_certificate_digests:
                try:
                    decoded = base64.b64decode(
                        digest + "=" * (-len(digest) % 4), altchars=b"-_", validate=True,
                    )
                except (ValueError, binascii.Error) as exc:
                    raise ValueError("Play Integrity certificate digests must be base64-encoded SHA-256 values") from exc
                if len(decoded) != 32:
                    raise ValueError("Play Integrity certificate digests must be base64-encoded SHA-256 values")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_deployment()
    return settings
