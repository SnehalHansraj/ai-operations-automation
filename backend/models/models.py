"""
ORM models for the Ops Automation Agent.

Case          -> one row per incoming request (email/ticket/message)
AgentStep     -> one row per step the agent took while resolving a Case
                 (this is what makes the workflow "agentic" and auditable)
"""
import datetime
import uuid

from sqlalchemy import Column, String, Float, Integer, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from backend.db import Base


def gen_uuid():
    return str(uuid.uuid4())


class Case(Base):
    __tablename__ = "cases"

    id = Column(String, primary_key=True, default=gen_uuid)
    raw_text = Column(Text, nullable=False)

    # extracted / classified fields
    order_id = Column(String, nullable=True)
    issue_type = Column(String, nullable=True)
    classification_confidence = Column(Float, nullable=True)

    # outcome
    status = Column(String, default="open")  # open | resolved | escalated
    response_text = Column(Text, nullable=True)
    notified_channel = Column(String, nullable=True)

    # metrics
    processing_time_ms = Column(Float, nullable=True)
    manual_baseline_ms = Column(Float, default=300000)  # 5 min manual baseline, for comparison

    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    steps = relationship("AgentStep", back_populates="case", cascade="all, delete-orphan")


class AgentStep(Base):
    """A single step in the agent's decision trace for one case."""
    __tablename__ = "agent_steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False)
    step_number = Column(Integer, nullable=False)
    step_name = Column(String, nullable=False)      # e.g. "classify", "call_order_api"
    detail = Column(Text, nullable=True)             # human-readable detail / tool output
    duration_ms = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    case = relationship("Case", back_populates="steps")
