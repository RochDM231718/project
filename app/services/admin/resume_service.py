import os
import httpx
import asyncio
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.achievement import Achievement
from app.models.user import Users
from app.models.enums import AchievementStatus


class ResumeService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_resume(self, user_id: int, force_regenerate: bool = False) -> str:
        user = await self.db.get(Users, user_id)
        if not user:
            return "Пользователь не найден."

        # Если резюме уже есть и мы не просим перегенерировать принудительно, отдаем из кэша
        if user.resume_text and not force_regenerate:
            return user.resume_text

        # 1. Ищем одобренные достижения
        stmt = select(Achievement).filter(
            Achievement.user_id == user_id,
            Achievement.status == AchievementStatus.APPROVED
        )
        achievements = (await self.db.execute(stmt)).scalars().all()

        if not achievements:
            return "У пользователя пока нет подтвержденных достижений для генерации резюме."

        combined_text = f"Студент: {user.first_name} {user.last_name}\n\n"

        # 2. Имитируем OCR (ТУТ БУДЕТ ВАШ CHANDRA)
        for ach in achievements:
            # ЗАГЛУШКА: Пока просто берем название достижения и его уровень
            text_from_ocr = f"Название: {ach.title}. Уровень: {ach.level.value if hasattr(ach.level, 'value') else ach.level}."

            # В будущем ваш друг напишет что-то вроде:
            # text_from_ocr = chandra_extract(f"static/{ach.file_path}")

            combined_text += f"--- Документ ---\n{text_from_ocr}\n\n"

        # 3. Отправляем в YandexGPT
        resume_result = await self._call_yandex_gpt(combined_text)

        # 4. Сохраняем в БД
        user.resume_text = resume_result
        await self.db.commit()

        return resume_result

    async def _call_yandex_gpt(self, combined_text: str) -> str:
        api_key = os.getenv("YANDEX_API_KEY")
        folder_id = os.getenv("YANDEX_FOLDER_ID")

        if not api_key or not folder_id:
            # Если ключей нет, имитируем задержку и возвращаем фейковое резюме (заглушку)
            await asyncio.sleep(2)  # Имитация работы нейросети
            return (
                f"🤖 [Демо-режим AI]\n"
                f"На основе {combined_text.count('--- Документ ---')} документов сгенерировано драфт-резюме:\n\n"
                f"Студент имеет подтвержденные достижения. Рекомендуется для участия в профильных программах. "
                f"(Для реального текста настройте YANDEX_API_KEY в .env)"
            )

        prompt = {
            "modelUri": f"gpt://{folder_id}/yandexgpt-lite",
            "completionOptions": {"stream": False, "temperature": 0.3, "maxTokens": "1000"},
            "messages": [
                {"role": "system",
                 "text": "Ты составляешь профессиональное резюме для школьника/студента на основе списка его достижений. Будь краток и структурирован."},
                {"role": "user", "text": f"Сделай красивую выжимку из этих документов:\n{combined_text}"}
            ]
        }

        url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        headers = {"Content-Type": "application/json", "Authorization": f"Api-Key {api_key}"}

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, headers=headers, json=prompt, timeout=20.0)
                response.raise_for_status()
                return response.json()['result']['alternatives'][0]['message']['text']
            except Exception as e:
                return f"Ошибка при обращении к ИИ: {str(e)}"