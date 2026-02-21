import pytest
from unittest.mock import MagicMock, AsyncMock

from app.services.auth_service import AuthService
from app.models.enums import UserRole, UserStatus


def _make_user(id=1, email="test@example.com", hashed_password="hashed123",
               role=UserRole.SUPER_ADMIN, status=UserStatus.ACTIVE, is_active=True):
    user = MagicMock()
    user.id = id
    user.email = email
    user.hashed_password = hashed_password
    user.role = role
    user.status = status
    user.is_active = is_active
    user.first_name = "Test"
    user.last_name = "User"
    user.avatar_path = None
    return user


@pytest.fixture
def auth_service():
    repo = MagicMock()
    repo.get_by_email = AsyncMock(return_value=None)
    token_service = MagicMock()
    service = AuthService(repo, token_service)
    return service


@pytest.mark.asyncio
async def test_authenticate_user_not_found(auth_service, monkeypatch):
    monkeypatch.setattr("app.services.auth_service.redis_client.get", AsyncMock(return_value=None))
    monkeypatch.setattr("app.services.auth_service.redis_client.incr", AsyncMock())
    monkeypatch.setattr("app.services.auth_service.redis_client.ttl", AsyncMock(return_value=-1))
    monkeypatch.setattr("app.services.auth_service.redis_client.expire", AsyncMock())

    result = await auth_service.authenticate("unknown@example.com", "password")
    assert result is None


@pytest.mark.asyncio
async def test_authenticate_wrong_password(auth_service, monkeypatch):
    user = _make_user()
    auth_service.repository.get_by_email = AsyncMock(return_value=user)
    monkeypatch.setattr("app.services.auth_service.redis_client.get", AsyncMock(return_value=None))
    monkeypatch.setattr("app.services.auth_service.redis_client.incr", AsyncMock())
    monkeypatch.setattr("app.services.auth_service.redis_client.ttl", AsyncMock(return_value=-1))
    monkeypatch.setattr("app.services.auth_service.redis_client.expire", AsyncMock())
    monkeypatch.setattr(auth_service, "verify_password", lambda p, h: False)

    result = await auth_service.authenticate("test@example.com", "badpassword")
    assert result is None


@pytest.mark.asyncio
async def test_authenticate_rejected_user(auth_service, monkeypatch):
    user = _make_user(status=UserStatus.REJECTED)
    auth_service.repository.get_by_email = AsyncMock(return_value=user)
    monkeypatch.setattr("app.services.auth_service.redis_client.get", AsyncMock(return_value=None))

    result = await auth_service.authenticate("test@example.com", "password")
    assert result is None


@pytest.mark.asyncio
async def test_authenticate_success(auth_service, monkeypatch):
    user = _make_user()
    auth_service.repository.get_by_email = AsyncMock(return_value=user)
    monkeypatch.setattr("app.services.auth_service.redis_client.get", AsyncMock(return_value=None))
    monkeypatch.setattr("app.services.auth_service.redis_client.delete", AsyncMock())
    monkeypatch.setattr(auth_service, "verify_password", lambda p, h: True)

    result = await auth_service.authenticate("test@example.com", "password")
    assert result == user


@pytest.mark.asyncio
async def test_authenticate_blocked_by_rate_limit(auth_service, monkeypatch):
    from app.services.auth_service import UserBlockedException
    monkeypatch.setattr("app.services.auth_service.redis_client.get", AsyncMock(return_value="5"))
    monkeypatch.setattr("app.services.auth_service.redis_client.ttl", AsyncMock(return_value=600))

    with pytest.raises(UserBlockedException):
        await auth_service.authenticate("test@example.com", "password")


def test_verify_password(auth_service):
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    hashed = pwd_context.hash("correctpassword")

    assert auth_service.verify_password("correctpassword", hashed) is True
    assert auth_service.verify_password("wrongpassword", hashed) is False
