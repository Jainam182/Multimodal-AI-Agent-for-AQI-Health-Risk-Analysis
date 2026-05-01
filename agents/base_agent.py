"""
agents/base_agent.py
─────────────────────
Abstract base. run() accepts either:
  - run(msg)         where msg is an AgentMessage (from app.py / external callers)
  - run(**kwargs)    (internal agent-to-agent calls from ReasoningAgent)
Both paths call _execute(message_id=..., **payload_kwargs).
"""

# ─── Imports ──────────────────────────────────────────────────────────────────
from __future__ import annotations
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from schemas.agent_messages import AgentMessage, AgentName, MessageStatus
from utils.logger import get_logger


# ─── Abstract base class for all agents ───────────────────────────────────────
class BaseAgent(ABC):
    # Subclasses must set this to identify themselves in inter-agent messages.
    agent_name: AgentName

    def __init__(self):
        # Per-class logger so log lines are tagged with the concrete agent name.
        self.logger = get_logger(self.__class__.__name__)

    # ─── Public entry point ───────────────────────────────────────────────────
    def run(self, msg=None, **kwargs) -> AgentMessage:
        """
        Unified entry point.
        If the first positional arg is an AgentMessage we unpack its payload
        into kwargs so _execute always receives plain keyword arguments.
        """
        # Unpack AgentMessage payload into kwargs so _execute always sees plain kwargs.
        if msg is not None and isinstance(msg, AgentMessage):
            payload = msg.payload or {}
            kwargs.update(payload)

        # ─── Timing + correlation id for this run ────────────────────────────
        start_ms  = time.perf_counter() * 1000
        message_id = str(uuid.uuid4())
        self.logger.info(f"▶ {self.agent_name.value} | id={message_id[:8]}")

        # ─── Execute subclass logic, capture errors as a structured response ──
        try:
            result = self._execute(message_id=message_id, **kwargs)
            if isinstance(result, AgentMessage):
                result.status = MessageStatus.SUCCESS
        except Exception as exc:
            self.logger.error(f"✘ {self.agent_name.value} failed: {exc}", exc_info=True)
            result = self._error_response(message_id, str(exc))

        duration_ms = time.perf_counter() * 1000 - start_ms
        self.logger.info(f"✔ {self.agent_name.value} done in {duration_ms:.1f}ms")

        # ─── Telemetry: log the handoff to SQLite (best-effort, never fatal) ─
        try:
            from data.database import db
            db.log_agent_message(
                message_id=message_id,
                source=self.agent_name.value,
                target=result.target_agent.value if result.target_agent else "",
                status=result.status.value,
                payload={},
                duration_ms=round(duration_ms, 2),
            )
        except Exception:
            pass

        return result

    # ─── Subclass contract ────────────────────────────────────────────────────
    @abstractmethod
    def _execute(self, message_id: str, **kwargs) -> AgentMessage:
        ...

    # ─── Standard error envelope returned when _execute raises ────────────────
    def _error_response(self, message_id: str, error: str) -> AgentMessage:
        return AgentMessage(
            message_id=message_id,
            source_agent=self.agent_name,
            status=MessageStatus.ERROR,
            errors=[error],
            payload={"error": error},
        )
