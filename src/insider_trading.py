"""SEC EDGAR Form 4 (insider) filing lookup. Free, no auth required."""

from __future__ import annotations

from datetime import date, timedelta

import requests

# SEC requests a descriptive User-Agent with contact info.
HEADERS = {
    'User-Agent': 'AI Stock Research Agent research@example.com',
    'Accept': 'application/json',
}

FULL_TEXT_SEARCH = 'https://efts.sec.gov/LATEST/search-index'
UNAVAILABLE = 'Insider filing data temporarily unavailable.'


def get_insider_activity(ticker: str) -> str:
    """Return a formatted summary of recent Form 4 filings for a ticker."""
    try:
        start = (date.today() - timedelta(days=60)).isoformat()
        end = date.today().isoformat()
        params = {
            'q': f'"{ticker}"',
            'forms': '4',
            'dateRange': 'custom',
            'startdt': start,
            'enddt': end,
        }

        resp = requests.get(FULL_TEXT_SEARCH, params=params, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            # Fallback to the simpler query form.
            resp = requests.get(
                FULL_TEXT_SEARCH,
                params={'q': ticker, 'forms': '4'},
                headers=HEADERS,
                timeout=10,
            )
        if resp.status_code != 200:
            return UNAVAILABLE

        payload = resp.json()
        hits = (payload.get('hits') or {}).get('hits') or []
        if not hits:
            return (
                f'No Form 4 insider filings found for {ticker} in the last 60 days. '
                f'Verify at https://www.sec.gov/cgi-bin/browse-edgar'
            )

        filings = []
        for h in hits[:15]:
            src = h.get('_source', {})
            names = src.get('display_names') or [src.get('entityName', 'Unknown')]
            entity = names[0] if names else 'Unknown'
            filed = src.get('file_date') or src.get('filedAt') or 'unknown date'
            form_type = src.get('file_type') or src.get('formType') or '4'
            filings.append((entity, filed, form_type))

        lines = [f'{len(filings)} Form 4 insider filing(s) found for {ticker} in the last 60 days:']
        for entity, filed, form_type in filings:
            lines.append(f'  - {entity} (Form {form_type}) filed {filed}')
        lines.append('Verify at https://www.sec.gov/cgi-bin/browse-edgar')
        return '\n'.join(lines)
    except Exception:
        return UNAVAILABLE


if __name__ == '__main__':
    print(get_insider_activity('NVDA'))
