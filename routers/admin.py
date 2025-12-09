from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Dict, Any
from pydantic import BaseModel

from database import get_async_session
from models import User, Task
from dependencies import get_current_admin
from schemas_auth import UserResponse

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
)

# Схема для ответа с количеством задач
class UserWithTasksResponse(BaseModel):
    id: int
    nickname: str
    email: str
    role: str
    task_count: int
    completed_tasks: int
    pending_tasks: int
    
    class Config:
        from_attributes = True

@router.get("/users", response_model=List[UserWithTasksResponse])
async def get_all_users(
    db: AsyncSession = Depends(get_async_session),
    admin: User = Depends(get_current_admin)
) -> List[UserWithTasksResponse]:
    """
    Получить список всех пользователей с количеством их задач.
    Доступно только администраторам.
    """
    # Получаем всех пользователей
    result = await db.execute(select(User))
    users = result.scalars().all()
    
    users_with_stats = []
    
    for user in users:
        # Считаем общее количество задач пользователя
        total_result = await db.execute(
            select(func.count(Task.id)).where(Task.user_id == user.id)
        )
        total_tasks = total_result.scalar() or 0
        
        # Считаем завершенные задачи
        completed_result = await db.execute(
            select(func.count(Task.id)).where(
                Task.user_id == user.id,
                Task.completed == True
            )
        )
        completed_tasks = completed_result.scalar() or 0
        
        # Считаем невыполненные задачи
        pending_tasks = total_tasks - completed_tasks
        
        users_with_stats.append({
            "id": user.id,
            "nickname": user.nickname,
            "email": user.email,
            "role": user.role.value,
            "task_count": total_tasks,
            "completed_tasks": completed_tasks,
            "pending_tasks": pending_tasks
        })
    
    return users_with_stats

@router.get("/users/{user_id}/tasks", response_model=List[Dict[str, Any]])
async def get_user_tasks(
    user_id: int,
    db: AsyncSession = Depends(get_async_session),
    admin: User = Depends(get_current_admin)
) -> List[Dict[str, Any]]:
    """
    Получить все задачи конкретного пользователя.
    Доступно только администраторам.
    """
    # Проверяем существование пользователя
    user_result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = user_result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=404,
            detail="Пользователь не найден"
        )
    
    # Получаем задачи пользователя
    tasks_result = await db.execute(
        select(Task).where(Task.user_id == user_id)
    )
    tasks = tasks_result.scalars().all()
    
    # Преобразуем задачи в словари
    tasks_list = []
    for task in tasks:
        task_dict = task.to_dict()
        # Добавляем вычисляемые поля
        from datetime import datetime, timezone
        if task.deadline_at:
            now = datetime.now(timezone.utc)
            days_left = (task.deadline_at - now).days
            task_dict["days_until_deadline"] = days_left
            task_dict["is_overdue"] = days_left < 0 and not task.completed
        else:
            task_dict["days_until_deadline"] = None
            task_dict["is_overdue"] = False
        
        tasks_list.append(task_dict)
    
    return tasks_list