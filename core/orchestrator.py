"""Orchestrator Core Module for Meow OS.

Coordinates agent workflows, dispatching intents to appropriate sub-agents,
and synthesizing multi-agent responses.
"""

from __future__ import annotations
import logging
from typing import Dict, Any, Callable, List, Optional
from enum import Enum
import traceback

logger = logging.getLogger(__name__)

class IntentCategory(str, Enum):
    SCHEDULE = "schedule"
    TASK = "task"
    MEMORY = "memory"
    PROJECT = "project"
    OPPORTUNITY = "opportunity"
    CAREER = "career"
    ACADEMIC = "academic"
    BRIEFING = "briefing"
    SEARCH = "search"
    GENERAL = "general"

class Orchestrator:
    def __init__(self):
        self.agents: Dict[IntentCategory, List[Callable]] = {cat: [] for cat in IntentCategory}
        
    def register_agent(self, category: IntentCategory, handler: Callable):
        """Register an agent capability handler for a specific intent category."""
        if handler not in self.agents[category]:
            self.agents[category].append(handler)
            logger.info(f"Registered agent handler for {category.value}")

    def classify_intent(self, text: str) -> IntentCategory:
        """Classify user input into an IntentCategory. 
        In Phase 2, this will use an LLM router.
        """
        text = text.lower()
        if any(w in text for w in ["schedule", "plan", "time", "calendar"]):
            return IntentCategory.SCHEDULE
        if any(w in text for w in ["task", "todo", "done"]):
            return IntentCategory.TASK
        if any(w in text for w in ["remember", "recall", "memory", "what was"]):
            return IntentCategory.MEMORY
        if any(w in text for w in ["nvidia", "career", "resume", "intern"]):
            return IntentCategory.CAREER
        if any(w in text for w in ["course", "assignment", "exam", "grade"]):
            return IntentCategory.ACADEMIC
        if any(w in text for w in ["opportunity", "hackathon", "competition"]):
            return IntentCategory.OPPORTUNITY
        if any(w in text for w in ["briefing", "summary", "morning"]):
            return IntentCategory.BRIEFING
            
        return IntentCategory.GENERAL

    def process_request(self, text: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Classify and dispatch a user request to appropriate agents."""
        intent = self.classify_intent(text)
        logger.info(f"Classified request as intent: {intent.value}")
        
        return self.run_workflow(intent, text, context or {})

    def run_workflow(self, intent: IntentCategory, payload: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute all agents registered for the given intent."""
        handlers = self.agents.get(intent, [])
        if not handlers:
            # Fallback to general if no specific handlers
            handlers = self.agents.get(IntentCategory.GENERAL, [])
            
        if not handlers:
            return {
                "status": "error", 
                "message": f"No agents configured to handle intent {intent.value}"
            }
            
        results = []
        errors = []
        
        # Fan-out to agents
        for handler in handlers:
            try:
                res = handler(payload, context)
                results.append({"handler": handler.__name__, "result": res})
            except Exception as e:
                logger.error(f"Agent {handler.__name__} failed: {e}")
                logger.debug(traceback.format_exc())
                errors.append({"handler": handler.__name__, "error": str(e)})
                
        # Synthesis
        return {
            "status": "success" if not errors else "partial_success" if results else "error",
            "intent": intent.value,
            "results": results,
            "errors": errors
        }

