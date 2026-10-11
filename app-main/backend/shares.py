"""A public link to the free product analysis.

The stored row is the product, not the person: no skin type, concerns, or
routine. Opening the link re-runs the engine and then keeps only the free
keys, so a shared URL cannot become a copy of someone else's paid result.
"""

import json
import logging
import secrets
import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

shares_router = APIRouter()

SCHEMA = """
CREATE TABLE IF NOT EXISTS share_link (
    share_id   TEXT PRIMARY KEY,
    payload    TEXT NOT NULL,
    created_at DOUBLE PRECISION NOT NULL
)
"""


class ShareRequest(BaseModel):
    product_name: str = ''
    brand: str = ''
    category: str = 'Serum'
    price: float = 0
    size_ml: float = 0
    ingredients: str = Field(min_length=1, max_length=5000)
    country: str = 'India'
    currency: str = 'INR'


def _wallet():
    import wallet
    wallet.init_storage()
    return wallet


def ensure_schema():
    wallet = _wallet()
    sql = SCHEMA if wallet.storage_is_durable() else SCHEMA.replace(
        'DOUBLE PRECISION', 'REAL')
    wallet._execute(sql, (), commit=True)


def _product(body):
    return {
        'product_name': (body.product_name or '')[:200],
        'brand': (body.brand or '')[:120],
        'category': (body.category or 'Serum')[:60],
        'price': float(body.price or 0),
        'size_ml': float(body.size_ml or 0),
        'ingredients': body.ingredients.strip()[:5000],
        'country': (body.country or 'India')[:40],
        'currency': (body.currency or 'INR')[:8],
    }


@shares_router.post('/share')
async def create_share(body: ShareRequest):
    product = _product(body)
    if not product['ingredients']:
        return JSONResponse(status_code=400, content={'error': 'Add an ingredient list first.'})
    try:
        ensure_schema()
        share_id = secrets.token_urlsafe(9)
        _wallet()._execute(
            'INSERT INTO share_link (share_id, payload, created_at) VALUES (?, ?, ?)',
            (share_id, json.dumps(product), time.time()),
            commit=True)
    except Exception:
        logger.exception('could not store share link')
        return JSONResponse(status_code=500, content={'error': 'Could not create a link.'})
    return {'share_id': share_id}


@shares_router.get('/share/{share_id}')
async def open_share(share_id: str):
    if not share_id or len(share_id) > 32:
        return JSONResponse(status_code=404, content={'error': 'That link is not here.'})
    try:
        ensure_schema()
        cur = _wallet()._execute(
            'SELECT payload FROM share_link WHERE share_id = ?', (share_id,))
        row = cur.fetchone()
    except Exception:
        logger.exception('could not read share link')
        return JSONResponse(status_code=500, content={'error': 'Could not open that link.'})
    if not row:
        return JSONResponse(status_code=404, content={'error': 'That link is not here.'})
    try:
        product = json.loads(row[0])
    except (TypeError, json.JSONDecodeError):
        return JSONResponse(status_code=404, content={'error': 'That link is not here.'})

    from scoring import analyze_product
    from entitlement import filter_for_entitlement, audit_no_paid_leakage
    import evidence

    product_data = {
        'ingredients': product['ingredients'],
        'price': product.get('price') or 0,
        'size_ml': product.get('size_ml') or 0,
        'category': product.get('category') or 'Serum',
        'concerns': [],
        'skin_type': 'normal',
        'country': product.get('country') or 'India',
        'currency': product.get('currency') or 'INR',
        'product_name': product.get('product_name') or '',
        'active_concentrations': {},
        'user_profile': {},
    }
    result = filter_for_entitlement(evidence.attach(analyze_product(product_data)), False)
    audit_no_paid_leakage(result)
    return {'share_id': share_id, 'product': product, 'result': result}
