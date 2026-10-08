# AdsEarn production preparation

This repository contains deployment preparation only. It does not identify a hosting provider or production domain, and nothing has been deployed. Do not use the sample values in `backend/.env.example` as live configuration.

## Required owner-provisioned resources

- A production container runtime and private network ingress/load balancer that terminates TLS. Keep the backend reachable only from that ingress and trusted operational networks.
- A persistent, managed PostgreSQL database with durable storage, automated backups, point-in-time recovery where available, and TLS certificate verification.
- A real API domain and DNS records controlled by the owner, plus a valid HTTPS certificate.
- A secret manager or workload identity for database credentials, application secrets, and Google API authorization.
- Google Play Console and Cloud project access for Play Integrity, plus AdMob account access to configure and verify the server callback.

Select a region, availability/recovery objectives, backup retention, database capacity, and operational budget before provisioning. This project creates no resources and cannot claim backups or recovery have been configured.

## Backend configuration and operation

Build the image from `AdsEarnFresh/backend` using its Dockerfile. Run the application as a non-root user. The image starts Uvicorn workers only; it does not create tables or run migrations on application startup. Supply the environment through the hosting platform's secret/configuration mechanism, not a committed `.env`.

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

The AdMob callback is implemented at `GET /v1/admob/ssv`. Configure this exact HTTPS callback in AdMob only after the endpoint is reachable. Keep `ADMOB_SSV_VERIFIED=false` until a real Google callback has been successfully verified. The existing production rewarded App ID and unit ID remain configured in code; no live callback was tested here.

## Reward funding and withdrawals

AdMob publisher revenue and the SSV callback's network reward metadata are not AdsEarn wallet funds. A verified ad is activity only unless a reviewed server-side reward policy implementation is registered in `backend/app/wallet_accounting.py`. No policy is currently registered. Keep `WALLET_FUNDING_ENABLED=false`, `REWARD_POLICY_ID` unset, and `WITHDRAWALS_ENABLED=false`; a policy ID by itself cannot credit funds or pass the production withdrawal gate. When the business owner defines the funding source, eligibility, amount/currency, reversals, reconciliation, and approval controls, implement and review that backend policy, register it, and separately authorize the server-side feature flags. Android does not decide reward amounts. Every future wallet movement must go through `post_wallet_entry`, which requires an exact Decimal amount, a ledger type and reference, locks the wallet, prevents negative balances, and records the movement in the same database transaction.

## Google Play Integrity and sessions

In Play Console, link the production app to the intended Cloud project and obtain the Play App Signing certificate digest. In Google Cloud, enable Play Integrity API access and grant the backend runtime identity permission to decode tokens. Use host workload identity or securely mounted Application Default Credentials; never put service-account credentials in the image, repository, Android app, or logs.

Set `PLAY_INTEGRITY_CLOUD_PROJECT_NUMBER`, `PLAY_INTEGRITY_PACKAGE_NAME`, and `PLAY_INTEGRITY_CERTIFICATE_SHA256` from the real project and Play signing configuration. The certificate digest must match Google's decoded verdict. Production anonymous-session issuance has a separate `ANONYMOUS_SESSIONS_ENABLED=false` gate. Keep it false until the Cloud/Play configuration works with real Play-installed tokens and backend verification succeeds. Set `EDGE_RATE_LIMITING_CONFIGURED=true` only after shared ingress rate limits have actually been deployed and reviewed; otherwise production configuration rejects enabling sessions. Missing or rejected attestation continues to fail closed.

## Android production API

Do not build a production variant until a real HTTPS API URL and positive Play Integrity Cloud project number are available. Configure them in the ignored `android/local.properties` file:

```properties
API_BASE_URL=https://<real-production-api-domain>/
PLAY_INTEGRITY_CLOUD_PROJECT_NUMBER=<real-cloud-project-number>
```

The Gradle production-variant guard rejects missing, non-HTTPS, or local API URLs. Development variants and test AdMob IDs remain separate. Never use the development API or test AdMob IDs in a production release.

## External approvals and launch blockers

Owner-controlled steps include cloud/vendor account and billing approval, domain/DNS and TLS control, Play Console linking and signing-certificate access, Cloud API/IAM approval, AdMob callback configuration/live validation, administrator approval, rate-limit policy, privacy/legal review, and the wallet reward/funding business policy. The wallet remains zero-funded and ad completions do not create user funds until a legitimate policy and funding source are defined.
