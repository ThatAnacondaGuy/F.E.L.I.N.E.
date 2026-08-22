"""Planner Core Module for Meow OS.

Provides logic for scheduling, detecting conflicts, and finding available
time slots within the user's constraints and routines.
"""

from __future__ import annotations
import datetime
from typing import List, Dict, Any, Tuple
from database.models import UserProfileModel, TaskModel, EventModel, ScheduleBlock

class TimeSlot:
    def __init__(self, start: datetime.datetime, end: datetime.datetime):
        self.start = start
        self.end = end
        
    def duration(self) -> datetime.timedelta:
        return self.end - self.start
        
    def __repr__(self) -> str:
        return f"TimeSlot({self.start.isoformat()} to {self.end.isoformat()})"

class Planner:
    def __init__(self, profile: UserProfileModel):
        self.profile = profile
        self.constraints = profile.constraints
        self.min_buffer = datetime.timedelta(minutes=self.constraints.get("min_buffer_minutes", 15))
        self.max_deep_work = datetime.timedelta(hours=self.constraints.get("max_deep_work_block_hours", 2.5))
        
    def _parse_time(self, time_str: str) -> datetime.time:
        """Parse HH:MM to datetime.time."""
        h, m = map(int, time_str.split(":"))
        return datetime.time(hour=h, minute=m)
        
    def _get_day_name(self, d: datetime.date) -> str:
        return d.strftime("%a").lower()[:3]
        
    def get_schedule_blocks(self, date: datetime.date) -> List[Tuple[datetime.datetime, datetime.datetime, ScheduleBlock]]:
        """Return the schedule blocks active on a specific date."""
        day_name = self._get_day_name(date)
        blocks_for_day = []
        for block in self.profile.schedule_blocks:
            if day_name in block.days:
                start_t = self._parse_time(block.start)
                end_t = self._parse_time(block.end)
                
                start_dt = datetime.datetime.combine(date, start_t)
                end_dt = datetime.datetime.combine(date, end_t)
                
                if end_t <= start_t:
                    # spans midnight
                    end_dt += datetime.timedelta(days=1)
                    
                blocks_for_day.append((start_dt, end_dt, block))
        
        return sorted(blocks_for_day, key=lambda x: x[0])

    def find_available_slots(self, date: datetime.date, events: List[EventModel]) -> List[TimeSlot]:
        """Find true available timeslots, subtracting fixed routines and calendar events."""
        blocks = self.get_schedule_blocks(date)
        
        day_start = datetime.datetime.combine(date, datetime.time(0, 0))
        day_end = day_start + datetime.timedelta(days=1)
        
        # Start with full day
        available_slots = [TimeSlot(day_start, day_end)]
        
        # Remove fixed schedule blocks (sleep, college)
        for bs, be, block in blocks:
            if block.is_fixed or block.is_dnd:
                available_slots = self._subtract_time(available_slots, bs, be)
                
        # Remove events
        for e in events:
            if e.start_at and e.end_at and (e.is_fixed or e.event_type == 'meeting'):
                # Add buffer around events
                es = e.start_at - self.min_buffer
                ee = e.end_at + self.min_buffer
                available_slots = self._subtract_time(available_slots, es, ee)
                
        # Filter tiny slots
        return [s for s in available_slots if s.duration() >= datetime.timedelta(minutes=30)]

    def _subtract_time(self, slots: List[TimeSlot], start: datetime.datetime, end: datetime.datetime) -> List[TimeSlot]:
        new_slots = []
        for s in slots:
            # no overlap
            if end <= s.start or start >= s.end:
                new_slots.append(s)
            else:
                if s.start < start:
                    new_slots.append(TimeSlot(s.start, start))
                if end < s.end:
                    new_slots.append(TimeSlot(end, s.end))
        return new_slots

    def detect_conflicts(self, events: List[EventModel]) -> List[Dict[str, Any]]:
        """Identify overlapping events."""
        conflicts = []
        sorted_events = [e for e in events if e.start_at and e.end_at]
        sorted_events.sort(key=lambda e: e.start_at)
        
        for i in range(len(sorted_events) - 1):
            e1 = sorted_events[i]
            e2 = sorted_events[i+1]
            if e2.start_at < e1.end_at:
                conflicts.append({
                    "e1": e1,
                    "e2": e2,
                    "overlap": (min(e1.end_at, e2.end_at) - max(e1.start_at, e2.start_at)).total_seconds() / 60
                })
        return conflicts

    def resolve_conflicts(self, conflicts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Suggest resolutions for event conflicts."""
        resolutions = []
        for c in conflicts:
            e1 = c["e1"]
            e2 = c["e2"]
            if e1.is_fixed and not e2.is_fixed:
                resolutions.append({"action": "move", "event": e2, "reason": f"{e1.title} is fixed."})
            elif e2.is_fixed and not e1.is_fixed:
                resolutions.append({"action": "move", "event": e1, "reason": f"{e2.title} is fixed."})
            else:
                resolutions.append({"action": "warn", "events": (e1, e2), "reason": "Both events have the same flexibility. User input required."})
        return resolutions

    def create_daily_plan(self, date: datetime.date, tasks: List[TaskModel], events: List[EventModel]) -> Dict[str, Any]:
        """Create an optimal daily schedule mapping tasks into available slots."""
        available_slots = self.find_available_slots(date, events)
        schedule = []
        
        # Sort tasks by priority score
        tasks.sort(key=lambda t: t.priority_score, reverse=True)
        
        # Attempt to map tasks to slots
        for t in tasks:
            req_time = datetime.timedelta(minutes=t.estimated_minutes or 30)
            for s in available_slots:
                if s.duration() >= req_time:
                    # Place task
                    schedule.append({
                        "task_id": t.id,
                        "title": t.title,
                        "start": s.start,
                        "end": s.start + req_time
                    })
                    # Adjust slot
                    s.start = s.start + req_time + self.min_buffer
                    break
                    
        return {
            "date": date,
            "scheduled_tasks": schedule,
            "remaining_slots": available_slots,
            "unscheduled_tasks": [t.id for t in tasks if not any(st["task_id"] == t.id for st in schedule)]
        }

    def suggest_schedule(self, task: TaskModel, events: List[EventModel], horizon_days: int = 7) -> List[Dict[str, Any]]:
        """Create a multi-session plan for a large task."""
        total_time = datetime.timedelta(minutes=task.estimated_minutes or 60)
        sessions = []
        
        today = datetime.date.today()
        for i in range(horizon_days):
            d = today + datetime.timedelta(days=i)
            available_slots = self.find_available_slots(d, events)
            
            for s in available_slots:
                if total_time <= datetime.timedelta(0):
                    break
                    
                dur = min(s.duration(), self.max_deep_work, total_time)
                if dur.total_seconds() < 1800: # skip < 30min blocks
                    continue
                    
                sessions.append({
                    "date": d,
                    "start": s.start,
                    "end": s.start + dur
                })
                
                total_time -= dur
                
            if total_time <= datetime.timedelta(0):
                break
                
        return sessions

