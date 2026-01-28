from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.models.enums import AchievementStatus

class AchievementBase(BaseModel):
    title: str
    description: Optional[str] = None

class AchievementCreate(AchievementBase):
    pass

class AchievementOut(AchievementBase):
    id: int
    user_id: int
    file_path: str
    preview_path: Optional[str]
    status: AchievementStatus
    created_at: datetime

    class Config:
        from_attributes = True