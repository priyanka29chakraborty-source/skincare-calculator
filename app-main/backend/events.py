"""Decision events for the paid beta.

Names are a fixed list so the table cannot become a place to store an email,
an ingredient list, or a free-text note. Counts answer whether people finish
an analysis, open the personal section, pay, compare, save a routine, come
back, or ask for a refund.
"""

import logging
import time
import uuid

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

events_router = APIRouter()

ALLOWED = {
    'analysis_completed',
    'personal_opened',
    'checkout_started',
    'checkout_completed',
    'routine_saved',
    'comparison_completed',
    'result_reopened',
    'refund_requested',
    'pdf_saved',
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS beta_event (
    event_id   TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    created_at DOUBLE PRECISION NOT NULL
)
"""


class EventIn(BaseModel):
    name: str


class FeedbackIn(BaseModel):
    message: str = Field(min_length=3, max_length=2000)
    email: str = ''


def _wallet():
    import wallet
    wallet.init_storage()
    return wallet


def ensure_schema():
    wallet = _wallet()
    sql = SCHEMA if wallet.storage_is_durable() else SCHEMA.replace(
        'DOUBLE PRECISION', 'REAL')
    wallet._execute(sql, (), commit=True)


def record(name):
    if name not in ALLOWED:
        return False
    ensure_schema()
    _wallet()._execute(
        'INSERT INTO beta_event (event_id, name, created_at) VALUES (?, ?, ?)',
        (uuid.uuid4().hex, name, time.time()),
        commit=True)
    return True


def counts():
    ensure_schema()
    cur = _wallet()._execute(
        'SELECT name, COUNT(*) FROM beta_event GROUP BY name', ())
    found = {row[0]: int(row[1]) for row in cur.fetchall()}
    return {name: found.get(name, 0) for name in sorted(ALLOWED)}


@events_router.post('/events')
async def post_event(body: EventIn):
    if body.name not in ALLOWED:
        return JSONResponse(status_code=400, content={'error': 'Unknown event.'})
    try:
        record(body.name)
    except Exception:
        logger.exception('could not store beta event')
        return JSONResponse(status_code=500, content={'error': 'Could not record that.'})
    return {'ok': True}


_FEEDBACK_SCHEMA = """
CREATE TABLE IF NOT EXISTS feedback_note (
    note_id    TEXT PRIMARY KEY,
    email      TEXT,
    message    TEXT NOT NULL,
    created_at DOUBLE PRECISION NOT NULL
)
"""


@events_router.post('/feedback')
async def post_feedback(body: FeedbackIn):
    wallet = _wallet()
    sql = _FEEDBACK_SCHEMA if wallet.storage_is_durable() else _FEEDBACK_SCHEMA.replace(
        'DOUBLE PRECISION', 'REAL')
    try:
        wallet._execute(sql, (), commit=True)
        wallet._execute(
            'INSERT INTO feedback_note (note_id, email, message, created_at) '
            'VALUES (?, ?, ?, ?)',
            (uuid.uuid4().hex, (body.email or '')[:200], body.message.strip()[:2000],
             time.time()),
            commit=True)
    except Exception:
        logger.exception('could not store feedback')
        return JSONResponse(status_code=500, content={'error': 'Could not save that.'})
    return {'received': True}


@events_router.get('/events/summary')
async def event_summary():
    try:
        return {'counts': counts()}
    except Exception:
        logger.exception('could not read beta events')
        return JSONResponse(status_code=500, content={'error': 'Could not read events.'})
