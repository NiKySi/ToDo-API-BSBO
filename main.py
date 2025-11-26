from fastapi import FastAPI, HTTPException
from typing import List, Dict, Any, Optional
from datetime import datetime

app = FastAPI(
    title="ToDo лист API",
    description="API для управления задачами с использованием матрицы Эйзенхауэра",
    version="1.0.0",
    contact={
        "name": "Сагдиева Вероника Борисовна",
    }
)

# Временное хранилище (позже будет заменено на PostgreSQL)
tasks_db: List[Dict[str, Any]] = [
    {
        "id": 1,
        "title": "Сдать проект по FastAPI",
        "description": "Завершить разработку API и написать документацию",
        "is_important": True,
        "is_urgent": True,
        "quadrant": "Q1",
        "completed": False,
        "created_at": datetime.now()
    },
    {
        "id": 2,
        "title": "Изучить SQLAlchemy",
        "description": "Прочитать документацию и попробовать примеры",
        "is_important": True,
        "is_urgent": False,
        "quadrant": "Q2",
        "completed": False,
        "created_at": datetime.now()
    },
    {
        "id": 3,
        "title": "Сходить на лекцию",
        "description": None,
        "is_important": False,
        "is_urgent": True,
        "quadrant": "Q3",
        "completed": False,
        "created_at": datetime.now()
    },
    {
        "id": 4,
        "title": "Посмотреть сериал",
        "description": "Новый сезон любимого сериала",
        "is_important": False,
        "is_urgent": False,
        "quadrant": "Q4",
        "completed": True,
        "created_at": datetime.now()
    },
]

@app.get("/")
async def welcome() -> dict:
    return {
        "message": "Привет, студент!", 
        "api_title": app.title, 
        "api_description": app.description, 
        "api_version": app.version, 
        "api_author": app.contact["name"] if app.contact else "Не указан"
    }

@app.get("/tasks") 
async def get_all_tasks() -> dict: 
    return { 
        "count": len(tasks_db),
        "tasks": tasks_db
    }

@app.get("/tasks/stats")
async def get_tasks_stats() -> dict:
    by_quadrant = {"Q1": 0, "Q2": 0, "Q3": 0, "Q4": 0}
    by_status = {"completed": 0, "pending": 0}
    
    for task in tasks_db:
        quadrant = task["quadrant"]
        by_quadrant[quadrant] += 1
        
        if task["completed"]:
            by_status["completed"] += 1
        else:
            by_status["pending"] += 1
    
    return {
        "total_tasks": len(tasks_db),
        "by_quadrant": by_quadrant,
        "by_status": by_status
    }

@app.get("/tasks/search")
async def search_tasks(q: str = None):  # Значение по умолчанию None
    # Проверяем, передан ли параметр q
    if q is None:
        raise HTTPException(
            status_code=400,
            detail="Необходимо указать поисковый запрос. Используйте: /tasks/search?q=ваш_запрос"
        )
    
    # Проверяем длину запроса
    if len(q) < 2:
        raise HTTPException(
            status_code=400,
            detail="Поисковый запрос должен содержать минимум 2 символа"
        )
    
    # Ищем задачи, содержащие запрос в title или description
    filtered_tasks = [
        task
        for task in tasks_db
        if (q.lower() in task["title"].lower() or 
            (task["description"] and q.lower() in task["description"].lower()))
    ]
    
    return {
        "query": q,
        "count": len(filtered_tasks),
        "tasks": filtered_tasks
    }

@app.get("/tasks/status/{status}")
async def get_tasks_by_status(status: str) -> dict:
    if status not in ["completed", "pending"]:
        raise HTTPException(
            status_code=400,
            detail="Неверный статус. Используйте: completed или pending"
        )
    
    is_completed = (status == "completed")
    
    filtered_tasks = [
        task
        for task in tasks_db
        if task["completed"] == is_completed
    ]
    
    return {
        "status": status,
        "count": len(filtered_tasks),
        "tasks": filtered_tasks
    }

@app.get("/tasks/quadrant/{quadrant}") 
async def get_tasks_by_quadrant(quadrant: str) -> dict: 
    if quadrant not in ["Q1", "Q2", "Q3", "Q4"]: 
        raise HTTPException(
            status_code=400, 
            detail="Неверный квадрант. Используйте: Q1, Q2, Q3, Q4"  
        ) 
    
    filtered_tasks = [ 
        task                          
        for task in tasks_db          
        if task["quadrant"] == quadrant  
    ] 
    
    return { 
        "quadrant": quadrant, 
        "count": len(filtered_tasks), 
        "tasks": filtered_tasks 
    }

@app.get("/tasks/{task_id}")
async def get_task_by_id(task_id: int) -> dict:
    for task in tasks_db:
        if task["id"] == task_id:
            return task
    
    raise HTTPException(
        status_code=404,
        detail=f"Задача с ID {task_id} не найдена"
    )