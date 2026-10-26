# Personal Hub Pro — website + Chrome extension

A learning starter for a multi-user personal-records app:
- Flask website with registration, login, logout, CRUD records, search and category filters
- Per-user record ownership enforced in database queries
- Password hashing with Werkzeug
- CSRF protection for website forms
- Short-lived JWT bearer tokens for extension API
- Rate limiting on login/registration
- Chrome Manifest V3 popup that calls the same API
- SQLite for local development; PostgreSQL URL supported for hosting

## 1. Requirements
Install Python 3.11+ and VS Code. Extract this folder and open it in VS Code using File → Open Folder.

## 2. Setup in Windows PowerShell
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```
Edit `.env` and replace both secret values with long random values. For local learning, `COOKIE_SECURE=0` is required because localhost is HTTP. Never use that setting on an HTTPS production deployment.

Generate secrets using:
```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```
Run it twice and place different outputs into `SECRET_KEY` and `JWT_SECRET_KEY`.

## 3. Initialize and run the website
```powershell
flask --app app init-db
python app.py
```
Open `http://127.0.0.1:5000` in Chrome. Create two test accounts to verify that each account sees only its own records.

## 4. Promote an administrator
First register the account through the website. Then run:
```powershell
flask --app app make-admin admin@example.com
```
Replace the email with the exact account email. Never expose admin promotion as a public registration option. This starter does not implement a separate admin console; the role is stored for future authorized admin features.

## 5. Load the Chrome extension locally
1. Open `extension/manifest.json`.
2. For local testing, the API base in `extension/popup.js` is `http://127.0.0.1:5000`; the manifest permits this local host.
3. Start the Flask server.
4. In Chrome, open `chrome://extensions`.
5. Turn on **Developer mode**.
6. Click **Load unpacked** and select this project's `extension` folder.
7. Click the extension icon. Register an account on the website first, then sign in in the popup.

The extension uses `chrome.storage.session`, so its access token is kept in the extension session rather than ordinary website local storage. JWT tokens expire after 30 minutes; sign in again when needed.

## 6. Before publishing online
- Deploy the Flask app to a Python-compatible host and provision managed PostgreSQL.
- Set `DATABASE_URL`, `SECRET_KEY`, `JWT_SECRET_KEY`, `COOKIE_SECURE=1`, and a persistent rate-limit storage URL in the host's secret/environment settings. Never upload `.env`.
- Ensure HTTPS is enabled. Use a strong unique secret for each key. Configure backups, restore tests, monitoring, database migrations, and account deletion/export policies.
- Set `RATELIMIT_STORAGE_URI` to a supported shared Redis URL for multi-worker production. The default in-memory limiter is only suitable for development.
- Add email verification, password reset, stronger abuse prevention, audit logging, and privacy/legal disclosures before accepting real users.
- Configure `TRUSTED_HOSTS` and a reviewed Content Security Policy for the actual domain. Review all security controls before handling sensitive information.
- This sample does not include email verification, password reset, MFA, account deletion UI, or a full admin portal. It is a learning baseline, not a security audit or a guarantee of production readiness.

## 7. Connect extension to production
Before submitting to the Chrome Web Store:
1. In `extension/popup.js`, replace `API_BASE` with your real HTTPS API origin, for example `https://your-real-domain.example`. Do not leave the placeholder.
2. In `extension/manifest.json`, replace the example production entry in `host_permissions` with the exact HTTPS API origin. Remove the localhost permission from the release build.
3. Test the extension against the HTTPS API. Keep permissions narrow and explain them in the store listing.
4. Create the release ZIP with the files inside `extension/` at the ZIP root (manifest.json must be at the root). Do not upload the whole project ZIP as the extension.
5. Register a Chrome Web Store developer account, upload the extension ZIP, provide screenshots and privacy disclosures, complete the data-use/privacy forms accurately, and submit for review.

## Security limitations
The extension login API endpoint is exempt from Flask-WTF CSRF because it uses a bearer token request from the extension. Do not enable permissive cross-origin access. The website uses CSRF-protected forms and secure cookie settings for production. The app enforces ownership for user CRUD, including API routes. Admin role does not currently bypass ownership.
