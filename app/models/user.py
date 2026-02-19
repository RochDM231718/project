from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.infrastructure.database import Base
from app.models.enums import UserRole, UserStatus

class Users(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    phone_number = Column(String, nullable=True)
    avatar_path = Column(String, nullable=True)

    role = Column(Enum(UserRole), default=UserRole.GUEST)
    status = Column(Enum(UserStatus), default=UserStatus.PENDING)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    failed_attempts = Column(Integer, default=0)
    blocked_until = Column(DateTime, nullable=True)

    achievements = relationship("Achievement", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    tokens = relationship("UserToken", back_populates="user", cascade="all, delete-orphan")