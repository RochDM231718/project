import os
import shutil
import uuid
from fastapi import UploadFile
from app.services.admin.base_crud_service import BaseCrudService
from app.repositories.admin.achievement_repository import AchievementRepository

# Настройки ограничений
MAX_DOC_SIZE = 5 * 1024 * 1024  # 5 MB
ALLOWED_DOC_TYPES = ["application/pdf", "image/jpeg", "image/png", "image/jpg"]


class AchievementService(BaseCrudService):
    def __init__(self, repository: AchievementRepository):
        super().__init__(repository)
        self.repo = repository

    async def save_file(self, file: UploadFile) -> str:
        """Сохраняет файл достижения с валидацией"""

        # 1. Проверка типа
        if file.content_type not in ALLOWED_DOC_TYPES:
            raise ValueError("Неверный формат. Разрешены: PDF, JPG, PNG.")

        # 2. Проверка размера
        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)

        if file_size > MAX_DOC_SIZE:
            raise ValueError(f"Файл слишком большой. Лимит: {MAX_DOC_SIZE // (1024 * 1024)} МБ.")

        upload_dir = "static/uploads/achievements"
        os.makedirs(upload_dir, exist_ok=True)

        # Определяем расширение
        filename = file.filename.lower()
        if filename.endswith('.pdf'):
            ext = 'pdf'
        elif filename.endswith('.png'):
            ext = 'png'
        else:
            ext = 'jpg'

        unique_name = f"{uuid.uuid4()}.{ext}"
        file_path = os.path.join(upload_dir, unique_name)

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        return f"uploads/achievements/{unique_name}"