import logging
from typing import Callable, Any, List
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

class Job:
    def __init__(self, id: str, name: str, next_run_time: Any):
        self.id = id
        self.name = name
        self.next_run_time = next_run_time

class BackgroundScheduler:
    """Wrapper around APScheduler AsyncIOScheduler."""
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self._init_builtins()

    def _init_builtins(self):
        # We will register the actual jobs from the scheduler package when starting
        pass

    def start(self):
        self.scheduler.start()
        logger.info("Background scheduler started")

    def stop(self):
        self.scheduler.shutdown()
        logger.info("Background scheduler stopped")

    def add_job(self, func: Callable, trigger: Any, job_id: str, **kwargs):
        self.scheduler.add_job(func, trigger, id=job_id, replace_existing=True, **kwargs)

    def remove_job(self, job_id: str):
        self.scheduler.remove_job(job_id)

    def list_jobs(self) -> List[Job]:
        return [Job(id=j.id, name=j.name, next_run_time=j.next_run_time) for j in self.scheduler.get_jobs()]

    def pause(self):
        self.scheduler.pause()

    def resume(self):
        self.scheduler.resume()
