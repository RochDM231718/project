from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.infrastructure.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    title = Column(String, nullable=False)  # Заголовок (напр. "Достижение одобрено")
    message = Column(Text, nullable=False)  # Текст
    is_read = Column(Boolean, default=False)  # Прочитано или нет
    link = Column(String, nullable=True)  # Ссылка (куда кликать)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Связи
    user = relationship("Users", back_populates="notifications")