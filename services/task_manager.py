"""
Centralized Task Manager - Tracks all active tasks across the bot.
Provides timeout management, termination, and admin visibility.
"""

import asyncio
import time
import logging
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class TaskType(Enum):
    LEECH_DOWNLOAD = "leech_download"
    LEECH_UPLOAD_TG = "leech_upload_tg"
    LEECH_UPLOAD_NC = "leech_upload_nc"
    VIDEO_DOWNLOAD = "video_download"
    AUDIO_DOWNLOAD = "audio_download"
    SUBSCRIPTION_CHECK = "subscription_check"


class TaskStatus(Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    UPLOADING = "uploading"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class TaskInfo:
    """Information about a running task."""
    task_id: str
    user_id: int
    task_type: TaskType
    status: TaskStatus = TaskStatus.PENDING
    started_at: float = field(default_factory=time.time)
    file_name: str = ""
    file_path: str = ""
    progress: float = 0.0
    speed: float = 0.0
    eta: int = 0
    message_id: Optional[int] = None
    asyncio_task: Optional[asyncio.Task] = None
    
    @property
    def elapsed(self) -> float:
        return time.time() - self.started_at
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'task_id': self.task_id,
            'user_id': self.user_id,
            'task_type': self.task_type.value,
            'status': self.status.value,
            'started_at': self.started_at,
            'elapsed': self.elapsed,
            'file_name': self.file_name,
            'file_path': self.file_path,
            'progress': self.progress,
            'speed': self.speed,
            'eta': self.eta,
        }


class TaskManager:
    """Centralized task management with timeout and termination."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._tasks: Dict[str, TaskInfo] = {}
        self._lock = asyncio.Lock()
        self._default_timeout = 1800  # 30 minutes
        self._cleanup_callbacks: List[Callable] = []
    
    @property
    def default_timeout(self) -> int:
        return self._default_timeout
    
    @default_timeout.setter
    def default_timeout(self, value: int):
        self._default_timeout = max(60, value)  # Minimum 1 minute
    
    async def register_task(
        self,
        user_id: int,
        task_type: TaskType,
        file_name: str = "",
        file_path: str = "",
        message_id: Optional[int] = None,
        asyncio_task: Optional[asyncio.Task] = None
    ) -> str:
        """Register a new task and return its ID."""
        async with self._lock:
            task_id = f"{user_id}_{int(time.time() * 1000)}"
            self._tasks[task_id] = TaskInfo(
                task_id=task_id,
                user_id=user_id,
                task_type=task_type,
                file_name=file_name,
                file_path=file_path,
                message_id=message_id,
                asyncio_task=asyncio_task
            )
            logger.info(f"Task registered: {task_id} ({task_type.value})")
            return task_id
    
    async def update_task(
        self,
        task_id: str,
        status: Optional[TaskStatus] = None,
        progress: Optional[float] = None,
        speed: Optional[float] = None,
        eta: Optional[int] = None,
        file_path: Optional[str] = None
    ):
        """Update task status and progress."""
        async with self._lock:
            if task_id not in self._tasks:
                return
            task = self._tasks[task_id]
            if status:
                task.status = status
            if progress is not None:
                task.progress = progress
            if speed is not None:
                task.speed = speed
            if eta is not None:
                task.eta = eta
            if file_path:
                task.file_path = file_path
    
    async def complete_task(self, task_id: str, success: bool = True):
        """Mark task as completed and trigger cleanup."""
        async with self._lock:
            if task_id not in self._tasks:
                return
            task = self._tasks[task_id]
            task.status = TaskStatus.COMPLETED if success else TaskStatus.FAILED
            
            # Trigger cleanup callbacks
            for callback in self._cleanup_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(task)
                    else:
                        callback(task)
                except Exception as e:
                    logger.error(f"Cleanup callback error: {e}")
            
            # Remove task after short delay
            asyncio.create_task(self._delayed_remove(task_id, 5))
    
    async def _delayed_remove(self, task_id: str, delay: float):
        """Remove task after delay."""
        await asyncio.sleep(delay)
        async with self._lock:
            self._tasks.pop(task_id, None)
    
    async def terminate_task(self, task_id: str) -> bool:
        """Terminate a running task."""
        async with self._lock:
            if task_id not in self._tasks:
                return False
            
            task = self._tasks[task_id]
            task.status = TaskStatus.CANCELLED
            
            # Cancel asyncio task if exists
            if task.asyncio_task and not task.asyncio_task.done():
                task.asyncio_task.cancel()
                logger.info(f"Task cancelled: {task_id}")
            
            # Trigger cleanup
            for callback in self._cleanup_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(task)
                    else:
                        callback(task)
                except Exception as e:
                    logger.error(f"Cleanup callback error: {e}")
            
            # Remove task
            self._tasks.pop(task_id, None)
            return True
    
    async def terminate_user_tasks(self, user_id: int) -> int:
        """Terminate all tasks for a user. Returns count."""
        count = 0
        task_ids = [tid for tid, t in self._tasks.items() if t.user_id == user_id]
        for task_id in task_ids:
            if await self.terminate_task(task_id):
                count += 1
        return count
    
    async def terminate_all_tasks(self) -> int:
        """Terminate all tasks. Returns count."""
        count = 0
        task_ids = list(self._tasks.keys())
        for task_id in task_ids:
            if await self.terminate_task(task_id):
                count += 1
        return count
    
    async def check_timeouts(self) -> List[str]:
        """Check and terminate timed-out tasks. Returns list of terminated IDs."""
        terminated = []
        now = time.time()
        
        async with self._lock:
            for task_id, task in list(self._tasks.items()):
                if task.elapsed > self._default_timeout:
                    if task.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED, 
                                           TaskStatus.CANCELLED, TaskStatus.TIMEOUT):
                        task.status = TaskStatus.TIMEOUT
                        if task.asyncio_task and not task.asyncio_task.done():
                            task.asyncio_task.cancel()
                        terminated.append(task_id)
                        logger.warning(f"Task timeout: {task_id}")
        
        return terminated
    
    def get_active_tasks(self) -> List[TaskInfo]:
        """Get all active (non-completed) tasks."""
        return [
            t for t in self._tasks.values()
            if t.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED,
                               TaskStatus.CANCELLED, TaskStatus.TIMEOUT)
        ]
    
    def get_all_tasks(self) -> List[TaskInfo]:
        """Get all tasks."""
        return list(self._tasks.values())
    
    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        """Get a specific task."""
        return self._tasks.get(task_id)
    
    def get_user_tasks(self, user_id: int) -> List[TaskInfo]:
        """Get all tasks for a user."""
        return [t for t in self._tasks.values() if t.user_id == user_id]
    
    def get_active_file_paths(self) -> List[str]:
        """Get file paths of all active tasks."""
        return [
            t.file_path for t in self.get_active_tasks()
            if t.file_path
        ]
    
    def register_cleanup_callback(self, callback: Callable):
        """Register a callback to be called on task completion."""
        self._cleanup_callbacks.append(callback)
    
    def is_path_in_use(self, file_path: str) -> bool:
        """Check if a file path is being used by an active task."""
        return any(
            t.file_path == file_path
            for t in self.get_active_tasks()
        )


# Global instance
task_manager = TaskManager()


def get_task_manager() -> TaskManager:
    """Get the global task manager instance."""
    return task_manager
