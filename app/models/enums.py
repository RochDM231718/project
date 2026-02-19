from enum import Enum

class UserRole(str, Enum):
    # Значения справа должны СТРОГО совпадать с тем, что в базе PostgreSQL
    GUEST = "GUEST"
    STUDENT = "STUDENT"
    MODERATOR = "MODERATOR"
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"  # <--- ДОБАВЛЕНА ЭТА СТРОКА

class UserStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    REJECTED = "rejected"
    DELETED = "deleted"

class AchievementStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

class UserTokenType(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"
    RESET_PASSWORD = "reset_password"
    VERIFY_EMAIL = "verify_email"

class AchievementCategory(str, Enum):
    SPORT = "Спорт"
    SCIENCE = "Наука"
    ART = "Искусство"
    VOLUNTEERING = "Волонтёрство"
    OTHER = "Другое"

class AchievementLevel(str, Enum):
    SCHOOL = "Школьный"
    MUNICIPAL = "Муниципальный"
    REGIONAL = "Региональный"
    FEDERAL = "Федеральный"
    INTERNATIONAL = "Международный"