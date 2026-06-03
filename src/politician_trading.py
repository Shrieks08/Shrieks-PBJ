"""Congressional trading data.

Free live congressional APIs no longer exist (Finnhub & FMP gate it behind paid
plans; the old Senate/House Stock Watcher S3 feeds return 403). So this module:

  1. Tries a live premium source (Finnhub) IF a key is supplied and has access —
     this auto-upgrades the data to current if you ever add a paid key.
  2. Otherwise falls back to the free Senate Stock Watcher GitHub mirror, which is
     real disclosure data but frozen at ~2012-2020 (clearly labelled historical).

The House dataset has no working free mirror, so only Senate history is available
on the free path.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import datetime

import requests

# Live (premium) source — only returns data on a paid Finnhub plan.
FINNHUB_URL = 'https://finnhub.io/api/v1/stock/congressional-trading'

# Free historical fallback (Senate only, ~2012-2020).
SENATE_HISTORICAL_URL = (
    'https://raw.githubusercontent.com/timothycarambat/'
    'senate-stock-watcher-data/master/aggregate/all_transactions.json'
)

HEADERS = {'User-Agent': 'AI Stock Research Agent research@example.com'}
HISTORICAL_LABEL = 'Senate Stock Watcher (historical 2012-2020)'

_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'stock_research_agent_cache')
_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60  # static dataset; cache a week
_DATE_FORMATS = ('%m/%d/%Y', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%m/%d/%y')

# In-process memo so we don't re-parse the 8k-record file for every ticker.
_senate_cache: list | None = None


def _parse_date(value) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    value = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    try:
        return datetime.strptime(value[:10], '%Y-%m-%d')
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Live premium source (Finnhub)
# --------------------------------------------------------------------------- #
def _fmt_amount(tx: dict) -> str:
    a, b = tx.get('amountFrom'), tx.get('amountTo')
    try:
        if a is not None and b is not None:
            return f'${float(a):,.0f} - ${float(b):,.0f}'
        if a is not None:
            return f'${float(a):,.0f}'
        if b is not None:
            return f'${float(b):,.0f}'
    except (TypeError, ValueError):
        pass
    return str(tx.get('amount') or 'N/A')


def _finnhub_trades(ticker: str, api_key: str, max_results: int) -> list[dict]:
    try:
        resp = requests.get(
            FINNHUB_URL,
            params={'symbol': ticker.upper(), 'token': api_key},
            headers=HEADERS,
            timeout=15,
        )
        if resp.status_code != 200:
            return []  # 403 on free tier -> caller falls back to historical
        rows = (resp.json() or {}).get('data') or []
    except Exception:
        return []

    results = []
    for tx in rows:
        try:
            results.append({
                'name': tx.get('name') or 'Unknown',
                'chamber': tx.get('chamber') or 'Congress',
                'type': tx.get('transactionType') or tx.get('position')
                        or tx.get('transaction') or 'Unknown',
                'amount': _fmt_amount(tx),
                'date': (tx.get('transactionDate') or tx.get('filingDate') or '')[:10],
                'asset_description': tx.get('assetName') or '',
                'source': 'Finnhub (live)',
            })
        except Exception:
            continue
    results.sort(key=lambda r: _parse_date(r['date']) or datetime.min, reverse=True)
    return results[:max_results]


# --------------------------------------------------------------------------- #
# Free historical Senate source (GitHub mirror)
# --------------------------------------------------------------------------- #
def _load_senate_dataset() -> list:
    global _senate_cache
    if _senate_cache is not None:
        return _senate_cache

    os.makedirs(_CACHE_DIR, exist_ok=True)
    path = os.path.join(_CACHE_DIR, 'senate_historical.json')

    # Disk cache.
    try:
        if os.path.exists(path) and (time.time() - os.path.getmtime(path)) < _CACHE_TTL_SECONDS:
            with open(path, 'r', encoding='utf-8') as f:
                _senate_cache = json.load(f)
                return _senate_cache
    except Exception:
        pass

    try:
        resp = requests.get(SENATE_HISTORICAL_URL, headers=HEADERS, timeout=30)
        if resp.status_code != 200:
            _senate_cache = []
            return _senate_cache
        data = resp.json()
        _senate_cache = data if isinstance(data, list) else []
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(_senate_cache, f)
        except Exception:
            pass
    except Exception:
        _senate_cache = []
    return _senate_cache


def _senate_historical_trades(ticker: str, max_results: int) -> list[dict]:
    ticker_up = ticker.upper().strip()
    results = []
    for tx in _load_senate_dataset():
        try:
            if (tx.get('ticker') or '').upper().strip() != ticker_up:
                continue
            results.append({
                'name': tx.get('senator') or tx.get('name') or 'Unknown',
                'chamber': 'Senate',
                'type': tx.get('type') or 'Unknown',
                'amount': tx.get('amount') or 'N/A',
                'date': tx.get('transaction_date') or '',
                'asset_description': tx.get('asset_description') or '',
                'source': HISTORICAL_LABEL,
            })
        except Exception:
            continue
    results.sort(key=lambda r: _parse_date(r['date']) or datetime.min, reverse=True)
    return results[:max_results]


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def get_politician_trades(ticker: str, api_key: str | None = None,
                          max_results: int = 40) -> list[dict]:
    """Congressional trades for a ticker.

    Uses a live premium Finnhub key if it has access; otherwise falls back to the
    free historical Senate dataset. Never raises — returns [] on total failure.
    """
    api_key = api_key or os.environ.get('FINNHUB_API_KEY', '')
    if api_key:
        live = _finnhub_trades(ticker, api_key, max_results)
        if live:
            return live
    return _senate_historical_trades(ticker, max_results)


def get_summary_text(ticker: str, transactions: list[dict]) -> str:
    """Readable summary of congressional trades for an AI prompt."""
    if not transactions:
        return f'No congressional trading disclosures found for {ticker}.'

    vintage = transactions[0].get('source', '')
    note = ' (NOTE: historical data, not current)' if 'historical' in vintage.lower() else ''
    lines = [f'{len(transactions)} congressional trade(s) found for {ticker}{note}:']
    for tx in transactions[:15]:
        lines.append(
            f"  - {tx['date']}: {tx['name']} ({tx['chamber']}) — {tx['type']} {tx['amount']}"
        )
    return '\n'.join(lines)


if __name__ == '__main__':
    trades = get_politician_trades('NVDA')
    print(get_summary_text('NVDA', trades))
