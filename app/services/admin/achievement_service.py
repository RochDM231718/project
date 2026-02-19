import os
import uuid
import shutil
from fastapi import UploadFile
from app.services.admin.base_crud_service import BaseCrudService
from app.repositories.admin.achievement_repository import AchievementRepository

# Максимальный размер файла: 10 МБ
MAX_DOC_SIZE = 10 * 1024 * 1024


class AchievementService(BaseCrudService):
    def __init__(self, repo: AchievementRepository):
        super().__init__(repo)
        self.repo = repo

    async def save_file(self, file: UploadFile) -> str:
        """
        Сохраняет файл достижения с валидацией сигнатуры (Magic Bytes).
        Защищает от загрузки exe/php/txt скриптов под видом картинок/pdf.
        """

        # Словарь допустимых сигнатур (hex)
        ALLOWED_SIGNATURES = {
            "application/pdf": b'\x25\x50\x44\x46',  # %PDF
            "image/jpeg": b'\xFF\xD8\xFF',  # JPEG start
            "image/png": b'\x89\x50\x4E\x47\x0D\x0A\x1A\x0A'  # PNG header
        }

        # 1. Читаем начало файла для проверки сигнатуры (Magic Bytes)
        # read и seek у UploadFile - асинхронные
        header = await file.read(8)
        await file.seek(0)

        is_valid = False
        detected_ext = ""

        # Проверяем сигнатуру
        for mime, signature in ALLOWED_SIGNATURES.items():
            if header.startswith(signature):
                is_valid = True
                if mime == "application/pdf":
                    detected_ext = "pdf"
                elif mime == "image/png":
                    detected_ext = "png"
                else:
                    detected_ext = "jpg"
                break

        if not is_valid:
            # Важно: если формат неверный, лучше не писать детали в ошибку для юзера,
            # но здесь для теста оставим подробности.
            raise ValueError("Недопустимый формат файла. Файл не соответствует заявленному типу (проверка подписи).")

        # 2. Проверка размера файла
        # ИСПРАВЛЕНИЕ: Обращаемся к file.file (синхронный объект),
        # так как асинхронный seek в FastAPI не всегда поддерживает аргумент 'whence' (2).
        file.file.seek(0, 2)  # Перемещаемся в конец
        file_size = file.file.tell()  # Узнаем позицию (размер)
        file.file.seek(0)  # Возвращаемся в начало

        if file_size > MAX_DOC_SIZE:
            raise ValueError(f"Файл слишком большой. Лимит: {MAX_DOC_SIZE // (1024 * 1024)} МБ.")

        # 3. Сохранение файла
        upload_dir = "static/uploads/achievements"
        os.makedirs(upload_dir, exist_ok=True)

        # Генерируем уникальное имя
        unique_name = f"{uuid.uuid4()}.{detected_ext}"
        file_path = os.path.join(upload_dir, unique_name)

        # Используем shutil для копирования содержимого из file.file в файл на диске
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        return f"uploads/achievements/{unique_name}"

    async def delete(self, id: int, user_id: int, user_role: str):
        """
        Удаление достижения с проверкой прав.
        """
        item = await self.repo.find(id)
        if not item:
            return

        is_owner = item.user_id == user_id
        is_staff = str(user_role) in ['moderator', 'super_admin', 'MODERATOR', 'SUPER_ADMIN']

        if not is_owner and not is_staff:
            raise ValueError("У вас нет прав на удаление этого файла")

        if item.file_path:
            full_path = os.path.join("static", item.file_path)
            if os.path.exists(full_path):
                try:
                    os.remove(full_path)
                except OSError:
                    pass

        await self.repo.delete(id)