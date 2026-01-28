from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Enum, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.infrastructure.database import Base
from app.models.enums import AchievementStatus, AchievementCategory, AchievementLevel


class Achievement(Base):
    __tablename__ = "achievements"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    file_path = Column(String, nullable=False)

    # Новые поля
    category = Column(Enum(AchievementCategory), default=AchievementCategory.OTHER, nullable=False)
    level = Column(Enum(AchievementLevel), default=AchievementLevel.SCHOOL, nullable=False)
    points = Column(Integer, default=0)  # Баллы за достижение

    status = Column(Enum(AchievementStatus), default=AchievementStatus.PENDING)
    rejection_reason = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Связи
    user = relationship("Users", back_populates="achievements")