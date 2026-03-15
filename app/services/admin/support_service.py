import os
import uuid
import structlog
from datetime import datetime
from app.models.support_ticket import SupportTicket
from app.models.support_message import SupportMessage
from app.models.enums import SupportTicketStatus
from app.repositories.admin.support_repository import SupportTicketRepository, SupportMessageRepository

logger = structlog.get_logger()

UPLOAD_DIR = os.path.join("static", "uploads", "support")
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
ALLOWED_SIGNATURES = {
    b'\xff\xd8\xff': 'jpg',
    b'\x89PNG': 'png',
    b'RIFF': 'webp',
}


class SupportService:
    def __init__(self, ticket_repo: SupportTicketRepository, message_repo: SupportMessageRepository):
        self.ticket_repo = ticket_repo
        self.message_repo = message_repo
        self.db = ticket_repo.db

    async def create_ticket(self, user_id: int, subject: str) -> SupportTicket:
        ticket = SupportTicket(
            user_id=user_id,
            subject=subject,
            status=SupportTicketStatus.OPEN
        )
        self.db.add(ticket)
        await self.db.commit()
        await self.db.refresh(ticket)
        return ticket

    async def send_message(self, ticket_id: int, sender_id: int, text: str = None,
                           file=None, is_from_moderator: bool = False) -> SupportMessage:
        file_path = None
        if file and file.filename:
            file_path = await self._save_file(file, ticket_id)

        if not text and not file_path:
            raise ValueError("Сообщение должно содержать текст или файл")

        message = SupportMessage(
            ticket_id=ticket_id,
            sender_id=sender_id,
            text=text,
            file_path=file_path,
            is_from_moderator=is_from_moderator
        )
        self.db.add(message)

        # Update ticket timestamp
        ticket = await self.ticket_repo.find(ticket_id)
        if ticket:
            ticket.updated_at = datetime.utcnow()
            if is_from_moderator and ticket.status == SupportTicketStatus.OPEN:
                ticket.status = SupportTicketStatus.IN_PROGRESS

        await self.db.commit()
        await self.db.refresh(message)
        return message

    async def close_ticket(self, ticket_id: int):
        ticket = await self.ticket_repo.find(ticket_id)
        if ticket:
            ticket.status = SupportTicketStatus.CLOSED
            await self.db.commit()
        return ticket

    async def reopen_ticket(self, ticket_id: int):
        ticket = await self.ticket_repo.find(ticket_id)
        if ticket:
            ticket.status = SupportTicketStatus.OPEN
            await self.db.commit()
        return ticket

    async def _save_file(self, file, ticket_id: int) -> str:
        content = await file.read()
        await file.seek(0)

        if len(content) > MAX_FILE_SIZE:
            raise ValueError("Файл слишком большой (макс. 5 МБ)")

        header = content[:8]
        valid = False
        ext = 'bin'
        for sig, extension in ALLOWED_SIGNATURES.items():
            if header.startswith(sig):
                valid = True
                ext = extension
                break

        if not valid:
            raise ValueError("Допустимы только изображения (JPG, PNG, WEBP)")

        ticket_dir = os.path.join(UPLOAD_DIR, str(ticket_id))
        os.makedirs(ticket_dir, exist_ok=True)

        filename = f"{uuid.uuid4().hex}.{ext}"
        filepath = os.path.join(ticket_dir, filename)

        with open(filepath, "wb") as f:
            f.write(content)

        return filepath
