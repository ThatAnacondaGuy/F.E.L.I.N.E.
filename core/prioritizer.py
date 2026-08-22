"""Prioritizer Core Module for Meow OS.

Provides the scoring engine for tasks and opportunities, aligning with
user goals, career trajectory (NVIDIA), and academic course priority.
"""

from __future__ import annotations
import math
import datetime
from typing import Dict, Any, Optional
from database.models import TaskModel, OpportunityModel, CoursePriority, Priority

class Prioritizer:
    def __init__(self):
        # NVIDIA Career Keywords
        self.career_keywords = [
            "cuda", "gpu", "nvidia", "parallel", "tensorrt", 
            "deep learning", "ml", "ai", "systems programming", "c++", "linux"
        ]
        
        # Course Priority Weights
        self.course_weights = {
            "PCC301COM": 1.0,   # AI
            "MDM331COM": 0.8,   # Robotics
            "PEC321BCOM": 0.8,  # Cloud
            "PCC302COM": 0.5,   # Networks
            "PCC303COM": 0.5,   # ToC
            "ELC342COM": 0.6    # Tech Seminar
        }
        
        # Base Priority Enum Multipliers
        self.priority_multipliers = {
            Priority.LOWEST: 0.2,
            Priority.LOW: 0.4,
            Priority.MEDIUM: 0.6,
            Priority.HIGH: 0.8,
            Priority.HIGHEST: 1.0,
            Priority.CRITICAL: 1.2
        }

    def _urgency_score(self, due_date: Optional[datetime.datetime]) -> float:
        """Exponential decay based on deadline proximity."""
        if not due_date:
            return 0.1
        
        now = datetime.datetime.now()
        delta = due_date - now
        days = max(0.0, delta.total_seconds() / 86400.0)
        
        # score = e^(-0.15 * days)
        return math.exp(-0.15 * days)

    def _text_match_score(self, text: str, keywords: list[str]) -> float:
        if not text:
            return 0.0
        text = text.lower()
        matches = sum(1 for kw in keywords if kw in text)
        return min(1.0, matches * 0.2)

    def score_task(self, task: TaskModel) -> float:
        """Score a task based on urgency, importance, and alignments."""
        # Base importance
        importance = self.priority_multipliers.get(task.priority, 0.5)
        
        # Urgency
        urgency = self._urgency_score(task.due_date)
        
        # Career impact
        career_impact = self._text_match_score(task.title + " " + task.description, self.career_keywords)
        
        # Academic impact (crude keyword matching to course codes for demo)
        academic_impact = 0.0
        for code, w in self.course_weights.items():
            if code in task.title or code in task.description or task.category == code:
                academic_impact = max(academic_impact, w)
                
        # Effort inverse (less effort = higher quick-win score)
        mins = task.estimated_minutes or 60
        effort_inv = max(0.1, 1.0 - (mins / 300.0))
        
        # Weighted sum
        score = (
            (importance * 0.3) +
            (urgency * 0.3) +
            (career_impact * 0.2) +
            (academic_impact * 0.1) +
            (effort_inv * 0.1)
        )
        
        # Normalize to 0-100
        return min(100.0, max(0.0, score * 100))

    def score_opportunity(self, opp: OpportunityModel) -> Dict[str, float]:
        """Score an opportunity and return a breakdown of components."""
        text = (opp.title + " " + opp.description).lower()
        
        # NVIDIA Relevance
        nvidia_relevance = self._text_match_score(text, self.career_keywords + ["nvidia software engineer", "nvidia intern"])
        
        # Skill Relevance
        skill_relevance = min(1.0, len(opp.tags) * 0.15)
        
        # Learning Value
        learning_value = self._text_match_score(text, ["learn", "course", "tutorial", "certification", "workshop"])
        
        # Portfolio Value
        portfolio_value = self._text_match_score(text, ["hackathon", "competition", "open source", "project", "build"])
        
        # Time Feasibility
        time_feasibility = 0.5
        if opp.time_requirement_hours:
            if opp.time_requirement_hours < 5:
                time_feasibility = 0.9
            elif opp.time_requirement_hours < 20:
                time_feasibility = 0.6
            else:
                time_feasibility = 0.3
                
        # Aggregate
        career_score = (nvidia_relevance * 0.6) + (skill_relevance * 0.4)
        relevance_score = (career_score * 0.4) + (learning_value * 0.3) + (portfolio_value * 0.3)
        
        overall = min(100.0, (relevance_score * 0.7 + time_feasibility * 0.3) * 100)
        
        return {
            "overall": overall,
            "relevance_score": relevance_score * 100,
            "career_score": career_score * 100,
            "nvidia_score": nvidia_relevance * 100,
            "learning_value": learning_value * 100,
            "portfolio_value": portfolio_value * 100
        }

    def explain_score(self, task: TaskModel) -> str:
        """Provide human readable explanation of the score."""
        score = self.score_task(task)
        urgency = self._urgency_score(task.due_date)
        career = self._text_match_score(task.title + " " + task.description, self.career_keywords)
        
        reasons = []
        if urgency > 0.7:
            reasons.append("Deadline is rapidly approaching.")
        if career > 0.4:
            reasons.append("Strongly aligns with NVIDIA career track.")
        if self.priority_multipliers.get(task.priority, 0.5) >= 0.8:
            reasons.append(f"Marked as {task.priority.value} priority.")
            
        if not reasons:
            reasons.append("Standard priority task with no immediate pressing factors.")
            
        return f"Score: {score:.1f}/100. " + " ".join(reasons)

