from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

# Базовые схемы остаются без изменений
class TaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)
    description: Optional[str] = None
    is_important: bool = False

# ИЗМЕНЯЕМ TaskCreate - добавляем deadline_at вместо is_urgent
class TaskCreate(TaskBase):
    # Убираем is_urgent, добавляем deadline_at
    # is_urgent: bool = False
    deadline_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

# ИЗМЕНЯЕМ TaskUpdate - добавляем deadline_at вместо is_urgent
class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=256)
    description: Optional[str] = None
    is_important: Optional[bool] = None
    # is_urgent: Optional[bool] = None  # Убираем
    deadline_at: Optional[datetime] = None  # Добавляем
    completed: Optional[bool] = None
    
    class Config:
        from_attributes = True

# ИЗМЕНЯЕМ TaskResponse - добавляем расчетные поля
class TaskResponse(TaskBase):
    id: int
    # is_urgent: bool  # Убираем, будет расчетное поле
    quadrant: str
    completed: bool
    created_at: datetime
    completed_at: Optional[datetime] = None
    deadline_at: Optional[datetime] = None  # Добавляем
    # ДОБАВЛЯЕМ расчетные поля
    is_urgent: bool  # Теперь расчетное поле
    days_until_deadline: Optional[int] = None  # Расчетное поле
    
    class Config:
        from_attributes = True
        
    # Кастомный метод для преобразования из модели SQLAlchemy
    @classmethod
    def from_orm(cls, obj):
        # Создаем словарь из объекта
        data = {
            "id": obj.id,
            "title": obj.title,
            "description": obj.description,
            "is_important": obj.is_important,
            "quadrant": obj.quadrant,
            "completed": obj.completed,
            "created_at": obj.created_at,
            "completed_at": obj.completed_at,
            "deadline_at": obj.deadline_at,
            # Расчетные поля
            "is_urgent": obj.calculate_is_urgent(),
            "days_until_deadline": obj.days_until_deadline()
        }
        return cls(**data)