# AdsEarn

New Kotlin/Jetpack Compose client and FastAPI service. The application opens directly on Home and creates a revocable anonymous server session in the background. Session issuance requires a single-use server challenge signed with an Android Keystore P-256 private key. The server binds the key together with the app-scoped device fingerprint; the fingerprint alone cannot recover an account. Session tokens are random bearer credentials stored in Android encrypted preferences. Logout revokes the session, clears the token, and deletes the device key so the prior anonymous account cannot silently be reopened. The backend is authoritative for identity, ad quota, wallet, payment, withdrawals, and support.

## Layout

- `android/`: Compose application with UI, ViewModels, repositories, Retrofit API, session storage, and AdMob manager.
- `backend/app/`: FastAPI, SQLAlchemy models, session security, services, and API routers.
- `backend/alembic/`: PostgreSQL schema migrations.

## Backend development

Python 3.11+ and PostgreSQL are required for a full deployment. Copy `backend/.env.example` to a private environment file, set a PostgreSQL `DATABASE_URL` and independent session, device-binding, and payment-encryption secrets, then:

```powershell
python -m pip install -r backend/requirements.txt -r backend/requirements-dev.txt
Set-Location backend
alembic upgrade head
pytest -q
uvicorn app.main:app --reload
```

Tests use isolated SQLite databases; production refuses SQLite. The migration is Alembic-managed. `/health` checks the configured database. Android transmits a SHA-256 pseudonym of the app-scoped Android device identifier and a public key; only the matching non-exportable Android Keystore private key can resume that identity. Clearing app data or reinstalling can recover an account only if Android Keystore preserves the app key on that device. If the key is lost (for example after uninstall or device replacement), this anonymous account has no password-based recovery flow; a new key creates a separate account rather than granting access to the old one. This avoids account takeover but can make old profile/history inaccessible. Key possession does not prove device integrity or prevent account farming with newly generated keys. The production session endpoints therefore fail closed until a server-verified Google Play Integrity (or equivalent) attestation flow is implemented, provisioned, and validated; local development sessions do not claim this protection.

## Android

Open `android/` in Android Studio, install the configured Android SDK, and provide a real HTTPS API root in untracked `android/local.properties`:

```properties
API_BASE_URL=https://your-real-api-domain/
```

Development builds use Google's official test rewarded-ad unit and are labelled Development. Production uses the requested AdsEarn App ID and rewarded unit; all production variants fail without an explicitly configured HTTPS API URL. Use `.\gradlew.bat :app:assembleDevelopmentDebug` on Windows to create a local development APK. A release signing key is supplied outside this project.

## Accounting and production status

Publisher revenue, ad completion activity, application reward ledger, and withdrawable wallet funds are separate. Ad completions never create money or wallet credits. There is no business rule or funded reward source in this project, so the wallet begins at zero and withdrawals cannot be fabricated. Admin withdrawal state changes are server role-gated; only an authorized administrator can record an actual payment reference and mark a transfer paid.

The AdMob callback verifies Google's ECDSA signatures, reserved user/event association, configured rewarded ad unit (bound to the production App ID when the reservation is created), server timestamp, and unique transaction ID. Google SSV callbacks do not contain an `app_id` parameter; application association is enforced through the server-configured ad-unit mapping. Duplicate signed callbacks are idempotently acknowledged. Keep `ADMOB_SSV_VERIFIED=false` until the real HTTPS endpoint is configured in AdMob and a live Google callback has been validated. This workspace cannot provision a production database, domain, HTTPS service, AdMob account settings, or Play signing credentials; none is claimed as deployed.

## Launch prerequisites

Provision persistent PostgreSQL and an HTTPS API, set secrets through the host's secret manager, configure gateway rate limits and the API domain, configure the AdMob SSV callback, live-test SSV before enabling it, provision Google Play Integrity for stronger device attestation, arrange reviewed/legitimate wallet funding rules before allowing withdrawals, and complete Play/legal/privacy release steps. Never commit environment files or signing keys.
