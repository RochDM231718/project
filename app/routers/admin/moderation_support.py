from fastapi import APIRouter, Request, Depends, Form, UploadFile, File, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import quote
import math
import structlog

from app.security.csrf import validate_csrf
from app.routers.admin.admin import guard_router, templates, get_db
from app.routers.admin.deps import get_current_user
from app.repositories.admin.support_repository import SupportTicketRepository, SupportMessageRepository
from app.services.admin.support_service import SupportService
from app.models.enums import UserRole, SupportTicketStatus

logger = structlog.get_logger()
router = guard_router

ITEMS_PER_PAGE = 20


def get_support_service(db: AsyncSession = Depends(get_db)):
    ticket_repo = SupportTicketRepository(db)
    message_repo = SupportMessageRepository(db)
    return SupportService(ticket_repo, message_repo)


async def require_moderator(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    if not user or user.role.value not in ['MODERATOR', 'SUPER_ADMIN']:
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    return user


@router.get('/moderation/support', response_class=HTMLResponse, name='admin.moderation.support.index')
async def moderation_support_index(
        request: Request,
        page: int = Query(1, ge=1),
        db: AsyncSession = Depends(get_db),
        user=Depends(require_moderator)
):
    ticket_repo = SupportTicketRepository(db)
    tickets = await ticket_repo.get_new_tickets(page)
    total = await ticket_repo.count_new_tickets()
    total_pages = math.ceil(total / ITEMS_PER_PAGE) if total > 0 else 1

    return templates.TemplateResponse('moderation/support.html', {
        'request': request,
        'user': user,
        'tickets': tickets,
        'page': page,
        'total_pages': total_pages,
        'total': total
    })


@router.get('/moderation/support/all', response_class=HTMLResponse, name='admin.moderation.support.all')
async def moderation_support_all(
        request: Request,
        page: int = Query(1, ge=1),
        status: str = '',
        query: str = '',
        sort_by: str = 'created_at',
        sort_order: str = 'desc',
        db: AsyncSession = Depends(get_db),
        user=Depends(require_moderator)
):
    ticket_repo = SupportTicketRepository(db)

    filters = {'page': page}
    if status:
        filters['status'] = status
    if query:
        filters['query'] = query

    tickets = await ticket_repo.get_all_tickets(filters, sort_by, sort_order)
    total = await ticket_repo.count_all_tickets(filters)
    total_pages = math.ceil(total / ITEMS_PER_PAGE) if total > 0 else 1

    return templates.TemplateResponse('moderation/support_all.html', {
        'request': request,
        'user': user,
        'tickets': tickets,
        'page': page,
        'total_pages': total_pages,
        'total': total,
        'current_status': status,
        'current_query': query,
        'sort_by': sort_by,
        'sort_order': sort_order
    })


@router.get('/moderation/support/{ticket_id}', response_class=HTMLResponse, name='admin.moderation.support.chat')
async def moderation_support_chat(
        request: Request,
        ticket_id: int,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_moderator)
):
    ticket_repo = SupportTicketRepository(db)
    ticket = await ticket_repo.find_with_messages(ticket_id)

    if not ticket:
        raise HTTPException(status_code=404, detail="Обращение не найдено")

    return templates.TemplateResponse('moderation/support_chat.html', {
        'request': request,
        'user': user,
        'ticket': ticket
    })


@router.post('/moderation/support/{ticket_id}/send', name='admin.moderation.support.send',
             dependencies=[Depends(validate_csrf)])
async def moderation_send_message(
        request: Request,
        ticket_id: int,
        text: str = Form(None),
        file: UploadFile = File(None),
        db: AsyncSession = Depends(get_db),
        user=Depends(require_moderator),
        service: SupportService = Depends(get_support_service)
):
    try:
        await service.send_message(
            ticket_id=ticket_id,
            sender_id=user.id,
            text=text,
            file=file if file and file.filename else None,
            is_from_moderator=True
        )
    except ValueError as e:
        return RedirectResponse(
            url=f'/sirius.achievements/moderation/support/{ticket_id}?toast_msg={quote(str(e))}&toast_type=error',
            status_code=302
        )

    return RedirectResponse(url=f'/sirius.achievements/moderation/support/{ticket_id}', status_code=302)


@router.post('/moderation/support/{ticket_id}/close', name='admin.moderation.support.close',
             dependencies=[Depends(validate_csrf)])
async def moderation_close_ticket(
        request: Request,
        ticket_id: int,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_moderator),
        service: SupportService = Depends(get_support_service)
):
    await service.close_ticket(ticket_id)
    return RedirectResponse(
        url=f'/sirius.achievements/moderation/support/{ticket_id}?toast_msg={quote("Обращение закрыто")}&toast_type=success',
        status_code=302
    )


@router.post('/moderation/support/{ticket_id}/reopen', name='admin.moderation.support.reopen',
             dependencies=[Depends(validate_csrf)])
async def moderation_reopen_ticket(
        request: Request,
        ticket_id: int,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_moderator),
        service: SupportService = Depends(get_support_service)
):
    await service.reopen_ticket(ticket_id)
    return RedirectResponse(
        url=f'/sirius.achievements/moderation/support/{ticket_id}?toast_msg={quote("Обращение открыто")}&toast_type=success',
        status_code=302
    )
