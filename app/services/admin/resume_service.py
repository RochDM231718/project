import os
import httpx
import asyncio
import easyocr
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.achievement import Achievement
from app.models.user import Users
from app.models.enums import AchievementStatus

_ocr_reader = None


def get_ocr_reader():
    global _ocr_reader
    if _ocr_reader is None:
        _ocr_reader = easyocr.Reader(
            ['ru', 'en'],
            gpu=False,
            model_storage_directory='/app/models'
        )
    return _ocr_reader


class ResumeService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_resume(self, user_id: int, force_regenerate: bool = False) -> str:
        user = await self.db.get(Users, user_id)
        if not user:
            return "Пользователь не найден."

        if user.resume_text and not force_regenerate:
            return user.resume_text

        stmt = select(Achievement).filter(
            Achievement.user_id == user_id,
            Achievement.status == AchievementStatus.APPROVED
        )
        achievements = (await self.db.execute(stmt)).scalars().all()

        if not achievements:
            return "У пользователя пока нет подтвержденных достижений для генерации резюме."

        # Формируем имя целевого студента
        student_name = f"{user.first_name} {user.last_name}"
        combined_text = f"Студент: {student_name}\n\n"
        loop = asyncio.get_running_loop()

        for ach in achievements:
            if ach.file_path:
                full_file_path = Path("static") / ach.file_path
                ext = full_file_path.suffix.lower()

                if full_file_path.is_file() and ext in ['.jpg', '.jpeg', '.png', '.webp']:
                    try:
                        reader = get_ocr_reader()

                        ocr_results = await loop.run_in_executor(
                            None,
                            lambda: reader.readtext(str(full_file_path), detail=0, paragraph=True)
                        )
                        extracted_text = "\n".join(ocr_results)
                        text_from_ocr = f"Название: {ach.title}\nРаспознанный текст из грамоты:\n{extracted_text}"
                    except Exception as e:
                        print(f"Ошибка OCR для файла {ach.file_path}: {e}")
                        text_from_ocr = f"Название: {ach.title}. Уровень: {ach.level.value if hasattr(ach.level, 'value') else ach.level}."
                else:
                    text_from_ocr = f"Название: {ach.title}. Уровень: {ach.level.value if hasattr(ach.level, 'value') else ach.level}."
            else:
                text_from_ocr = f"Название: {ach.title} (файл отсутствует)."

            combined_text += f"--- Документ ---\n{text_from_ocr}\n\n"

        # Передаем имя студента в ИИ
        resume_result = await self._call_yandex_gpt(combined_text, student_name)

        user.resume_text = resume_result
        await self.db.commit()

        return resume_result

    async def _call_yandex_gpt(self, combined_text: str, target_name: str) -> str:
        api_key = os.getenv("YANDEX_API_KEY")
        folder_id = os.getenv("YANDEX_FOLDER_ID")

        if not api_key or not folder_id:
            await asyncio.sleep(2)
            return (
                f"🤖 [Демо-режим AI]\n"
                f"На основе {combined_text.count('--- Документ ---')} документов сгенерировано драфт-резюме:\n\n"
                f"Студент {target_name} имеет подтвержденные достижения. Рекомендуется для участия в профильных программах.\n\n"
                f"[ДЛЯ РАЗРАБОТЧИКА]: Распознанный текст переданный в модель:\n{combined_text}\n"
                f"(Для реального текста настройте YANDEX_API_KEY в .env)"
            )

        prompt = {
            "modelUri": f"gpt://{folder_id}/yandexgpt",  # Используем более умную модель (без -lite)
            "completionOptions": {
                "stream": False,
                "temperature": 0.1,  # Минимальная температура, чтобы ИИ был строгим и не фантазировал
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
                return f"Ошибка при обращении к ИИ: {str(e)}"