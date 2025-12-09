from fastapi import APIRouter, HTTPException, Query, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from typing import List
from datetime import datetime, timedelta, timezone

from schemas import TaskCreate, TaskUpdate, TaskResponse
from database import get_async_session
from models import Task, User
from dependencies import get_current_user, get_current_admin

router = APIRouter(
    prefix="/tasks",
    tags=["tasks"],
    responses={404: {"description": "Task not found"}},
)

# ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ: определение квадранта на основе важности и дедлайна
def calculate_quadrant(is_important: bool, deadline_at: datetime | None) -> str:
    """
    Определяет квадрант задачи:
    - Важно + Срочно (дедлайн <= 3 дня) → Q1
    - Важно + Не срочно (дедлайн >= 3 дня или нет дедлайна) → Q2
    - Не важно + Срочно → Q3
    - Не важно + Не срочно → Q4
    """
    is_urgent = False
    if deadline_at:
        now = datetime.now(timezone.utc)
        time_left = deadline_at - now
        
        # Срочно, если осталось МЕНЕЕ 3 дней 
        # 259200 секунд = 3 дня
        is_urgent = time_left.total_seconds() <= 259200
    
    if is_important and is_urgent:
        return "Q1"
    elif is_important and not is_urgent:
        return "Q2"
    elif not is_important and is_urgent:
        return "Q3"
    else:
        return "Q4"

# ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ: расчет дней до дедлайна
def calculate_days_until_deadline(deadline_at: datetime | None) -> int | None:
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

# GET ALL TASKS - Получить все задачи (С УЧЕТОМ АВТОРИЗАЦИИ)
@router.get("", response_model=List[TaskResponse])
async def get_all_tasks(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
) -> List[TaskResponse]:
    # Администраторы видят все задачи
    if current_user.role.value == "admin":
        result = await db.execute(select(Task))
    else:
        # Обычные пользователи видят только свои задачи
        result = await db.execute(
            select(Task).where(Task.user_id == current_user.id)
        )
    
    tasks = result.scalars().all()
    
    # Добавляем вычисляемые поля
    tasks_with_days = []
    for task in tasks:
        task_dict = task.to_dict()
        task_dict['days_until_deadline'] = calculate_days_until_deadline(task.deadline_at)
        
        # Проверяем, просрочена ли задача
        if task.deadline_at is not None and calculate_days_until_deadline(task.deadline_at) is not None and calculate_days_until_deadline(task.deadline_at) < 0:
            task_dict['status_message'] = "Задача просрочена"
        else:
            task_dict['status_message'] = "Все идет по плану!"
        
        tasks_with_days.append(TaskResponse(**task_dict))
    
    return tasks_with_days

# GET TASKS BY QUADRANT (С УЧЕТОМ АВТОРИЗАЦИИ)
@router.get("/quadrant/{quadrant}", response_model=List[TaskResponse])
async def get_tasks_by_quadrant(
    quadrant: str,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
) -> List[TaskResponse]:
    """Получить задачи пользователя по квадрату"""
    if quadrant not in ["Q1", "Q2", "Q3", "Q4"]:
        raise HTTPException(
            status_code=400,
            detail="Неверный квадрант. Используйте: Q1, Q2, Q3, Q4"
        )
    
    # Администраторы видят все, пользователи - только свои
    if current_user.role.value == "admin":
        result = await db.execute(
            select(Task).where(Task.quadrant == quadrant)
        )
    else:
        result = await db.execute(
            select(Task).where(
                Task.quadrant == quadrant,
                Task.user_id == current_user.id
            )
        )
    
    tasks = result.scalars().all()
    return [TaskResponse.from_orm(task) for task in tasks]

# GET TASKS DUE TODAY (С УЧЕТОМ АВТОРИЗАЦИИ)
@router.get("/today", response_model=List[TaskResponse])
async def get_tasks_due_today(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
) -> List[TaskResponse]:
    """
    Возвращает задачи, срок выполнения которых истекает сегодня.
    """
    now = datetime.now(timezone.utc)
    today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    today_end = today_start + timedelta(days=1)
    
    # Администраторы видят все задачи, пользователи - только свои
    if current_user.role.value == "admin":
        result = await db.execute(
            select(Task).where(
                (Task.deadline_at >= today_start) &
                (Task.deadline_at < today_end) &
                (Task.completed == False)
            ).order_by(Task.deadline_at)
        )
    else:
        result = await db.execute(
            select(Task).where(
                Task.user_id == current_user.id,
                (Task.deadline_at >= today_start) &
                (Task.deadline_at < today_end) &
                (Task.completed == False)
            ).order_by(Task.deadline_at)
        )
    
    tasks = result.scalars().all()
    return [TaskResponse.from_orm(task) for task in tasks]

# SEARCH TASKS (С УЧЕТОМ АВТОРИЗАЦИИ)
@router.get("/search", response_model=List[TaskResponse])
async def search_tasks(
    q: str = Query(..., min_length=2),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
) -> List[TaskResponse]:
    keyword = f"%{q.lower()}%"
    
    # Администраторы видят все задачи
    if current_user.role.value == "admin":
        result = await db.execute(
            select(Task).where(
                (Task.title.ilike(keyword)) |
                (Task.description.ilike(keyword))
            )
        )
    else:
        # Пользователи видят только свои задачи
        result = await db.execute(
            select(Task).where(
                Task.user_id == current_user.id,
                (Task.title.ilike(keyword)) |
                (Task.description.ilike(keyword))
            )
        )
    
    tasks = result.scalars().all()
    
    if not tasks:
        raise HTTPException(status_code=404, detail="По данному запросу ничего не найдено")
    
    return [TaskResponse.from_orm(task) for task in tasks]

# GET TASKS BY STATUS (С УЧЕТОМ АВТОРИЗАЦИИ)
@router.get("/status/{status}", response_model=List[TaskResponse])
async def get_tasks_by_status(
    status: str,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
) -> List[TaskResponse]:
    if status not in ["completed", "pending"]:
        raise HTTPException(
            status_code=400,
            detail="Недопустимый статус. Используйте: completed или pending"
        )
    
    is_completed = (status == "completed")
    
    # Администраторы видят все задачи
    if current_user.role.value == "admin":
        result = await db.execute(
            select(Task).where(Task.completed == is_completed)
        )
    else:
        # Пользователи видят только свои задачи
        result = await db.execute(
            select(Task).where(
                Task.completed == is_completed,
                Task.user_id == current_user.id
            )
        )
    
    tasks = result.scalars().all()
    return [TaskResponse.from_orm(task) for task in tasks]

# GET TASK BY ID (С УЧЕТОМ АВТОРИЗАЦИИ)
@router.get("/{task_id}", response_model=TaskResponse)
async def get_task_by_id(
    task_id: int,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
) -> TaskResponse:
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    
    # Проверка прав доступа: админ или владелец задачи
    if current_user.role.value != "admin" and task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к этой задаче"
        )
    
    # Добавляем вычисляемые поля
    task_dict = task.to_dict()
    task_dict['days_until_deadline'] = calculate_days_until_deadline(task.deadline_at)
    
    # Проверяем, просрочена ли задача
    if task.deadline_at is not None and calculate_days_until_deadline(task.deadline_at) is not None and calculate_days_until_deadline(task.deadline_at) < 0:
        task_dict['status_message'] = "Задача просрочена"
    else:
        task_dict['status_message'] = "Все идет по плану!"
    
    return TaskResponse(**task_dict)

# POST - СОЗДАНИЕ НОВОЙ ЗАДАЧИ (ПРИВЯЗКА К ПОЛЬЗОВАТЕЛЮ)
@router.post("/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    task: TaskCreate,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
) -> TaskResponse:
    # Определяем квадрант на основе важности и дедлайна
    quadrant = calculate_quadrant(task.is_important, task.deadline_at)
    
    # Определяем срочность
    is_urgent = False
    if task.deadline_at:
        now = datetime.now(timezone.utc)
        time_left = task.deadline_at - now
        is_urgent = time_left.total_seconds() <= 259200

    new_task = Task(
        title=task.title,
        description=task.description,
        is_important=task.is_important,
        quadrant=quadrant,
        completed=False,
        deadline_at=task.deadline_at,
        user_id=current_user.id  # Привязываем задачу к текущему пользователю
    )
    
    # Устанавливаем вычисляемое поле срочности
    new_task.is_urgent = is_urgent

    db.add(new_task)
    await db.commit()
    await db.refresh(new_task)
    
    return TaskResponse.from_orm(new_task)

# PUT - ОБНОВЛЕНИЕ ЗАДАЧИ (С ПРОВЕРКОЙ ПРАВ ДОСТУПА)
@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: int,
    task_update: TaskUpdate,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
) -> TaskResponse:
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    
    # Проверка прав доступа: админ или владелец задачи
    if current_user.role.value != "admin" and task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к этой задаче"
        )

    update_data = task_update.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(task, field, value)

    # Пересчитываем срочность и квадрант
    if "is_important" in update_data or "deadline_at" in update_data:
        task.is_urgent = False
        if task.deadline_at:
            now = datetime.now(timezone.utc)
            time_left = task.deadline_at - now
            task.is_urgent = time_left.total_seconds() <= 259200
        task.quadrant = calculate_quadrant(task.is_important, task.deadline_at)

    await db.commit()
    await db.refresh(task)

    # Добавляем вычисляемые поля
    task_dict = task.to_dict()
    task_dict['days_until_deadline'] = calculate_days_until_deadline(task.deadline_at)
    
    return TaskResponse(**task_dict)

# PATCH - ОТМЕТИТЬ ЗАДАЧУ ВЫПОЛНЕННОЙ (С ПРОВЕРКОЙ ПРАВ ДОСТУПА)
@router.patch("/{task_id}/complete", response_model=TaskResponse)
async def complete_task(
    task_id: int,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
) -> TaskResponse:
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    
    # Проверка прав доступа: админ или владелец задачи
    if current_user.role.value != "admin" and task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к этой задаче"
        )

    task.completed = True
    task.completed_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(task)

    # Добавляем вычисляемые поля
    task_dict = task.to_dict()
    task_dict['days_until_deadline'] = calculate_days_until_deadline(task.deadline_at)
    
    return TaskResponse(**task_dict)

# DELETE - УДАЛЕНИЕ ЗАДАЧИ (С ПРОВЕРКОЙ ПРАВ ДОСТУПА)
@router.delete("/{task_id}", status_code=status.HTTP_200_OK)
async def delete_task(
    task_id: int,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
) -> dict:
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    
    # Проверка прав доступа: админ или владелец задачи
    if current_user.role.value != "admin" and task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к этой задаче"
        )
    
    deleted_task_info = {
        "id": task.id,
        "title": task.title
    }
    
    await db.delete(task)
    await db.commit()

    return {
        "message": "Задача успешно удалена",
        "id": deleted_task_info["id"],
        "title": deleted_task_info["title"]
    }