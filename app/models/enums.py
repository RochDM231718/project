from enum import Enum

class UserRole(str, Enum):
    STUDENT = "student"
    MODERATOR = "moderator"
    SUPER_ADMIN = "super_admin"

class UserStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    REJECTED = "rejected"
    DELETED = "deleted"

class AchievementStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

# --- ЭТОТ КЛАСС БЫЛ ПОТЕРЯН, ВОЗВРАЩАЕМ ЕГО ---
class UserTokenType(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"
    RESET_PASSWORD = "reset_password"
    VERIFY_EMAIL = "verify_email"

# --- НОВЫЕ КАТЕГОРИИ ---
class AchievementCategory(str, Enum):
    SPORT = "sport"
    SCIENCE = "science"
    ART = "art"
    VOLUNTEERING = "volunteering"
    OTHER = "other"

class AchievementLevel(str, Enum):
    SCHOOL = "school"
    MUNICIPAL = "municipal"
    REGIONAL = "regional"
    FEDERAL = "federal"
    INTERNATIONAL = "international"