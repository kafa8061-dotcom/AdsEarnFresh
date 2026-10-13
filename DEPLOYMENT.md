# AdsEarn production preparation

This repository contains deployment preparation only. It does not identify a hosting provider or production domain, and nothing has been deployed. Do not use the sample values in `backend/.env.example` as live configuration.

## FastAPI Cloud deployment note

The API service must be deployed from the `backend/` directory so the host uses `backend/Dockerfile`, `backend/requirements.txt`, and the backend application package. The backend Docker image now uses Python 3.13 and installs `fastapi[standard]` so the FastAPI CLI is present in the runtime dependency set. A successful build alone does not make the API production-ready: the production environment still must pass the validation below, database migrations must be applied, and the readiness endpoint must return HTTP 200 before Android can use the API.

## Required owner-provisioned resources

- A production container runtime and private network ingress/load balancer that terminates TLS. Keep the backend reachable only from that ingress and trusted operational networks.
- A persistent, managed PostgreSQL database with durable storage, automated backups, point-in-time recovery where available, and TLS certificate verification.
- A real API domain and DNS records controlled by the owner, plus a valid HTTPS certificate.
- A secret manager or workload identity for database credentials, application secrets, and Google API authorization.
- Google Play Console and Cloud project access for Play Integrity, plus AdMob account access to configure and verify the server callback.

Select a region, availability/recovery objectives, backup retention, database capacity, and operational budget before provisioning. This project creates no resources and cannot claim backups or recovery have been configured.

## Backend configuration and operation

Build the image from `AdsEarnFresh/backend` using its Dockerfile. Run the application as a non-root user. The image starts Uvicorn workers only; it does not create tables or run migrations on application startup. Supply the environment through the hosting platform's secret/configuration mechanism, not a committed `.env`.

### Vercel deployment

For the repository's Vercel project, set the project Root Directory to the repository root (not `android/` or `backend/`). The root `pyproject.toml` explicitly points Vercel to `vercel_app:app`; `vercel_app.py` adds the existing `backend/` package directory to Python's module path and exports the existing FastAPI instance. The root `requirements.txt` installs the unchanged backend dependency list. Do not create a second API implementation or replace the Docker deployment.

Configure all required production environment variables from the hosting provider's secret/configuration manager before deploying. The application validates production settings at import/startup and intentionally fails closed if required values are missing or invalid. In particular, supply the real persistent PostgreSQL URL, stable secrets, API URL/hosts/CORS/proxy values, approved administrators, and Google settings as required by enabled features. Do not set session, AdMob SSV, funding, or withdrawal gates to enabled before their documented validations. Vercel deployment does not run Alembic automatically: run `alembic upgrade head` as a separate, reviewed operation against the production database before serving traffic. Use `/health/live` for process health and `/health/ready` for PostgreSQL/schema readiness.

Configure every production value in `backend/.env.example` with owner-controlled values. In particular:

- `DATABASE_URL` must point to persistent PostgreSQL using the installed psycopg 3 driver and `sslmode=verify-full`; configure the provider CA certificate if its driver configuration requires one.
- Generate independent, random `SESSION_HMAC_SECRET` and `DEVICE_BINDING_SECRET` values of at least 32 characters. Generate `PAYMENT_ENCRYPTION_KEY` with `cryptography.fernet.Fernet.generate_key()`. Keep all three stable and backed up securely: losing the payment key makes stored payout destinations unreadable.
- `JWT_SECRET` is documented as not applicable; the existing session tokens are opaque random bearer tokens, not JWTs. Do not treat that placeholder as a configured secret.
- Set exact `PUBLIC_BASE_URL`, `ALLOWED_HOSTS`, approved HTTPS `CORS_ORIGINS`, and `FORWARDED_ALLOW_IPS` values. Set trusted proxy IPs/CIDRs to the actual ingress only; never use `*`. The ingress must remove client-supplied forwarding headers before setting its own.
- Configure DB pool/timeout settings to fit the provider's connection limit and the selected worker count.
- Set `ADMIN_EMAILS` only to approved operators. Administrator role assignment must be performed through a controlled, audited operator process; the app has no self-service role elevation.
- The authentication token is a random opaque server session, not a JWT; configure `SESSION_HMAC_SECRET` rather than an unused `JWT_SECRET`.

The backend rejects production HTTP requests (except the non-sensitive container liveness probe), wildcard CORS, placeholder domains/secrets, untrusted hosts, non-PostgreSQL databases, and PostgreSQL URLs without certificate-verified TLS. Uvicorn trusts forwarded scheme/host information only from `FORWARDED_ALLOW_IPS`. Configure ingress rate limits for session challenges, session creation, profile/support endpoints, and other routes before enabling sessions. Rate limiting must be enforced at the shared ingress, not with a process-local counter. Do not log request query strings: the AdMob SSV callback carries a signature and event data. The container disables Uvicorn access logs; configure gateway logging to redact query strings and credentials.

## Migrations and data safety

Run migrations as a separate, one-off release step using the same built image and production environment, before routing traffic to a version that requires the schema:

```sh
alembic upgrade head
alembic current
alembic check
```

The current schema is a single initial Alembic revision and uses PostgreSQL-compatible integer keys, foreign keys, unique/index constraints, timezone-aware timestamps, `BIGINT` AdMob millisecond timestamps, and exact `NUMERIC(18, 2)` monetary values. The application does not call `create_all()` at startup. Review every future migration before applying it. The initial revision's `downgrade` drops the complete application schema; it is destructive and must not be used as a production rollback. Prefer a forward corrective migration. Take and verify a recoverable backup before any schema change.

Before launch, configure automated encrypted backups and a retention schedule that satisfies the owner's legal and business requirements. Record recovery objectives, restrict restore permissions, and perform a restore rehearsal in an isolated environment. Backups, retention, and restore capability are not configured by this project.

## Health and HTTPS

- `GET /health/live` is a dependency-free liveness probe for the container; it may be reached internally over HTTP.
- `GET /health` and `GET /health/ready` check PostgreSQL and compare its Alembic revision to the application's expected schema. They return a generic `503` readiness response if the database or required schema is unavailable/out of date.
- Public API and authenticated/session traffic must use HTTPS. TLS terminates at the real ingress, which must be the only public path to the container and must set trusted forwarded headers. HTTPS is not live until the owner configures domain, DNS, certificate, and ingress.

## AdMob, integrity, and wallet gates

- Keep `ADMOB_SSV_VERIFIED=false` until the HTTPS callback URL is configured in the AdMob console and a genuine signed Google callback has been validated.
- Keep `ANONYMOUS_SESSIONS_ENABLED=false` until Play Integrity is configured and validated against the actual production package/signing certificate, and shared edge rate limiting is active.
- Keep `WALLET_FUNDING_ENABLED=false` and `WITHDRAWALS_ENABLED=false` until a lawful, funded reward policy exists and has been reviewed. AdMob publisher revenue is paid to the app publisher; it is not a guaranteed per-view cash payment to each viewer. Never credit a wallet simply because an ad was displayed or completed.
- Do not claim that real ads, server-verified completions, user accounts, or withdrawals work until the relevant live test passes.

## Android network and ad diagnostics

The Android manifest includes INTERNET and ACCESS_NETWORK_STATE permissions. Development uses Google's official test ad IDs and is not the production build. Production uses the configured AdsEarn AdMob App ID and rewarded unit ID. If an ad fails to load, Android Logcat entries tagged `AdsEarnRewardedAd` report the Google SDK's load error code, domain, and message; that error distinguishes network/SDK/no-fill problems from a backend reservation failure. The Android API base URL is configured in the untracked `android/local.properties`, not in the repository, and must be a real HTTPS API root ending in `/`.

## Launch prerequisites

Read this guide before launch. Provision persistent PostgreSQL and an HTTPS API, set secrets through the host's secret manager, configure the AdMob SSV callback, live-test SSV before enabling it, provision Google Play Integrity for stronger device attestation, arrange reviewed/legitimate wallet funding rules before allowing withdrawals, and complete Play/legal/privacy release steps. Never commit environment files or signing keys.
