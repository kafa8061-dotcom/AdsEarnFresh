import base64
import binascii
from functools import lru_cache
from decimal import Decimal
from ipaddress import ip_address
from urllib.parse import parse_qsl, urlparse

from cryptography.fernet import Fernet
from pydantic import Field
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
    allowed_hosts: str = ""
    forwarded_allow_ips: str = "127.0.0.1"
    db_connect_timeout_seconds: int = Field(default=5, gt=0, le=60)
    db_pool_size: int = Field(default=5, gt=0, le=50)
    db_max_overflow: int = Field(default=5, ge=0, le=100)
    db_pool_timeout_seconds: int = Field(default=30, gt=0, le=300)
    db_pool_recycle_seconds: int = Field(default=1800, gt=0, le=86400)
    admob_ssv_verified: bool = False
    admob_app_id: str = "ca-app-pub-4973946737213196~3854510671"
    admob_rewarded_unit_id: str = "2667340525"
    admob_ssv_key_url: str = "https://www.gstatic.com/admob/reward/verifier-keys.json"
    play_integrity_cloud_project_number: int = 0
    play_integrity_package_name: str = "com.adsearn.mobile"
    play_integrity_certificate_sha256: str = ""
    anonymous_sessions_enabled: bool = False
    edge_rate_limiting_configured: bool = False
    wallet_funding_enabled: bool = False
    reward_policy_id: str = ""
    withdrawals_enabled: bool = False
    session_ttl_days: int = 30
    withdrawal_minimum: Decimal = Decimal("0.00")

    @property
    def admins(self) -> set[str]:
        return {email.strip().casefold() for email in self.admin_emails.split(",") if email.strip()}

    @property
    def origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def hosts(self) -> list[str]:
        return [host.strip() for host in self.allowed_hosts.split(",") if host.strip()]

    @property
    def trusted_proxies(self) -> list[str]:
        return [proxy.strip() for proxy in self.forwarded_allow_ips.split(",") if proxy.strip()]

    @property
    def play_integrity_certificate_digests(self) -> set[str]:
        return {
            value.strip()
            for value in self.play_integrity_certificate_sha256.split(",")
            if value.strip()
        }

    def validate_deployment(self) -> None:
        if self.environment.lower() == "production":
            if (
                not self.database_url.startswith(("postgres://", "postgresql://", "postgresql+psycopg://"))
                or self._is_placeholder(self.database_url)
            ):
                raise ValueError("Production requires persistent PostgreSQL")
            database_url = self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
            database_host = (urlparse(database_url).hostname or "").casefold().rstrip(".")
            if not database_host or database_host == "localhost" or database_host.endswith(".localhost"):
                raise ValueError("Production PostgreSQL must use a remote persistent database host")
            ssl_modes = [
                value for name, value in parse_qsl(urlparse(database_url).query, keep_blank_values=True)
                if name.casefold() == "sslmode"
            ]
            if ssl_modes != ["verify-full"]:
                raise ValueError("Production PostgreSQL requires sslmode=verify-full")
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
                or self._is_placeholder(host)
                or not public_url.path.endswith("/")
                or public_url.query
                or public_url.fragment
                or public_url.username
                or public_url.password
            ):
                raise ValueError("Production requires the real HTTPS public API URL")
            if (
                len(self.session_hmac_secret) < 32
                or self.session_hmac_secret == "development-only-session-secret-change-before-production"
                or self._is_placeholder(self.session_hmac_secret)
            ):
                raise ValueError("SESSION_HMAC_SECRET must contain at least 32 characters")
            if (
                len(self.device_binding_secret) < 32
                or self.device_binding_secret == "development-only-device-binding-secret-change"
                or self._is_placeholder(self.device_binding_secret)
            ):
                raise ValueError("DEVICE_BINDING_SECRET must contain at least 32 characters")
            if not self.payment_encryption_key or self._is_placeholder(self.payment_encryption_key):
                raise ValueError("PAYMENT_ENCRYPTION_KEY is required in production")
            try:
                Fernet(self.payment_encryption_key.encode())
            except (TypeError, ValueError) as exc:
                raise ValueError("PAYMENT_ENCRYPTION_KEY must be a valid Fernet key") from exc
            if self.admob_app_id != "ca-app-pub-4973946737213196~3854510671":
                raise ValueError("Production AdMob App ID does not match the configured publisher app")
            if self.admob_rewarded_unit_id != "2667340525":
                raise ValueError("Production AdMob rewarded unit ID does not match the configured unit")
            if self.anonymous_sessions_enabled:
                if self.play_integrity_cloud_project_number <= 0:
                    raise ValueError("PLAY_INTEGRITY_CLOUD_PROJECT_NUMBER is required when anonymous sessions are enabled")
                if self.play_integrity_package_name != "com.adsearn.mobile":
                    raise ValueError("PLAY_INTEGRITY_PACKAGE_NAME does not match the production Android app")
                if not self.play_integrity_certificate_digests:
                    raise ValueError("PLAY_INTEGRITY_CERTIFICATE_SHA256 is required when anonymous sessions are enabled")
                for digest in self.play_integrity_certificate_digests:
                    try:
                        decoded = base64.b64decode(
                            digest + "=" * (-len(digest) % 4), altchars=b"-_", validate=True,
                        )
                    except (ValueError, binascii.Error) as exc:
                        raise ValueError("Play Integrity certificate digests must be base64-encoded SHA-256 values") from exc
                    if len(decoded) != 32:
                        raise ValueError("Play Integrity certificate digests must be base64-encoded SHA-256 values")
            if not self.hosts or any("*" in allowed for allowed in self.hosts):
                raise ValueError("ALLOWED_HOSTS must contain explicit production hostnames")
            if host not in {allowed.casefold().rstrip(".") for allowed in self.hosts}:
                raise ValueError("ALLOWED_HOSTS must include the PUBLIC_BASE_URL hostname")
            if not self.origins or any("*" in origin for origin in self.origins):
                raise ValueError("CORS_ORIGINS must contain explicit approved HTTPS origins")
            for origin in self.origins:
                parsed_origin = urlparse(origin)
                if (
                    parsed_origin.scheme != "https"
                    or not parsed_origin.hostname
                    or self._is_placeholder(parsed_origin.hostname)
                    or parsed_origin.path not in ("", "/")
                    or parsed_origin.query
                    or parsed_origin.fragment
                    or parsed_origin.username
                    or parsed_origin.password
                ):
                    raise ValueError("CORS_ORIGINS must contain exact HTTPS origins without paths or credentials")
            if not self.trusted_proxies or any("*" in proxy for proxy in self.trusted_proxies):
                raise ValueError("FORWARDED_ALLOW_IPS must identify explicit trusted HTTPS proxy addresses")
            if any(self._is_placeholder(proxy) for proxy in self.trusted_proxies):
                raise ValueError("FORWARDED_ALLOW_IPS must contain real trusted proxy addresses")
            if not self.admins or self._is_placeholder(self.admin_emails):
                raise ValueError("ADMIN_EMAILS must contain approved administrator addresses")
            if self.anonymous_sessions_enabled and not self.edge_rate_limiting_configured:
                raise ValueError("Edge rate limiting must be configured before anonymous sessions are enabled")
            if self.wallet_funding_enabled and (
                not self.reward_policy_id or self._is_placeholder(self.reward_policy_id)
            ):
                raise ValueError("A registered server-side reward policy is required before wallet funding is enabled")
            if self.withdrawals_enabled and not self.wallet_funding_enabled:
                raise ValueError("Withdrawals require an explicitly enabled wallet funding policy")

    @staticmethod
    def _is_placeholder(value: str) -> bool:
        normalized = value.strip().casefold()
        return normalized.startswith("<") or any(
            marker in normalized for marker in ("replace-with", "change-me", "placeholder", "your-")
        )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_deployment()
    return settings
