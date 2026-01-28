import os
import shutil
import uuid
from fastapi import UploadFile
from app.services.admin.base_crud_service import BaseCrudService
from app.repositories.admin.user_repository import UserRepository

# Настройки ограничений
MAX_AVATAR_SIZE = 2 * 1024 * 1024  # 2 MB
ALLOWED_AVATAR_TYPES = ["image/jpeg", "image/png", "image/webp", "image/jpg"]


class UserService(BaseCrudService):
    def __init__(self, repository: UserRepository):
        super().__init__(repository)
        self.repository = repository

    async def save_avatar(self, user_id: int, file: UploadFile) -> str:
        """Сохраняет аватарку с проверкой типа и размера"""

        # 1. Проверка типа файла
        if file.content_type not in ALLOWED_AVATAR_TYPES:
            raise ValueError("Неподдерживаемый формат. Используйте JPG, PNG или WEBP.")

        # 2. Проверка размера файла
        # Перемещаем курсор в конец файла, чтобы узнать размер
        file.file.seek(0, 2)
        file_size = file.file.tell()
        # Возвращаем курсор в начало для сохранения
        file.file.seek(0)

        if file_size > MAX_AVATAR_SIZE:
            raise ValueError(f"Файл слишком большой. Максимальный размер: {MAX_AVATAR_SIZE // (1024 * 1024)} МБ.")

        upload_dir = "static/uploads/avatars"
        os.makedirs(upload_dir, exist_ok=True)

        user = await self.repository.find(user_id)

        # Удаляем старую
        if user and user.avatar_path:
            old_path = os.path.join("static", user.avatar_path)
            if os.path.exists(old_path) and os.path.isfile(old_path):
                try:
                    os.remove(old_path)
                except Exception:
                    pass

        unique_name = f"avatar_{user_id}_{uuid.uuid4().hex[:8]}.jpg"
        file_path = os.path.join(upload_dir, unique_name)

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        return f"uploads/avatars/{unique_name}"