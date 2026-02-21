import pytest
from unittest.mock import MagicMock, AsyncMock
from app.services.admin.user_service import UserService
from app.models.enums import UserRole


@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.find = AsyncMock()
    repo.get = AsyncMock()
    repo.create = AsyncMock()
    repo.update = AsyncMock()
    repo.delete = AsyncMock()
    repo.db = MagicMock()
    repo.db.commit = AsyncMock()
    repo.db.refresh = AsyncMock()
    return repo


@pytest.fixture
def service(mock_repo):
    return UserService(repository=mock_repo)


@pytest.mark.asyncio
async def test_get_users(service, mock_repo):
    users = [MagicMock(id=1, email="a@b.com"), MagicMock(id=2, email="c@d.com")]
    mock_repo.get.return_value = users

    result = await service.get()
    assert len(result) == 2
    mock_repo.get.assert_called_once()


@pytest.mark.asyncio
async def test_find_user(service, mock_repo):
    user = MagicMock(id=1, email="a@b.com")
    mock_repo.find.return_value = user

    result = await service.find(1)
    assert result.id == 1
    mock_repo.find.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_update_role(service, mock_repo):
    user = MagicMock(id=1, role=UserRole.STUDENT)
    mock_repo.find.return_value = user

    result = await service.update_role(1, UserRole.MODERATOR)

    assert user.role == UserRole.MODERATOR
    mock_repo.db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_update_role_user_not_found(service, mock_repo):
    mock_repo.find.return_value = None

    result = await service.update_role(999, UserRole.MODERATOR)
    assert result is None


@pytest.mark.asyncio
async def test_delete_user(service, mock_repo):
    await service.delete(1)
    mock_repo.delete.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_delete_user_not_found(service, mock_repo):
    mock_repo.delete.side_effect = ValueError("User not found")

    with pytest.raises(ValueError, match="User not found"):
        await service.delete(999)
