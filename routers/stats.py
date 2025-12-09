from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models import Task
from database import get_async_session
from datetime import datetime, timezone
from typing import List, Dict, Any

router = APIRouter(
    prefix='/stats',
    tags=["statistics"]
)

# Существующая статистика (немного обновлена)
@router.get("/", response_model=Dict[str, Any])
async def get_tasks_stats(db: AsyncSession = Depends(get_async_session)) -> Dict[str, Any]:
    result = await db.execute(select(Task))
    tasks = result.scalars().all()
    
    total_tasks = len(tasks)
    by_quadrant = {"Q1": 0, "Q2": 0, "Q3": 0, "Q4": 0}
    by_status = {"completed": 0, "pending": 0}
    
    # Статистика по дедлайнам
    deadlines_stats = {
        "with_deadline": 0,
        "without_deadline": 0,
        "urgent": 0,  # <= 3 дня
        "overdue": 0,  # просроченные
    }
    
    for task in tasks:
        if task.quadrant in by_quadrant:
            by_quadrant[task.quadrant] += 1
        
        if task.completed:
            by_status["completed"] += 1
        else:
            by_status["pending"] += 1
        
        # Статистика по дедлайнам
        if task.deadline_at:
            deadlines_stats["with_deadline"] += 1
            
            # Проверяем срочность
            if task.calculate_is_urgent():
                deadlines_stats["urgent"] += 1
            
            # Проверяем просроченность
            if task.days_until_deadline() is not None and task.days_until_deadline() < 0:
                deadlines_stats["overdue"] += 1
        else:
            deadlines_stats["without_deadline"] += 1
    
    return {
        "total_tasks": total_tasks,
        "by_quadrant": by_quadrant,
        "by_status": by_status,
        "deadlines": deadlines_stats
    }

# НОВЫЙ ENDPOINT: статистика по дедлайнам для незавершенных задач
@router.get("/deadlines", response_model=List[Dict[str, Any]])
async def get_pending_tasks_with_deadlines(
    db: AsyncSession = Depends(get_async_session)
) -> List[Dict[str, Any]]:
    """
    Возвращает список незавершенных задач с дедлайнами,
    отсортированный по оставшемуся времени.
    """
    result = await db.execute(
        select(Task).where(
            (Task.completed == False) &
            (Task.deadline_at.isnot(None))
        ).order_by(Task.deadline_at)
    )
    tasks = result.scalars().all()
    
    pending_tasks = []
    for task in tasks:
        pending_tasks.append({
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "created_at": task.created_at,
            "deadline_at": task.deadline_at,
            "days_until_deadline": task.days_until_deadline(),
            "is_urgent": task.calculate_is_urgent(),
            "quadrant": task.quadrant
        })
    
    return pending_tasks

# НОВЫЙ ENDPOINT: задачи, требующие срочного внимания
@router.get("/urgent", response_model=List[Dict[str, Any]])
async def get_urgent_tasks(
    db: AsyncSession = Depends(get_async_session)
) -> List[Dict[str, Any]]:
    """
    Возвращает список срочных задач (дедлайн <= 3 дня).
    """
    result = await db.execute(select(Task))
    all_tasks = result.scalars().all()
    
    urgent_tasks = []
    for task in all_tasks:
        if task.calculate_is_urgent() and not task.completed:
            urgent_tasks.append({
                "id": task.id,
                "title": task.title,
                "description": task.description,
                "deadline_at": task.deadline_at,
                "days_until_deadline": task.days_until_deadline(),
                "quadrant": task.quadrant
            })
    
    # Сортируем по срочности (меньше дней = более срочно)
    urgent_tasks.sort(key=lambda x: x["days_until_deadline"] if x["days_until_deadline"] is not None else float('inf'))
    
    return urgent_tasks