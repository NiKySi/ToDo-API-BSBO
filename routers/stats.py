from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from models import Task, User
from database import get_async_session
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from dependencies import get_current_user

router = APIRouter(
    prefix='/stats',
    tags=["statistics"]
)

# Вспомогательная функция для расчета срочности
def calculate_is_urgent(deadline_at: datetime | None) -> bool:
    """
    Рассчитывает срочность задачи на основе дедлайна.
    Задача считается срочной, если до дедлайна осталось <= 3 дня.
    """
    if deadline_at is None:
        return False
    
    now = datetime.now(timezone.utc)
    time_left = deadline_at - now
    
    # Срочно, если осталось МЕНЬШЕ 3 дней (259200 секунд = 3 дня)
    return time_left.total_seconds() <= 259200

# Вспомогательная функция для расчета дней до дедлайна
def days_until_deadline(deadline_at: datetime | None) -> int | None:
    """
    Возвращает количество дней до дедлайна.
    Положительное число - дней осталось.
    Отрицательное - дедлайн просрочен.
    None - дедлайн не установлен.
    """
    if deadline_at is None:
        return None
    
    now = datetime.now(timezone.utc)
    time_left = deadline_at - now
    
    # Используем days для целых дней разницы
    return time_left.days

# Общая статистика (С УЧЕТОМ АВТОРИЗАЦИИ)
@router.get("/", response_model=Dict[str, Any])
async def get_tasks_stats(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Получить общую статистику задач.
    Администраторы видят статистику по всем задачам.
    Обычные пользователи видят статистику только по своим задачам.
    """
    
    # Определяем условия фильтрации в зависимости от роли
    if current_user.role.value == "admin":
        # Администраторы видят все задачи
        total_result = await db.execute(select(func.count(Task.id)))
        tasks_query = select(Task)
    else:
        # Обычные пользователи видят только свои задачи
        total_result = await db.execute(
            select(func.count(Task.id)).where(Task.user_id == current_user.id)
        )
        tasks_query = select(Task).where(Task.user_id == current_user.id)
    
    total_tasks = total_result.scalar()
    
    # Получаем задачи для детальной статистики
    result = await db.execute(tasks_query)
    tasks = result.scalars().all()
    
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
            if calculate_is_urgent(task.deadline_at):
                deadlines_stats["urgent"] += 1
            
            # Проверяем просроченность
            days = days_until_deadline(task.deadline_at)
            if days is not None and days < 0:
                deadlines_stats["overdue"] += 1
        else:
            deadlines_stats["without_deadline"] += 1
    
    # Расчет процентов завершения
    completion_rate = (by_status["completed"] / total_tasks * 100) if total_tasks > 0 else 0
    
    return {
        "total_tasks": total_tasks,
        "by_quadrant": by_quadrant,
        "by_status": by_status,
        "deadlines": deadlines_stats,
        "completion_rate": round(completion_rate, 2),
        "user_info": {
            "user_id": current_user.id,
            "role": current_user.role.value,
            "nickname": current_user.nickname
        }
    }

# Статистика по дедлайнам для незавершенных задач (С УЧЕТОМ АВТОРИЗАЦИИ)
@router.get("/deadlines", response_model=List[Dict[str, Any]])
async def get_pending_tasks_with_deadlines(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    Возвращает список незавершенных задач с дедлайнами,
    отсортированный по оставшемуся времени.
    Администраторы видят все задачи, пользователи - только свои.
    """
    
    # Определяем условия фильтрации в зависимости от роли
    if current_user.role.value == "admin":
        query = select(Task).where(
            (Task.completed == False) &
            (Task.deadline_at.isnot(None))
        ).order_by(Task.deadline_at)
    else:
        query = select(Task).where(
            Task.user_id == current_user.id,
            (Task.completed == False) &
            (Task.deadline_at.isnot(None))
        ).order_by(Task.deadline_at)
    
    result = await db.execute(query)
    tasks = result.scalars().all()
    
    pending_tasks = []
    for task in tasks:
        pending_tasks.append({
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "created_at": task.created_at,
            "deadline_at": task.deadline_at,
            "days_until_deadline": days_until_deadline(task.deadline_at),
            "is_urgent": calculate_is_urgent(task.deadline_at),
            "quadrant": task.quadrant,
            "user_id": task.user_id,
            "is_own_task": task.user_id == current_user.id  # Показывает, является ли задача своей
        })
    
    return pending_tasks

# Срочные задачи (С УЧЕТОМ АВТОРИЗАЦИИ)
@router.get("/urgent", response_model=List[Dict[str, Any]])
async def get_urgent_tasks(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    Возвращает список срочных задач (дедлайн <= 3 дня).
    Администраторы видят все срочные задачи, пользователи - только свои.
    """
    
    # Определяем условия фильтрации в зависимости от роли
    if current_user.role.value == "admin":
        query = select(Task)
    else:
        query = select(Task).where(Task.user_id == current_user.id)
    
    result = await db.execute(query)
    all_tasks = result.scalars().all()
    
    urgent_tasks = []
    for task in all_tasks:
        if calculate_is_urgent(task.deadline_at) and not task.completed:
            urgent_tasks.append({
                "id": task.id,
                "title": task.title,
                "description": task.description,
                "deadline_at": task.deadline_at,
                "days_until_deadline": days_until_deadline(task.deadline_at),
                "quadrant": task.quadrant,
                "user_id": task.user_id,
                "is_own_task": task.user_id == current_user.id  # Показывает, является ли задача своей
            })
    
    # Сортируем по срочности (меньше дней = более срочно)
    urgent_tasks.sort(key=lambda x: x["days_until_deadline"] if x["days_until_deadline"] is not None else float('inf'))
    
    return urgent_tasks

# НОВЫЙ ENDPOINT: Статистика продуктивности по дням
@router.get("/productivity", response_model=Dict[str, Any])
async def get_productivity_stats(
    days: int = 7,  # Количество дней для анализа (по умолчанию неделя)
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Статистика продуктивности за последние N дней.
    Показывает количество завершенных задач по дням.
    """
    
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=days)
    
    # Определяем условия фильтрации в зависимости от роли
    if current_user.role.value == "admin":
        daily_stats_result = await db.execute(
            select(
                func.date(Task.completed_at).label("date"),
                func.count(Task.id).label("tasks_completed")
            ).where(
                (Task.completed == True) &
                (Task.completed_at >= start_date) &
                (Task.completed_at.isnot(None))
            ).group_by(func.date(Task.completed_at))
            .order_by(func.date(Task.completed_at))
        )
    else:
        daily_stats_result = await db.execute(
            select(
                func.date(Task.completed_at).label("date"),
                func.count(Task.id).label("tasks_completed")
            ).where(
                Task.user_id == current_user.id,
                (Task.completed == True) &
                (Task.completed_at >= start_date) &
                (Task.completed_at.isnot(None))
            ).group_by(func.date(Task.completed_at))
            .order_by(func.date(Task.completed_at))
        )
    
    daily_stats = daily_stats_result.all()
    
    # Преобразуем результат в удобный формат
    daily_completions = [
        {"date": str(stat.date), "tasks_completed": stat.tasks_completed}
        for stat in daily_stats
    ]
    
    total_completed = sum(stat.tasks_completed for stat in daily_stats)
    average_daily = total_completed / days if days > 0 else 0
    
    return {
        "period_days": days,
        "start_date": start_date.isoformat(),
        "end_date": now.isoformat(),
        "daily_completions": daily_completions,
        "total_completed": total_completed,
        "average_daily": round(average_daily, 2),
        "user_role": current_user.role.value
    }

# НОВЫЙ ENDPOINT: Краткая сводка
@router.get("/summary", response_model=Dict[str, Any])
async def get_stats_summary(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Краткая сводка статистики для быстрого просмотра.
    """
    
    # Определяем условия фильтрации в зависимости от роли
    if current_user.role.value == "admin":
        # Общее количество задач
        total_result = await db.execute(select(func.count(Task.id)))
        
        # Завершенные задачи
        completed_result = await db.execute(
            select(func.count(Task.id)).where(Task.completed == True)
        )
        
        # Срочные задачи
        urgent_result = await db.execute(
            select(func.count(Task.id)).where(
                (Task.deadline_at.isnot(None)) &
                (calculate_is_urgent(Task.deadline_at)) &
                (Task.completed == False)
            )
        )
        
        # Просроченные задачи
        now = datetime.now(timezone.utc)
        overdue_result = await db.execute(
            select(func.count(Task.id)).where(
                (Task.deadline_at < now) &
                (Task.completed == False) &
                (Task.deadline_at.isnot(None))
            )
        )
    else:
        # Общее количество задач пользователя
        total_result = await db.execute(
            select(func.count(Task.id)).where(Task.user_id == current_user.id)
        )
        
        # Завершенные задачи пользователя
        completed_result = await db.execute(
            select(func.count(Task.id)).where(
                Task.user_id == current_user.id,
                Task.completed == True
            )
        )
        
        # Срочные задачи пользователя
        urgent_result = await db.execute(
            select(func.count(Task.id)).where(
                Task.user_id == current_user.id,
                (Task.deadline_at.isnot(None)) &
                (calculate_is_urgent(Task.deadline_at)) &
                (Task.completed == False)
            )
        )
        
        # Просроченные задачи пользователя
        now = datetime.now(timezone.utc)
        overdue_result = await db.execute(
            select(func.count(Task.id)).where(
                Task.user_id == current_user.id,
                (Task.deadline_at < now) &
                (Task.completed == False) &
                (Task.deadline_at.isnot(None))
            )
        )
    
    total_tasks = total_result.scalar() or 0
    completed_tasks = completed_result.scalar() or 0
    urgent_tasks = urgent_result.scalar() or 0
    overdue_tasks = overdue_result.scalar() or 0
    pending_tasks = total_tasks - completed_tasks
    
    # Расчет процентов
    completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
    
    return {
        "summary": {
            "total_tasks": total_tasks,
            "completed": completed_tasks,
            "pending": pending_tasks,
            "urgent": urgent_tasks,
            "overdue": overdue_tasks,
            "completion_rate": round(completion_rate, 2)
        },
        "user": {
            "id": current_user.id,
            "nickname": current_user.nickname,
            "role": current_user.role.value
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }