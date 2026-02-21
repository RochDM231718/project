import pytest
from unittest.mock import MagicMock, AsyncMock
from app.services.admin.page_service import PageService
from app.schemas.admin.pages import PageCreate, PageUpdate
from app.models.page import Page


@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.find = AsyncMock()
    repo.get = AsyncMock()
    repo.create = AsyncMock()
    repo.update = AsyncMock()
    repo.delete = AsyncMock()
    repo.is_slug_exists = AsyncMock(return_value=False)
    return repo


@pytest.fixture
def service(mock_repo):
    return PageService(repo=mock_repo)


def _get_page(id=1, title="Title", content="Content", slug="title"):
    return Page(id=id, title=title, content=content, slug=slug)


@pytest.mark.asyncio
async def test_create_page_generates_slug_and_saves(service, mock_repo):
    page_data = PageCreate(title="Title", content="Content")
    page = _get_page()
    mock_repo.create.return_value = page

    result = await service.create(page_data)

    assert page_data.slug == "title"
    mock_repo.is_slug_exists.assert_called_once_with("title")
    mock_repo.create.assert_called_once_with(page_data)
    assert result == page


@pytest.mark.asyncio
async def test_update_page_regenerates_slug(service, mock_repo):
    page_data = PageUpdate(title="Title Updated", content="Content Updated")
    page = _get_page(title="Title Updated", content="Content Updated", slug="title-updated")
    mock_repo.update.return_value = page

    result = await service.update(1, page_data)

    assert page_data.slug == "title-updated"
    mock_repo.is_slug_exists.assert_called_once_with("title-updated")
    mock_repo.update.assert_called_once_with(1, page_data)
    assert result == page


@pytest.mark.asyncio
async def test_get_slug_handles_duplicates(service, mock_repo):
    mock_repo.is_slug_exists.side_effect = [True, True, False]
    slug = await service._get_slug("My Page")
    assert slug == "my-page-2"


@pytest.mark.asyncio
async def test_find_page(service, mock_repo):
    page = _get_page()
    mock_repo.find.return_value = page

    result = await service.find(1)

    mock_repo.find.assert_called_once_with(1)
    assert result == page


@pytest.mark.asyncio
async def test_get_pages(service, mock_repo):
    pages = [_get_page()]
    mock_repo.get.return_value = pages

    result = await service.get()

    mock_repo.get.assert_called_once_with(None)
    assert result == pages


@pytest.mark.asyncio
async def test_delete_page(service, mock_repo):
    await service.delete(1)
    mock_repo.delete.assert_called_once_with(1)
