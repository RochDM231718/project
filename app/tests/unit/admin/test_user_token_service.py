import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException

from app.services.admin.user_token_service import UserTokenService
from app.schemas.admin.user_tokens import UserTokenCreate
from app.models.enums import UserTokenType


@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.create = AsyncMock()
    repo.find_by_token = AsyncMock()
    repo.delete = AsyncMock()
    repo.db = MagicMock()
    repo.db.execute = AsyncMock()
    repo.model = MagicMock()
    return repo


@pytest.fixture
def service(mock_repo):
    return UserTokenService(repo=mock_repo)


@pytest.mark.asyncio
async def test_create_user_token(service, mock_repo):
    data = UserTokenCreate(user_id=1, type=UserTokenType.RESET_PASSWORD)
    mock_repo.create.return_value = MagicMock(id=1, token="123456")

    result = await service.create(data)

    mock_repo.create.assert_called_once()
    call_args = mock_repo.create.call_args[0][0]
    assert call_args["user_id"] == 1
    assert len(call_args["token"]) == 6
    assert call_args["token"].isdigit()
    assert call_args["expires_at"] > datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_get_reset_password_token_success(service, mock_repo):
    token = MagicMock()
    token.token_type = UserTokenType.RESET_PASSWORD.value
    token.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    mock_repo.find_by_token.return_value = token

    result = await service.getResetPasswordToken("123456")
    assert result == token
    mock_repo.find_by_token.assert_called_once_with("123456")


@pytest.mark.asyncio
async def test_get_reset_password_token_not_found(service, mock_repo):
    mock_repo.find_by_token.return_value = None

    with pytest.raises(HTTPException) as exc:
        await service.getResetPasswordToken("invalid")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_reset_password_token_expired(service, mock_repo):
    token = MagicMock()
    token.token_type = UserTokenType.RESET_PASSWORD.value
    token.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    mock_repo.find_by_token.return_value = token

    with pytest.raises(HTTPException) as exc:
        await service.getResetPasswordToken("expired")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_get_reset_password_token_wrong_type(service, mock_repo):
    token = MagicMock()
    token.token_type = "EMAIL_VERIFICATION"
    token.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    mock_repo.find_by_token.return_value = token

    with pytest.raises(HTTPException) as exc:
        await service.getResetPasswordToken("123456")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_token(service, mock_repo):
    mock_repo.delete.return_value = True
    result = await service.delete(1)
    mock_repo.delete.assert_called_once_with(1)
    assert result is True
