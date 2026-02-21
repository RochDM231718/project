# Sirius Achievements - Security Audit & Improvement Proposals

**Date:** 2026-02-21
**Scope:** Full codebase analysis
**Severity levels:** CRITICAL / HIGH / MEDIUM / LOW / INFO

---

## Table of Contents

1. [Critical Vulnerabilities](#1-critical-vulnerabilities)
2. [High Severity Issues](#2-high-severity-issues)
3. [Medium Severity Issues](#3-medium-severity-issues)
4. [Low Severity Issues](#4-low-severity-issues)
5. [Architectural Improvements](#5-architectural-improvements)
6. [Feature Suggestions](#6-feature-suggestions)

---

## 1. Critical Vulnerabilities

### 1.1 CRITICAL: SQL Injection via ILIKE Patterns

**Files:**
- `app/routers/admin/achievements.py:29,56`
- `app/routers/admin/users.py:48-51,78-79`
- `app/routers/admin/documents.py:38-41`

**Problem:**
User input is interpolated directly into SQL ILIKE patterns without escaping special SQL wildcard characters (`%`, `_`). While SQLAlchemy parameterizes the value (preventing classic SQL injection), the `%` and `_` inside the LIKE pattern are **not escaped**, allowing a user to craft search queries that match unintended data or cause performance degradation.

```python
# Current (vulnerable pattern):
Achievement.title.ilike(f"%{q}%")

# Attacker can send q = "%" and match ALL records
```

**Fix:**
```python
from sqlalchemy import func

def escape_like(value: str) -> str:
    return value.replace("%", "\\%").replace("_", "\\_")

# Usage:
Achievement.title.ilike(f"%{escape_like(q)}%")
```

---

### 1.2 CRITICAL: Default Admin Credentials in Setup Script

**File:** `setup.py:29-30`

```python
email = "admin@example.com"
password = "admin"
```

**Problem:**
The setup script creates a SUPER_ADMIN account with trivially guessable credentials (`admin@example.com` / `admin`). If this script runs in production and the password is not changed, an attacker gets full administrative access.

**Fix:**
- Generate a random password at setup time and print it once
- Force password change on first login
- Remove hardcoded credentials from source code

---

### 1.3 CRITICAL: `backup.sql` Committed to Repository

**File:** `backup.sql` (root of project)

**Problem:**
A database backup file is committed to the repository. This may contain:
- User personal data (emails, names, phone numbers)
- Hashed passwords (susceptible to offline brute-force)
- Achievement records and other sensitive data

This violates GDPR/personal data protection principles.

**Fix:**
- Remove `backup.sql` from the repository: `git rm backup.sql`
- Add `*.sql` or `backup.sql` to `.gitignore`
- If the file contained real data, rotate all affected user passwords

---

### 1.4 CRITICAL: Missing Authentication on `guard_router` Routes

**File:** `app/routers/admin/admin.py:21`

```python
guard_router = APIRouter(prefix="/sirius.achievements", tags=["Admin Protected"])
```

**Problem:**
The `guard_router` has **no dependency on authentication**. While some endpoints (like `users.py`) manually call `check_admin_rights()`, many endpoints using this router rely only on `request.session.get('auth_id')` — which returns `None` for unauthenticated users rather than denying access. Critical examples:

- `dashboard.py:20` — `get_current_user()` returns `None`, but the code continues rendering (line 31 checks `pending_review` but doesn't reject unauthenticated users before that)
- `achievements.py:47` — `user_id = request.session.get('auth_id')` can be `None`, allowing `db.get(Users, None)`
- `leaderboard.py:26` — `user = await db.get(Users, user_id)` where `user_id` can be `None`, leading to a crash or data leak
- `notifications.py:16` — returns `{"count": 0}` for unauthenticated users instead of 401

**Fix:**
Add a global authentication dependency to `guard_router`:
```python
from app.middlewares.admin_middleware import auth

guard_router = APIRouter(
    prefix="/sirius.achievements",
    tags=["Admin Protected"],
    dependencies=[Depends(auth)]
)
```

---

## 2. High Severity Issues

### 2.1 HIGH: Brute-Force on Password Reset Code (6-digit OTP)

**File:** `app/services/admin/user_token_service.py:16`

```python
token = ''.join(secrets.choice(string.digits) for _ in range(6))
```

**Problem:**
The reset password token is a 6-digit numeric code (1,000,000 combinations). The `verify_code` endpoint (`app/routers/admin/auth.py:197`) has **no rate limiting** on code verification attempts. An attacker can brute-force all 1M combinations.

**Fix:**
- Add rate limiting on `/verify-code` endpoint (max 5 attempts per email per 15 minutes)
- Invalidate the token after N failed attempts
- Consider using longer tokens (8+ characters with mixed alphanumeric)

---

### 2.2 HIGH: Email Verification Code Stored in Session (Weak Security)

**File:** `app/routers/admin/profile.py:83-85`

```python
code = str(random.randint(100000, 999999))
request.session['pending_email'] = email
request.session['email_code'] = code
```

**Problems:**
1. Uses `random.randint()` instead of `secrets` — **not cryptographically secure**
2. The verification code is stored in the session cookie (signed but readable client-side)
3. No rate limiting on verification attempts
4. No expiration on the code

**Fix:**
```python
import secrets
code = ''.join(secrets.choice('0123456789') for _ in range(6))
# Store code server-side (in DB or Redis), not in session
```

---

### 2.3 HIGH: Role Check via String Comparison is Fragile

**Files:**
- `app/routers/admin/achievements.py:198`
- `app/routers/admin/documents.py:31,64-66`
- `app/routers/admin/dashboard.py:28`

```python
is_staff = str(user_role) in [UserRole.MODERATOR.value, UserRole.SUPER_ADMIN.value, 'moderator', 'super_admin']
# and
allowed_roles = ['admin', 'moderator', 'super_admin', 'ADMIN', 'MODERATOR', 'SUPER_ADMIN']
```

**Problem:**
Role checking is done by string comparison with hardcoded lists that include case variations. This is error-prone, bypassed if enum values change, and includes a non-existent 'ADMIN' role (only SUPER_ADMIN exists in the enum).

**Fix:**
Always compare enum objects directly:
```python
if user.role in [UserRole.MODERATOR, UserRole.SUPER_ADMIN]:
```

---

### 2.4 HIGH: Path Traversal Risk in File Operations

**File:** `app/services/admin/achievement_service.py:60,73`

```python
old_file_full_path = os.path.join(service.upload_dir, achievement.file_path)
# and
full_path = os.path.join("static", item.file_path)
```

**Problem:**
While `file_path` is currently generated server-side with UUID names, if this value were ever tampered with (e.g., through a DB injection or migration error), `os.path.join` with a value starting with `/` would resolve to an absolute path, allowing deletion of arbitrary files.

**Fix:**
```python
import os
safe_path = os.path.normpath(os.path.join("static", item.file_path))
if not safe_path.startswith(os.path.normpath("static")):
    raise ValueError("Invalid file path")
```

---

### 2.5 HIGH: User Avatar Upload Trusts `content_type` Header

**File:** `app/services/admin/user_service.py:19`

```python
if file.content_type not in ALLOWED_AVATAR_TYPES:
    raise ValueError(...)
```

**Problem:**
Unlike achievement file uploads (which check magic bytes), avatar uploads only check the `Content-Type` header — which is fully controlled by the client. An attacker can upload a malicious file (e.g., HTML with JavaScript, `.php`, etc.) by setting a fake Content-Type.

**Fix:**
Apply the same magic-byte validation used in `AchievementService.save_file()`:
```python
ALLOWED_SIGNATURES = {
    "image/jpeg": b'\xFF\xD8\xFF',
    "image/png": b'\x89\x50\x4E\x47\x0D\x0A\x1A\x0A',
    "image/webp": b'RIFF'
}
header = await file.read(8)
await file.seek(0)
# Validate against signatures...
```

---

## 3. Medium Severity Issues

### 3.1 MEDIUM: No Password Strength Validation on Reset

**File:** `app/routers/admin/auth.py:229-261`

**Problem:**
The `reset_password` endpoint does not use `ResetPasswordSchema` from `app/schemas/admin/auth.py`. While registration validates password strength (uppercase, lowercase, digit, special char), password reset accepts any string. A user can reset their password to `"12345678"`.

**Fix:**
```python
from app.schemas.admin.auth import ResetPasswordSchema

# Validate before proceeding:
ResetPasswordSchema(password=password, password_confirm=password_confirm)
```

---

### 3.2 MEDIUM: Session Fixation After Registration

**File:** `app/routers/admin/auth.py:121-123`

```python
request.session['auth_id'] = user.id
request.session['auth_name'] = f"{user.first_name} {user.last_name}"
request.session['auth_avatar'] = user.avatar_path
```

**Problem:**
After successful registration, the user is immediately authenticated and given a session with GUEST role and PENDING status. The session ID is not regenerated, making session fixation attacks possible.

**Fix:**
- Regenerate session after authentication: clear old session, create new one
- Do not auto-login after registration; require explicit login
- Or at minimum, verify user status before granting access to protected routes

---

### 3.3 MEDIUM: No HTTPS Enforcement

**Problem:**
There is no middleware or configuration forcing HTTPS redirects. Session cookies and CSRF tokens transmitted over HTTP are vulnerable to interception (MITM).

**Fix:**
- Add `Secure` flag to session cookies
- Add HSTS header middleware
- Force HTTPS redirect in production

---

### 3.4 MEDIUM: Missing Security Headers

**Problem:**
The application does not set standard security headers:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Content-Security-Policy`
- `Strict-Transport-Security`
- `Referrer-Policy`

**Fix:**
Add a security headers middleware:
```python
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response
```

---

### 3.5 MEDIUM: Docker Compose Exposes Ports Externally

**File:** `docker-compose.yml:12-13,20-21`

```yaml
ports:
  - "5432:5432"   # PostgreSQL accessible from outside!
  - "6379:6379"   # Redis accessible from outside!
```

**Problem:**
PostgreSQL and Redis ports are mapped to the host, making them accessible from any network interface. In a production environment, this means the database and cache are directly exposed to the internet.

**Fix:**
```yaml
# Bind to localhost only in production:
ports:
  - "127.0.0.1:5432:5432"
  - "127.0.0.1:6379:6379"
# Or remove port mappings entirely and use Docker networks
```

---

### 3.6 MEDIUM: Redis Without Authentication

**File:** `docker-compose.yml:17-21`

**Problem:**
Redis runs without a password. Combined with exposed port 6379, anyone can connect and manipulate rate-limiting data, cache values, or flush the database.

**Fix:**
```yaml
redis:
  command: redis-server --requirepass ${REDIS_PASSWORD}
```

---

### 3.7 MEDIUM: `--reload` Flag in Production Dockerfile

**File:** `Dockerfile:21`

```dockerfile
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

**Problem:**
The `--reload` flag enables hot-reloading, which:
- Watches filesystem for changes (resource waste)
- Can be exploited if an attacker writes files to the mounted volume
- Is a development-only feature not suitable for production

**Fix:**
```dockerfile
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

---

### 3.8 MEDIUM: Source Code Mounted as Volume in Docker

**File:** `docker-compose.yml:42`

```yaml
volumes:
  - .:/app
```

**Problem:**
The entire project directory (including `.env`, `.git`, `backup.sql`) is mounted into the container. If an attacker gains access to the container, they have access to:
- Environment variables with secrets
- Git history (may contain previously committed secrets)
- Database backups

**Fix:**
In production, do not mount the source code. Copy it during build:
```yaml
# Remove the volume mount for production
# Only use it for development with a separate docker-compose.dev.yml
```

---

## 4. Low Severity Issues

### 4.1 LOW: Database Connection String Printed to Stdout

**File:** `app/infrastructure/database/__init__.py:21-24`

```python
print(f"--- DATABASE CONNECTION ---")
safe_url = DATABASE_URL.replace(DB_PASSWORD, "****") if DB_PASSWORD else DATABASE_URL
print(f"URL: {safe_url}")
```

**Problem:**
While the password is masked, this prints connection details (host, port, username, database name) to stdout on every startup. In containerized environments, stdout is often captured in logging systems.

**Fix:**
Use `logger.debug()` instead of `print()`, and only in development mode.

---

### 4.2 LOW: Debug Print Statements in Production Code

**Files:**
- `app/routers/admin/deps.py:17` — `print(f"DEBUG: ...")`
- `app/middlewares/admin_middleware.py:54` — `print(f"Middleware DB/Cache Error: ...")`
- `app/services/auth_service.py:175` — `print(f"[INFO] Email sent to {to_email}")`

**Fix:**
Replace all `print()` with structured logging via `structlog`.

---

### 4.3 LOW: Error Messages Leak Internal Details

**File:** `app/routers/admin/achievements.py:134`

```python
return RedirectResponse(url=f"...?toast_msg=Ошибка: {e}&toast_type=error", ...)
```

**Problem:**
Exception messages (which may contain stack traces, SQL errors, or internal paths) are passed directly to the user via URL parameters.

**Fix:**
Log the full error server-side; show a generic message to the user:
```python
logger.error("Achievement creation failed", exc_info=True)
return RedirectResponse(url="...?toast_msg=Произошла ошибка&toast_type=error", ...)
```

---

### 4.4 LOW: `ALLOWED_HOSTS` Default Includes Wildcard in `.env.example`

**File:** `.env.example:18`

```
ALLOWED_HOSTS="localhost,127.0.0.1,*"
```

**Problem:**
The wildcard `*` defeats the purpose of the TrustedHostMiddleware. Users copying `.env.example` to `.env` will have host header validation disabled.

**Fix:**
Remove the wildcard from the example:
```
ALLOWED_HOSTS="localhost,127.0.0.1,your-domain.com"
```

---

### 4.5 LOW: No Password Strength Check on Profile Password Change

**File:** `app/routers/admin/profile.py:193-226`

**Problem:**
The password change endpoint in the profile section does not validate password strength. Users can change their password to weak values.

---

### 4.6 LOW: Missing API_SECRET_KEY / API_REFRESH_SECRET_KEY in `.env.example`

**File:** `.env.example`

**Problem:**
The JWT handler requires `API_SECRET_KEY` and `API_REFRESH_SECRET_KEY` environment variables and raises `ValueError` if they're missing. But these variables are not documented in `.env.example`, making setup difficult and potentially causing crashes.

---

### 4.7 LOW: Old Reset Tokens Not Invalidated

**File:** `app/services/admin/user_token_service.py`

**Problem:**
When a new password reset token is created, old tokens for the same user are not invalidated. Multiple valid tokens can exist simultaneously.

---

### 4.8 LOW: Uploaded Files Served via Static Mount Without Access Control

**File:** `main.py:47`

```python
app.mount("/static", StaticFiles(directory="static"), name="static")
```

**Problem:**
All uploaded achievement files (certificates, documents) are served as static files without authentication. Anyone who knows or guesses the UUID filename can access any user's documents directly via `/static/uploads/achievements/{uuid}.pdf`.

**Fix:**
Serve uploaded files through an authenticated endpoint instead of the static mount:
```python
@router.get("/files/{filename}")
async def serve_file(filename: str, user=Depends(get_current_user)):
    # Check permissions, then serve
```

---

## 5. Architectural Improvements

### 5.1 Unify Authentication Logic

Currently there are 3 different authentication patterns:
1. `admin_middleware.py:auth()` — checks session + role (ADMIN/MODERATOR)
2. `deps.py:get_current_user()` — checks session, returns None on failure
3. `api_auth_middleware.py:auth()` — checks JWT Bearer token

**Recommendation:**
Create a unified dependency that accepts both session and JWT, with configurable role requirements:
```python
def require_auth(roles: list[UserRole] = None):
    async def dependency(request: Request):
        user = await get_authenticated_user(request)
        if roles and user.role not in roles:
            raise HTTPException(403)
        return user
    return dependency
```

### 5.2 Implement Repository Pattern Consistently

The codebase mixes:
- Direct `db.execute()` calls in routers (e.g., `moderation.py:174`)
- Repository methods via services
- Manual ORM queries in middleware

**Recommendation:**
Move all database operations to the repository layer. Routers should only interact with services.

### 5.3 Add Database Migrations for Production

While Alembic is configured, the app also creates tables on startup (`main.py:42-44`):
```python
async with engine.begin() as conn:
    await conn.run_sync(Base.metadata.create_all)
```

**Recommendation:**
Remove `create_all` from the startup event in production. Rely exclusively on Alembic migrations.

### 5.4 Add Request Validation with Pydantic

Many endpoints accept raw `Form(...)` fields without Pydantic validation:
- `profile.py:update_profile` — no validation on `first_name`, `last_name`, `phone_number`
- `moderation.py:update_achievement_status` — `status` is a raw string, not validated against enum

**Recommendation:**
Create Pydantic schemas for all input and validate at the router level.

### 5.5 Add Audit Logging

No audit trail exists for critical admin actions:
- User role changes
- Achievement approvals/rejections
- Season endings
- User deletions

**Recommendation:**
Create an `AuditLog` model to record who did what, when, and to whom.

---

## 6. Feature Suggestions

### 6.1 Two-Factor Authentication (2FA)
Add optional TOTP-based 2FA for admin and moderator accounts to strengthen access control.

### 6.2 Achievement History / Version Tracking
Track changes to achievements (status changes, file re-uploads) with timestamps and who performed the action.

### 6.3 Rate Limiting Middleware
Add global rate limiting (e.g., via Redis) for all API and form endpoints to prevent abuse. Currently only login has rate limiting.

### 6.4 Content Security Policy (CSP)
Implement a strict CSP to mitigate XSS risks from user-generated content or third-party scripts.

### 6.5 Automated Testing for Security
- Add integration tests for authentication/authorization
- Test that unauthenticated users cannot access protected routes
- Test file upload with malicious content
- Test CSRF protection

### 6.6 S3 File Storage
The code imports `boto3` but files are stored locally. Migrating to S3 (or compatible object storage) would improve:
- Scalability across multiple app instances
- Backup and disaster recovery
- Access control via presigned URLs

### 6.7 Health Check Endpoint
Add a `/health` endpoint that checks database and Redis connectivity for use with container orchestration (Kubernetes, Docker health checks).

### 6.8 Pagination Limit Cap
Currently, pagination uses a hardcoded `limit = 10`, but there's no maximum cap on `page` parameter. While `ge=1` ensures minimum, extremely high page values could cause slow queries.

### 6.9 Notification Delivery Improvements
- Add WebSocket support for real-time notifications
- Add email notification option for important events (achievement approved/rejected)
- Mark individual notifications as read (currently only "mark all as read")

### 6.10 Session Timeout / Inactivity Logout
Currently sessions have no explicit timeout. Add configurable session TTL and automatic logout after inactivity.

---

## Summary

| Severity | Count | Key Areas |
|----------|-------|-----------|
| CRITICAL | 4     | SQL patterns, default creds, backup in repo, missing auth on router |
| HIGH     | 5     | OTP brute-force, insecure email code, role checks, path traversal, avatar upload |
| MEDIUM   | 8     | No password validation on reset, session fixation, no HTTPS, missing headers, Docker config |
| LOW      | 8     | Debug prints, error leaks, static file access, missing env vars |
| Architecture | 5 | Auth unification, repository pattern, migrations, validation, audit logging |
| Features | 10    | 2FA, history tracking, rate limiting, CSP, testing, S3, health check, etc. |

**Overall assessment:**
The project has a solid architectural foundation with proper separation of concerns (routers/services/repositories), good use of async patterns, and some security measures already in place (CSRF protection, bcrypt password hashing, file signature validation, login rate limiting). The main areas requiring attention are authentication consistency across routes, input validation on reset/profile flows, Docker hardening for production, and access control for uploaded files.
