"""
AI Orchestrator V2 - Bidirektionales Master-Worker System mit Rollentausch

Ermöglicht die Orchestrierung von Claude Code und Codex CLI mit:
- Zielorientierung (GOAL.txt)
- Modularem Rollentausch
- Autonomer Entscheidungsfindung
- Verifikation nach Implementierung
"""

__version__ = "2.0.0"
__author__ = "BenniProbst"

from .orchestrator import Orchestrator, OrchestratorConfig
from .agents.base import IAgent, AgentResponse, AgentType
from .roles.master import MasterRole
from .roles.worker import WorkerRole
from .goal.parser import GoalParser, Goal
from .goal.validator import GoalValidator

__all__ = [
    "Orchestrator",
    "OrchestratorConfig",
    "IAgent",
    "AgentResponse",
    "AgentType",
    "MasterRole",
    "WorkerRole",
    "GoalParser",
    "Goal",
    "GoalValidator",
]
