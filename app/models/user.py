from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.infrastructure.database import Base
from app.models.enums import UserRole, UserStatus


# !!! ВАЖНО: Добавьте этот импорт, чтобы разорвать цикличность, используем строки в relationship
# Но для SQLAlchemy лучше, если класс будет известен хотя бы как строка.
# Если возникает циклическая зависимость (Notification импортирует User, а User -> Notification),
# то импорт можно делать внутри метода или оставить строкой, НО убедиться, что Notification вообще где-то импортируется в проекте.

# В данном случае, проблема в том, что когда загружается User, SQLAlchemy пытается найти 'Notification',
# но модель Notification еще не загружена в память.

class Users(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    phone_number = Column(String, nullable=True)
    avatar_path = Column(String, nullable=True)

    role = Column(Enum(UserRole), default=UserRole.STUDENT)
    status = Column(Enum(UserStatus), default=UserStatus.PENDING)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Связи
    # Используем строковые названия классов ("Achievement", "Notification"), чтобы избежать проблем с порядком импорта
    achievements = relationship("Achievement", back_populates="user", cascade="all, delete-orphan")

    # ВОТ ЗДЕСЬ БЫЛА ОШИБКА. SQLAlchemy не мог найти класс Notification.
    # Если мы используем строковое имя "Notification", то сам файл notification.py должен быть импортирован
    # где-то в проекте (например в __init__.py или main.py), чтобы модель зарегистрировалась.

    # Самый надежный способ: импортировать TYPE_CHECKING
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")