"""
agents/base_agent.py
─────────────────────
Abstract base. run() accepts either:
  - run(msg)         where msg is an AgentMessage (from app.py / external callers)
  - run(**kwargs)    (internal agent-to-agent calls from ReasoningAgent)
Both paths call _execute(message_id=..., **payload_kwargs).
"""

from __future__ import annotations
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from schemas.agent_messages import AgentMessage, AgentName, MessageStatus
from utils.logger import get_logger


class BaseAgent(ABC):
    agent_name: AgentName

    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)

    def run(self, msg=None, **kwargs) -> AgentMessage:
        """
        Unified entry point.
        If the first positional arg is an AgentMessage we unpack its payload
        into kwargs so _execute always receives plain keyword arguments.
        """
        # Unpack AgentMessage payload into kwargs
        if msg is not None and isinstance(msg, AgentMessage):
            payload = msg.payload or {}
            kwargs.update(payload)

        start_ms  = time.perf_counter() * 1000
        message_id = str(uuid.uuid4())
        self.logger.info(f"▶ {self.agent_name.value} | id={message_id[:8]}")

        try:
            result = self._execute(message_id=message_id, **kwargs)
            if isinstance(result, AgentMessage):
                result.status = MessageStatus.SUCCESS
        except Exception as exc:
            self.logger.error(f"✘ {self.agent_name.value} failed: {exc}", exc_info=True)
            result = self._error_response(message_id, str(exc))

        duration_ms = time.perf_counter() * 1000 - start_ms
        self.logger.info(f"✔ {self.agent_name.value} done in {duration_ms:.1f}ms")

        # Optional DB logging — fail-safe
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

    @abstractmethod
    def _execute(self, message_id: str, **kwargs) -> AgentMessage:
        ...

    def _error_response(self, message_id: str, error: str) -> AgentMessage:
        return AgentMessage(
            message_id=message_id,
            source_agent=self.agent_name,
            status=MessageStatus.ERROR,
            errors=[error],
            payload={"error": error},
        )
