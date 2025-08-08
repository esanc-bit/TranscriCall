from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, String, Integer, DateTime, Float
from datetime import datetime

Base = declarative_base()


class CallSession(Base):
    __tablename__ = "call_session"

    id = Column(String, primary_key=True)
    agent_id = Column(String, index=True, nullable=False)
    started_at = Column(DateTime, nullable=False)
    last_update = Column(DateTime, nullable=False)
    duration_sec = Column(Integer, default=0)
    hot = Column(Integer, default=0)  # 0/1
    hot_score = Column(Float, default=0.0)

    def as_dict(self):
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "last_update": self.last_update.isoformat() if self.last_update else None,
            "duration_sec": self.duration_sec,
            "hot": bool(self.hot),
            "hot_score": self.hot_score,
        }


class TranscriptChunk(Base):
    __tablename__ = "transcript_chunk"

    id = Column(Integer, primary_key=True, autoincrement=True)
    call_id = Column(String, index=True, nullable=False)
    agent_id = Column(String, index=True, nullable=False)
    ts = Column(DateTime, default=datetime.utcnow, index=True)
    start_ms = Column(Integer, default=0)
    end_ms = Column(Integer, default=0)
    text = Column(String, default="")
    hot_score = Column(Float, default=0.0)

    def as_dict(self):
        return {
            "id": self.id,
            "call_id": self.call_id,
            "agent_id": self.agent_id,
            "ts": self.ts.isoformat() if self.ts else None,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "text": self.text,
            "hot_score": self.hot_score,
        }