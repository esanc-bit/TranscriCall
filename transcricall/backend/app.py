from fastapi import FastAPI, UploadFile, File, Form, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Optional, List, Dict, Any
import asyncio
import io
import os
import time
from datetime import datetime, timezone

from .database import init_db, get_session
from .models import TranscriptChunk, CallSession
from .inference import Transcriber, ensure_default_model
from .classifier import HotLeadClassifier
from .websocket_manager import ConnectionManager

app = FastAPI(title="TranscriCall API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

manager = ConnectionManager()
classifier = HotLeadClassifier()

ENGINE = os.getenv("TRANSCRIBER_ENGINE", "vosk")
LANGUAGE = os.getenv("LANGUAGE", "es")
MODEL_PATH = os.getenv("MODEL_PATH", "")

ensure_default_model(engine=ENGINE, language=LANGUAGE, model_path=MODEL_PATH)
transcriber = Transcriber(engine=ENGINE, language=LANGUAGE, model_path=MODEL_PATH)

init_db()


@app.post("/ingest")
async def ingest_audio(
    agent_id: str = Form(...),
    call_id: Optional[str] = Form(None),
    chunk_start_ts: Optional[float] = Form(None),
    audio: UploadFile = File(...),
):
    """Accept 5-10s audio chunk (16k mono WAV PCM recommended)."""
    content = await audio.read()
    received_at = datetime.now(timezone.utc)

    # Basic guardrails
    if len(content) == 0:
        return JSONResponse({"error": "Empty audio"}, status_code=400)

    # Transcribe in a thread to avoid blocking event loop
    loop = asyncio.get_event_loop()
    try:
        text, segment_ms = await loop.run_in_executor(
            None, lambda: transcriber.transcribe_chunk(content)
        )
    except Exception as e:
        return JSONResponse({"error": f"Transcription failed: {e}"}, status_code=500)

    hot_score = classifier.score_text(text)
    is_hot = hot_score >= classifier.threshold

    # Persist
    with get_session() as session:
        # Ensure call exists
        call_session = session.get(CallSession, call_id) if call_id else None
        if call_session is None:
            # Create a new call if not provided or not found
            call_id_local = call_id or f"call_{int(time.time()*1000)}_{agent_id}"
            call_session = CallSession(
                id=call_id_local,
                agent_id=agent_id,
                started_at=received_at,
                last_update=received_at,
                duration_sec=0,
                hot=False,
                hot_score=0.0,
            )
            session.add(call_session)
            call_id = call_id_local
        else:
            call_id = call_session.id

        chunk = TranscriptChunk(
            call_id=call_id,
            agent_id=agent_id,
            ts=received_at,
            start_ms=segment_ms.get("start_ms", 0),
            end_ms=segment_ms.get("end_ms", 0),
            text=text,
            hot_score=hot_score,
        )
        session.add(chunk)

        # Update call session aggregates
        call_session.last_update = received_at
        # Approximate duration by last end_ms or by time since start
        approx_duration = max(
            call_session.duration_sec or 0,
            int((segment_ms.get("end_ms", 0)) / 1000),
            int((received_at - call_session.started_at).total_seconds()),
        )
        call_session.duration_sec = approx_duration

        if hot_score > call_session.hot_score:
            call_session.hot_score = hot_score
        if call_session.hot_score >= classifier.threshold:
            call_session.hot = True

        session.commit()
        session.refresh(chunk)

    payload = {
        "type": "transcript",
        "agent_id": agent_id,
        "call_id": call_id,
        "text": text,
        "ts": received_at.isoformat(),
        "hot": is_hot,
        "hot_score": hot_score,
    }

    await manager.broadcast(agent_id=agent_id, message=payload)

    return {"ok": True, "call_id": call_id, "text": text, "hot": is_hot, "hot_score": hot_score}


@app.get("/transcripts")
async def list_transcripts(
    agent_id: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    since: Optional[str] = Query(None),
    until: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=2000),
):
    since_dt = datetime.fromisoformat(since) if since else None
    until_dt = datetime.fromisoformat(until) if until else None

    with get_session() as session:
        query = session.query(TranscriptChunk)
        if agent_id:
            query = query.filter(TranscriptChunk.agent_id == agent_id)
        if q:
            like = f"%{q}%"
            query = query.filter(TranscriptChunk.text.ilike(like))
        if since_dt:
            query = query.filter(TranscriptChunk.ts >= since_dt)
        if until_dt:
            query = query.filter(TranscriptChunk.ts <= until_dt)
        query = query.order_by(TranscriptChunk.ts.desc()).limit(limit)

        rows = [r.as_dict() for r in query.all()]
        return {"items": rows}


@app.get("/analytics/summary")
async def analytics_summary(
    since: Optional[str] = Query(None),
    until: Optional[str] = Query(None),
):
    since_dt = datetime.fromisoformat(since) if since else None
    until_dt = datetime.fromisoformat(until) if until else None

    with get_session() as session:
        # Calls by hour of day (UTC)
        call_q = session.query(CallSession)
        if since_dt:
            call_q = call_q.filter(CallSession.started_at >= since_dt)
        if until_dt:
            call_q = call_q.filter(CallSession.started_at <= until_dt)
        calls = call_q.all()

        by_hour = {str(h): 0 for h in range(24)}
        hot_by_hour = {str(h): 0 for h in range(24)}
        for c in calls:
            h = c.started_at.astimezone(timezone.utc).hour
            by_hour[str(h)] += 1
            if c.hot:
                hot_by_hour[str(h)] += 1

        # Keyword percentage from transcript chunks
        chunks_q = session.query(TranscriptChunk)
        if since_dt:
            chunks_q = chunks_q.filter(TranscriptChunk.ts >= since_dt)
        if until_dt:
            chunks_q = chunks_q.filter(TranscriptChunk.ts <= until_dt)
        chunks = chunks_q.all()
        total_chunks = len(chunks)
        keyword_hits = 0
        for ch in chunks:
            if classifier.score_text(ch.text) >= classifier.threshold:
                keyword_hits += 1
        keyword_pct = (keyword_hits / total_chunks) * 100 if total_chunks else 0

        # Agent ranking by volume and quality
        by_agent: Dict[str, Dict[str, Any]] = {}
        for c in calls:
            stats = by_agent.setdefault(c.agent_id, {"calls": 0, "hot_calls": 0, "avg_hot_score": 0.0})
            stats["calls"] += 1
            if c.hot:
                stats["hot_calls"] += 1
            stats["avg_hot_score"] += c.hot_score
        for aid, stats in by_agent.items():
            if stats["calls"]:
                stats["avg_hot_score"] = stats["avg_hot_score"] / stats["calls"]

        ranking = sorted(
            (
                {
                    "agent_id": aid,
                    "calls": s["calls"],
                    "hot_calls": s["hot_calls"],
                    "avg_hot_score": round(s["avg_hot_score"], 3),
                }
                for aid, s in by_agent.items()
            ),
            key=lambda r: (r["hot_calls"], r["avg_hot_score"], r["calls"]),
            reverse=True,
        )

        # Call duration distribution (histogram bins)
        bins = [0, 60, 120, 300, 600, 900, 1800]
        labels = ["<1m", "1-2m", "2-5m", "5-10m", "10-15m", "15-30m", ">30m"]
        hist = {label: 0 for label in labels}
        for c in calls:
            d = c.duration_sec or 0
            if d < 60:
                hist[labels[0]] += 1
            elif d < 120:
                hist[labels[1]] += 1
            elif d < 300:
                hist[labels[2]] += 1
            elif d < 600:
                hist[labels[3]] += 1
            elif d < 900:
                hist[labels[4]] += 1
            elif d < 1800:
                hist[labels[5]] += 1
            else:
                hist[labels[6]] += 1

        return {
            "calls_by_hour": by_hour,
            "hot_calls_by_hour": hot_by_hour,
            "keyword_hit_pct": round(keyword_pct, 2),
            "agent_ranking": ranking,
            "duration_histogram": hist,
        }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            if action == "subscribe":
                agent_id = data.get("agent_id", "all")
                await manager.subscribe(websocket, agent_id)
            elif action == "unsubscribe":
                agent_id = data.get("agent_id", "all")
                await manager.unsubscribe(websocket, agent_id)
            else:
                await websocket.send_json({"type": "error", "message": "Unknown action"})
    except WebSocketDisconnect:
        await manager.disconnect(websocket)