from fastapi import APIRouter, HTTPException, Query, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from datetime import datetime, timedelta, timezone  # ДОБАВЛЯЕМ timezone

from schemas import TaskCreate, TaskUpdate, TaskResponse
from database import get_async_session
from models import Task

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
    from datetime import datetime, timezone
    
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

# GET ALL TASKS - Получить все задачи (без изменений)
@router.get("", response_model=List[TaskResponse])
async def get_all_tasks(
    db: AsyncSession = Depends(get_async_session)
) -> List[TaskResponse]:
    result = await db.execute(select(Task))
    tasks = result.scalars().all()
    # Используем from_orm для преобразования с расчетными полями
    return [TaskResponse.from_orm(task) for task in tasks]

# GET TASKS BY QUADRANT (без изменений)
@router.get("/quadrant/{quadrant}", response_model=List[TaskResponse])
async def get_tasks_by_quadrant(
    quadrant: str,
    db: AsyncSession = Depends(get_async_session)
) -> List[TaskResponse]:
    if quadrant not in ["Q1", "Q2", "Q3", "Q4"]:
        raise HTTPException(
            status_code=400,
            detail="Неверный квадрант. Используйте: Q1, Q2, Q3, Q4"
        )
    
    result = await db.execute(
        select(Task).where(Task.quadrant == quadrant)
    )
    tasks = result.scalars().all()
    return [TaskResponse.from_orm(task) for task in tasks]

# SEARCH TASKS (без изменений)
@router.get("/search", response_model=List[TaskResponse])
async def search_tasks(
    q: str = Query(..., min_length=2),
    db: AsyncSession = Depends(get_async_session)
) -> List[TaskResponse]:
    keyword = f"%{q.lower()}%"
    
    result = await db.execute(
        select(Task).where(
            (Task.title.ilike(keyword)) |
            (Task.description.ilike(keyword))
        )
    )
    tasks = result.scalars().all()
    
    if not tasks:
        raise HTTPException(status_code=404, detail="По данному запросу ничего не найдено")
    
    return [TaskResponse.from_orm(task) for task in tasks]

# GET TASKS BY STATUS (без изменений)
@router.get("/status/{status}", response_model=List[TaskResponse])
async def get_tasks_by_status(
    status: str,
    db: AsyncSession = Depends(get_async_session)
) -> List[TaskResponse]:
    if status not in ["completed", "pending"]:
        raise HTTPException(
            status_code=400,
            detail="Недопустимый статус. Используйте: completed или pending"
        )
    
    is_completed = (status == "completed")
    
    result = await db.execute(
        select(Task).where(Task.completed == is_completed)
    )
    tasks = result.scalars().all()
    return [TaskResponse.from_orm(task) for task in tasks]

# GET TASK BY ID (с использованием from_orm)
@router.get("/{task_id}", response_model=TaskResponse)
async def get_task_by_id(
    task_id: int,
    db: AsyncSession = Depends(get_async_session)
) -> TaskResponse:
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    
    return TaskResponse.from_orm(task)

# POST - СОЗДАНИЕ НОВОЙ ЗАДАЧИ (ИЗМЕНЕНА ЛОГИКА)
@router.post("/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    task: TaskCreate,
    db: AsyncSession = Depends(get_async_session)
) -> TaskResponse:
    # Определяем квадрант на основе важности и дедлайна
    quadrant = calculate_quadrant(task.is_important, task.deadline_at)

    new_task = Task(
        title=task.title,
        description=task.description,
        is_important=task.is_important,
        quadrant=quadrant,
        completed=False,
        deadline_at=task.deadline_at  # Сохраняем дедлайн
    )

    db.add(new_task)
    await db.commit()
    await db.refresh(new_task)
    
    return TaskResponse.from_orm(new_task)

# PUT - ОБНОВЛЕНИЕ ЗАДАЧИ (ИЗМЕНЕНА ЛОГИКА)
@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: int,
    task_update: TaskUpdate,
    db: AsyncSession = Depends(get_async_session)
) -> TaskResponse:
    # ШАГ 1: по аналогии с GET ищем задачу по ID
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    # ШАГ 2: Получаем и обновляем только переданные поля
    update_data = task_update.model_dump(exclude_unset=True)

    # ШАГ 3: Обновить атрибуты объекта
    for field, value in update_data.items():
        setattr(task, field, value)

    # ШАГ 4: Пересчитываем квадрант, если изменились важность или дедлайн
    if "is_important" in update_data or "deadline_at" in update_data:
        task.quadrant = calculate_quadrant(task.is_important, task.deadline_at)

    await db.commit()
    await db.refresh(task)

    return TaskResponse.from_orm(task)

# PATCH - ОТМЕТИТЬ ЗАДАЧУ ВЫПОЛНЕННОЙ (без изменений)
@router.patch("/{task_id}/complete", response_model=TaskResponse)
async def complete_task(
    task_id: int,
    db: AsyncSession = Depends(get_async_session)
) -> TaskResponse:
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    task.completed = True
    task.completed_at = datetime.now(timezone.utc)  # ДОБАВЛЯЕМ timezone

    await db.commit()
    await db.refresh(task)

    return TaskResponse.from_orm(task)

# DELETE - УДАЛЕНИЕ ЗАДАЧИ (без изменений)
@router.delete("/{task_id}", status_code=status.HTTP_200_OK)
async def delete_task(
    task_id: int,
    db: AsyncSession = Depends(get_async_session)
) -> dict:
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    
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