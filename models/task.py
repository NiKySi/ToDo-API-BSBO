from sqlalchemy import Column, Integer, Boolean, DateTime, Text, ForeignKey, String
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base

class Task(Base):
    __tablename__ = "tasks"
    
    id = Column(
        Integer,
        primary_key=True,
        index=True,
        autoincrement=True
    )
  
    title = Column(
        Text,
        nullable=False
    )
    
    description = Column(
        Text,
        nullable=True
    )
    
    is_important = Column(
        Boolean,
        nullable=False,
        default=False
    )
    
    quadrant = Column(
        String(2),
        nullable=False
    )
    
    completed = Column(
        Boolean,
        nullable=False,
        default=False
    )
    
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    
    completed_at = Column(
        DateTime(timezone=True),
        nullable=True
    )
    
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    owner = relationship(
        "User",
        back_populates="tasks"
    )

    # ДОБАВЛЯЕМ новое поле - дедлайн
    deadline_at = Column(
        DateTime(timezone=True),
        nullable=True  # Может быть NULL, если дедлайн не установлен
    )
    
    def __repr__(self) -> str:
        return f"<Task(id={self.id}, title={self.title}, quadrant={self.quadrant})>"
    
    def to_dict(self) -> dict:
        # Включаем deadline_at в словарь
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "is_important": self.is_important,
            # "is_urgent": self.is_urgent,  # Убираем
            "quadrant": self.quadrant,
            "completed": self.completed,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "deadline_at": self.deadline_at,  # Добавляем
            "user_id": self.user_id
        }
    
    # НОВЫЙ МЕТОД: проверка срочности на основе дедлайна
    def calculate_is_urgent(self) -> bool:
        """
        Рассчитывает срочность задачи на основе дедлайна.
        Задача считается срочной, если до дедлайна осталось <= 3 дня.
        (0, 1, 2 или 3 полных дня)
        """
        from datetime import datetime, timezone
        
        if self.deadline_at is None:
            return False
        
        now = datetime.now(timezone.utc)
        time_left = self.deadline_at - now
        
        # Срочно, если осталось МЕНЬШЕ 3 дней
        return time_left.total_seconds() <= 259200  

    # НОВЫЙ МЕТОД: расчет оставшихся дней
    def days_until_deadline(self) -> int | None:
        """
        Возвращает количество дней до дедлайна.
        Положительное число - дней осталось.
        Отрицательное - дедлайн просрочен.
        None - дедлайн не установлен.
        """
        from datetime import datetime, timezone
        
        if self.deadline_at is None:
            return None
        
        now = datetime.now(timezone.utc)
        time_left = self.deadline_at - now
        
        # Используем days для целых дней разницы
        return time_left.days