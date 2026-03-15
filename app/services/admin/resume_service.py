import os
import httpx
import asyncio
import easyocr
import fitz  # PyMuPDF для работы с PDF
import structlog
from pathlib import Path
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sql_func

from app.models.achievement import Achievement
from app.models.user import Users
from app.models.enums import AchievementStatus

logger = structlog.get_logger()

_ocr_reader = None


def get_ocr_reader():
    global _ocr_reader
    if _ocr_reader is None:
        model_dir = os.getenv('EASYOCR_MODEL_DIR', '/app/easyocr_models')
        try:
            _ocr_reader = easyocr.Reader(
                ['ru', 'en'],
                gpu=False,
                model_storage_directory=model_dir,
                download_enabled=True,
                verbose=False
            )
        except Exception as e:
            logger.warning("EasyOCR init with download failed, retrying offline", error=str(e))
            _ocr_reader = easyocr.Reader(
                ['ru', 'en'],
                gpu=False,
                model_storage_directory=model_dir,
                download_enabled=False,
                verbose=False
            )
    return _ocr_reader


class ResumeService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def can_generate(self, user_id: int) -> dict:
        """Проверяет, может ли пользователь сгенерировать резюме."""
        user = await self.db.get(Users, user_id)
        if not user:
            return {"allowed": False, "reason": "Пользователь не найден."}

        # Считаем подтверждённые документы
        count_stmt = select(sql_func.count()).select_from(Achievement).filter(
            Achievement.user_id == user_id,
            Achievement.status == AchievementStatus.APPROVED
        )
        approved_count = (await self.db.execute(count_stmt)).scalar() or 0

        if approved_count == 0:
            return {"allowed": False, "reason": "Нет подтверждённых достижений."}

        # Если резюме ещё не генерировалось — можно
        if not user.resume_generated_at:
            return {"allowed": True, "reason": None}

        # Есть ли новые подтверждённые документы после последней генерации?
        new_stmt = select(sql_func.count()).select_from(Achievement).filter(
            Achievement.user_id == user_id,
            Achievement.status == AchievementStatus.APPROVED,
            Achievement.updated_at > user.resume_generated_at
        )
        new_count = (await self.db.execute(new_stmt)).scalar() or 0

        if new_count == 0:
            return {"allowed": False, "reason": "Нет новых подтверждённых документов с момента последней генерации."}

        return {"allowed": True, "reason": None}

    async def generate_resume(self, user_id: int, force_regenerate: bool = False, bypass_check: bool = False) -> dict:
        user = await self.db.get(Users, user_id)
        if not user:
            return {"success": False, "error": "Пользователь не найден."}

        if user.resume_text and not force_regenerate:
            return {"success": True, "resume": user.resume_text}

        # Проверка права на генерацию (bypass для админов)
        if not bypass_check:
            check = await self.can_generate(user_id)
            if not check["allowed"]:
                return {"success": False, "error": check["reason"], "resume": user.resume_text}

        stmt = select(Achievement).filter(
            Achievement.user_id == user_id,
            Achievement.status == AchievementStatus.APPROVED
        )
        achievements = (await self.db.execute(stmt)).scalars().all()

        if not achievements:
            return {"success": False, "error": "У пользователя пока нет подтвержденных достижений для генерации резюме."}

        student_name = f"{user.first_name} {user.last_name}"
        combined_text = f"Студент: {student_name}\n\n"
        loop = asyncio.get_running_loop()

        for ach in achievements:
            if ach.file_path:
                full_file_path = Path("static") / ach.file_path
                ext = full_file_path.suffix.lower()

                if full_file_path.is_file():
                    # --- ОБРАБОТКА КАРТИНОК ---
                    if ext in ['.jpg', '.jpeg', '.png', '.webp']:
                        try:
                            reader = get_ocr_reader()
                            ocr_results = await loop.run_in_executor(
                                None,
                                lambda: reader.readtext(str(full_file_path), detail=0, paragraph=True)
                            )
                            extracted_text = "\n".join(ocr_results)
                            text_from_ocr = f"Название: {ach.title}\nРаспознанный текст из грамоты:\n{extracted_text}"
                        except Exception as e:
                            logger.error("Ошибка OCR для картинки", file_path=ach.file_path, error=str(e))
                            text_from_ocr = f"Название: {ach.title}. Уровень: {ach.level.value if hasattr(ach.level, 'value') else ach.level}."

                    # --- ОБРАБОТКА PDF ---
                    elif ext == '.pdf':
                        try:
                            def process_pdf(filepath):
                                text = ""
                                # Открываем PDF файл
                                with fitz.open(filepath) as doc:
                                    for page in doc:
                                        # 1. Пробуем вытащить вшитый текст (электронный PDF)
                                        page_text = page.get_text().strip()
                                        if page_text:
                                            text += page_text + "\n"
                                        else:
                                            # 2. Если текста нет, значит это скан. Рендерим страницу в PNG!
                                            # matrix=fitz.Matrix(2, 2) увеличивает разрешение в 2 раза для лучшего распознавания
                                            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                                            img_bytes = pix.tobytes("png")

                                            # Передаем байты картинки в EasyOCR
                                            reader = get_ocr_reader()
                                            ocr_results = reader.readtext(img_bytes, detail=0, paragraph=True)
                                            text += "\n".join(ocr_results) + "\n"
                                return text

                            # Запускаем чтение PDF в фоновом потоке
                            extracted_text = await loop.run_in_executor(None, process_pdf, str(full_file_path))
                            text_from_ocr = f"Название: {ach.title}\nТекст из PDF:\n{extracted_text}"

                        except Exception as e:
                            logger.error("Ошибка чтения PDF", file_path=ach.file_path, error=str(e))
                            text_from_ocr = f"Название: {ach.title}. Уровень: {ach.level.value if hasattr(ach.level, 'value') else ach.level}."

                    # Если формат неизвестный
                    else:
                        text_from_ocr = f"Название: {ach.title}. Уровень: {ach.level.value if hasattr(ach.level, 'value') else ach.level}."
                else:
                    text_from_ocr = f"Название: {ach.title} (файл не найден на сервере)."
            else:
                text_from_ocr = f"Название: {ach.title} (файл отсутствует)."

            combined_text += f"--- Документ ---\n{text_from_ocr}\n\n"

        # Отправляем в ИИ
        resume_result = await self._call_yandex_gpt(combined_text, student_name)

        user.resume_text = resume_result
        user.resume_generated_at = datetime.now(timezone.utc)
        await self.db.commit()

        return {"success": True, "resume": resume_result}

    async def _call_yandex_gpt(self, combined_text: str, target_name: str) -> str:
        api_key = os.getenv("YANDEX_API_KEY")
        folder_id = os.getenv("YANDEX_FOLDER_ID")

        if not api_key or not folder_id:
            return self._generate_local_resume(combined_text, target_name)

        prompt = {
            "modelUri": f"gpt://{folder_id}/yandexgpt",
            "completionOptions": {
                "stream": False,
                "temperature": 0.1,
                "maxTokens": "1000"
            },
            "messages": [
                {
                    "role": "system",
                    "text": (
                        f"Ты — строгий HR-специалист. "
                        f"Твоя задача — составить краткое профессиональное резюме ТОЛЬКО для одного человека. "
                        f"Его зовут: {target_name}. "
                        f"В предоставленном тексте могут быть случайные имена других людей — полностью игнорируй их. "
                        f"Собери только те достижения и факты, которые относятся к {target_name}. "
                        f"Напиши связный текст от третьего лица (3-4 предложения). Ни в коем случае не выводи исходный сырой текст."
                    )
                },
                {
                    "role": "user",
                    "text": f"Данные из документов:\n{combined_text}"
                }
            ]
        }

        url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        headers = {"Content-Type": "application/json", "Authorization": f"Api-Key {api_key}"}

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, headers=headers, json=prompt, timeout=30.0)
                response.raise_for_status()
                return response.json()['result']['alternatives'][0]['message']['text']
            except Exception as e:
                logger.error("Yandex GPT API error", error=str(e))
                return self._generate_local_resume(combined_text, target_name)

    def _generate_local_resume(self, combined_text: str, target_name: str) -> str:
        """Generate a structured resume locally from OCR-extracted text without AI API."""
        doc_count = combined_text.count('--- Документ ---')

        # Extract document titles and texts
        documents = []
        for block in combined_text.split('--- Документ ---'):
            block = block.strip()
            if not block or block.startswith('Студент:'):
                continue
            lines = block.split('\n')
            title = ""
            text_lines = []
            for line in lines:
                line = line.strip()
                if line.startswith('Название:'):
                    title = line.replace('Название:', '').strip()
                elif line and not line.startswith('Распознанный текст') and not line.startswith('Текст из PDF'):
                    text_lines.append(line)
            documents.append({'title': title, 'text': ' '.join(text_lines)})

        # Build resume
        parts = [f"{target_name}\n"]
        parts.append(f"Подтвержденные достижения ({doc_count}):\n")

        for i, doc in enumerate(documents, 1):
            if doc['title']:
                parts.append(f"  {i}. {doc['title']}")
                if doc['text'] and len(doc['text']) > 20:
                    # Truncate long OCR text to a meaningful snippet
                    snippet = doc['text'][:200].rsplit(' ', 1)[0] if len(doc['text']) > 200 else doc['text']
                    parts.append(f"     {snippet}")
            parts.append("")

        parts.append("Резюме составлено автоматически на основе распознанных документов.")

        return '\n'.join(parts)