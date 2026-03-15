from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import quote
import structlog

from app.security.csrf import validate_csrf
from app.routers.admin.admin import guard_router, templates, get_db
from app.routers.admin.deps import get_current_user
from app.repositories.admin.support_repository import SupportTicketRepository, SupportMessageRepository
from app.services.admin.support_service import SupportService

logger = structlog.get_logger()
router = guard_router


def get_support_service(db: AsyncSession = Depends(get_db)):
    ticket_repo = SupportTicketRepository(db)
    message_repo = SupportMessageRepository(db)
    return SupportService(ticket_repo, message_repo)


@router.get('/support', response_class=HTMLResponse, name='admin.support.index')
async def support_index(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse(url='/sirius.achievements/login', status_code=302)

    ticket_repo = SupportTicketRepository(db)
    tickets = await ticket_repo.get_by_user(user.id)

    return templates.TemplateResponse('support/index.html', {
        'request': request,
        'user': user,
        'tickets': tickets
    })


@router.post('/support/create', name='admin.support.create', dependencies=[Depends(validate_csrf)])
async def create_ticket(
        request: Request,
        subject: str = Form(...),
        message: str = Form(...),
        file: UploadFile = File(None),
        db: AsyncSession = Depends(get_db),
        service: SupportService = Depends(get_support_service)
):
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse(url='/sirius.achievements/login', status_code=302)

    try:
        ticket = await service.create_ticket(user.id, subject[:255])
        await service.send_message(
            ticket_id=ticket.id,
            sender_id=user.id,
            text=message,
            file=file if file and file.filename else None,
            is_from_moderator=False
        )
        return RedirectResponse(
            url=f'/sirius.achievements/support/{ticket.id}?toast_msg={quote("Обращение создано")}&toast_type=success',
            status_code=302
        )
    except ValueError as e:
        return RedirectResponse(
            url=f'/sirius.achievements/support?toast_msg={quote(str(e))}&toast_type=error',
            status_code=302
        )


@router.get('/support/{ticket_id}', response_class=HTMLResponse, name='admin.support.chat')
async def support_chat(request: Request, ticket_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse(url='/sirius.achievements/login', status_code=302)

    ticket_repo = SupportTicketRepository(db)
    ticket = await ticket_repo.find_with_messages(ticket_id)

    if not ticket or ticket.user_id != user.id:
        return RedirectResponse(url='/sirius.achievements/support', status_code=302)

    return templates.TemplateResponse('support/chat.html', {
        'request': request,
        'user': user,
        'ticket': ticket
    })


@router.post('/support/{ticket_id}/send', name='admin.support.send', dependencies=[Depends(validate_csrf)])
async def send_message(
        request: Request,
        ticket_id: int,
        text: str = Form(None),
        file: UploadFile = File(None),
        db: AsyncSession = Depends(get_db),
        service: SupportService = Depends(get_support_service)
):
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse(url='/sirius.achievements/login', status_code=302)

    ticket_repo = SupportTicketRepository(db)
    ticket = await ticket_repo.find(ticket_id)

    if not ticket or ticket.user_id != user.id:
        return RedirectResponse(url='/sirius.achievements/support', status_code=302)

    try:
        await service.send_message(
            ticket_id=ticket_id,
            sender_id=user.id,
            text=text,
            file=file if file and file.filename else None,
            is_from_moderator=False
        )
    except ValueError as e:
        return RedirectResponse(
            url=f'/sirius.achievements/support/{ticket_id}?toast_msg={quote(str(e))}&toast_type=error',
            status_code=302
        )

    return RedirectResponse(url=f'/sirius.achievements/support/{ticket_id}', status_code=302)
