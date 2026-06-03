"""Congressional trading from Senate / House Stock Watcher public JSON.

Free, no API key. Files are cached locally for 24 hours.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import datetime, timedelta

import requests

SENATE_URL = 'https://senate-stock-watcher-data.s3-us-west-2.amazonaws.com/aggregate/all_transactions.json'
HOUSE_URL = 'https://house-stock-watcher-data.s3-us-west-2.amazonaws.com/data/all_transactions.json'

HEADERS = {'User-Agent': 'AI Stock Research Agent research@example.com'}
CACHE_TTL_SECONDS = 24 * 60 * 60
_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'stock_research_agent_cache')

_DATE_FORMATS = ('%m/%d/%Y', '%Y-%m-%d', '%m/%d/%y')


def _cache_path(name: str) -> str:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    return os.path.join(_CACHE_DIR, name)


def _load_dataset(url: str, cache_name: str) -> list:
    """Return parsed JSON list, using a <24h local cache when available."""
    path = _cache_path(cache_name)
    try:
        if os.path.exists(path) and (time.time() - os.path.getmtime(path)) < CACHE_TTL_SECONDS:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass

    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code != 200:
            return _stale_or_empty(path)
        data = resp.json()
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f)
        except Exception:
            pass
        return data if isinstance(data, list) else []
    except Exception:
        return _stale_or_empty(path)


def _stale_or_empty(path: str) -> list:
    """Fall back to a stale cache file if a fresh download failed."""
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _parse_date(value) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


def get_politician_trades(ticker: str, days: int = 180) -> list[dict]:
    """Congressional trades for a ticker within the last `days` days."""
    ticker_up = ticker.upper().strip()
    cutoff = datetime.now() - timedelta(days=days)
    results: list[dict] = []

    sources = (
        ('Senate', _load_dataset(SENATE_URL, 'senate_transactions.json')),
        ('House', _load_dataset(HOUSE_URL, 'house_transactions.json')),
    )

    for chamber, dataset in sources:
        for tx in dataset:
            try:
                tx_ticker = (tx.get('ticker') or '').upper().strip()
                if tx_ticker != ticker_up:
                    continue
                tx_date = _parse_date(tx.get('transaction_date'))
                if tx_date is None or tx_date < cutoff:
                    continue
                name = tx.get('senator') or tx.get('representative') or tx.get('name') or 'Unknown'
                results.append({
                    'name': name,
                    'chamber': chamber,
                    'type': tx.get('type') or tx.get('transaction_type') or 'Unknown',
                    'amount': tx.get('amount') or 'N/A',
                    'date': tx.get('transaction_date') or '',
                    'asset_description': tx.get('asset_description') or '',
                })
            except Exception:
                continue

    results.sort(key=lambda r: _parse_date(r['date']) or datetime.min, reverse=True)
    return results


def get_summary_text(ticker: str, transactions: list[dict]) -> str:
    """Readable summary of congressional trades for an AI prompt."""
    if not transactions:
        return f'No congressional trading disclosures found for {ticker} in the last 180 days.'

    lines = [f'{len(transactions)} congressional trade(s) found for {ticker} (last 180 days):']
    for tx in transactions[:15]:
        lines.append(
            f"  - {tx['date']}: {tx['name']} ({tx['chamber']}) — {tx['type']} {tx['amount']}"
        )
    return '\n'.join(lines)


if __name__ == '__main__':
    trades = get_politician_trades('NVDA')
    print(get_summary_text('NVDA', trades))
