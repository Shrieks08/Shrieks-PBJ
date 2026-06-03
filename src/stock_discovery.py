"""Sector / free-text field -> list of stock tickers.

Three-step strategy:
  1. Hardcoded keyword -> tickers map (case-insensitive).
  2. financedatabase equity search on extracted keywords.
  3. yfinance Search(query).quotes for EQUITY results.
Final list is de-duplicated and ranked by market cap (top N).
"""

from __future__ import annotations

import re

import yfinance as yf

SECTOR_MAP = {
    'ai': ['NVDA', 'MSFT', 'GOOGL', 'META', 'AMD', 'SMCI', 'PLTR', 'AI', 'SOUN', 'BBAI', 'ORCL', 'CRM'],
    'artificial intelligence': ['NVDA', 'MSFT', 'GOOGL', 'META', 'AMD', 'SMCI', 'PLTR', 'AI', 'SOUN'],
    'semiconductor': ['NVDA', 'AMD', 'INTC', 'QCOM', 'AVGO', 'TSM', 'AMAT', 'LRCX', 'KLAC', 'MRVL', 'MU', 'ON'],
    'defense': ['LMT', 'RTX', 'NOC', 'GD', 'BA', 'KTOS', 'CACI', 'SAIC', 'LDOS', 'BWXT', 'HII'],
    'cybersecurity': ['CRWD', 'PANW', 'ZS', 'FTNT', 'S', 'OKTA', 'CYBR', 'QLYS', 'RPD', 'TENB'],
    'cloud': ['AMZN', 'MSFT', 'GOOGL', 'SNOW', 'NET', 'DDOG', 'MDB', 'ESTC', 'HUBS', 'ZM'],
    'biotech': ['MRNA', 'BIIB', 'REGN', 'VRTX', 'GILD', 'BMRN', 'RARE', 'ALNY', 'SRPT', 'BEAM'],
    'energy': ['NEE', 'ENPH', 'FSLR', 'BE', 'PLUG', 'CEG', 'VST', 'ETR', 'SO', 'DUK'],
    'clean energy': ['NEE', 'ENPH', 'FSLR', 'BE', 'PLUG', 'RUN', 'ARRY', 'SHLS', 'NOVA'],
    'robotics': ['ISRG', 'TER', 'ROK', 'BRKS', 'ABB', 'FANUC', 'IRBT', 'AVAV', 'AGIO'],
    'quantum': ['IBM', 'IONQ', 'RGTI', 'QUBT', 'QMCO', 'MSFT', 'GOOGL'],
    'infrastructure': ['CAT', 'DE', 'URI', 'PWR', 'AECOM', 'MDU', 'VMC', 'MLM', 'J'],
    'space': ['RKLB', 'SPCE', 'LMT', 'NOC', 'MAXR', 'IRDM', 'GSAT', 'MNTS'],
    'fintech': ['SQ', 'PYPL', 'AFRM', 'UPST', 'LC', 'SOFI', 'NU', 'OPEN', 'HOOD'],
}

# A few synonyms that map onto the canonical keys above.
SYNONYMS = {
    'machine learning': 'ai',
    'ml': 'ai',
    'genai': 'ai',
    'generative ai': 'ai',
    'chips': 'semiconductor',
    'semiconductors': 'semiconductor',
    'semis': 'semiconductor',
    'defence': 'defense',
    'military': 'defense',
    'aerospace': 'defense',
    'cyber': 'cybersecurity',
    'security': 'cybersecurity',
    'solar': 'clean energy',
    'renewable': 'clean energy',
    'renewables': 'clean energy',
    'green energy': 'clean energy',
    'pharma': 'biotech',
    'biotechnology': 'biotech',
    'healthcare': 'biotech',
    'quantum computing': 'quantum',
    'fin tech': 'fintech',
    'payments': 'fintech',
    'banking': 'fintech',
    'robots': 'robotics',
    'automation': 'robotics',
    'data center': 'cloud',
    'datacenter': 'cloud',
    'saas': 'cloud',
}


def _match_hardcoded(user_input: str) -> list[str]:
    """Case-insensitive keyword matching against SECTOR_MAP + SYNONYMS."""
    text = user_input.lower()
    matched: list[str] = []

    for phrase, key in SYNONYMS.items():
        if phrase in text and key in SECTOR_MAP:
            for t in SECTOR_MAP[key]:
                if t not in matched:
                    matched.append(t)

    for key, tickers in SECTOR_MAP.items():
        if key in text:
            for t in tickers:
                if t not in matched:
                    matched.append(t)

    return matched


def _match_financedatabase(user_input: str) -> list[str]:
    """Best-effort financedatabase equity search. Returns [] on any failure."""
    found: list[str] = []
    try:
        import financedatabase as fd

        equities = fd.Equities()
        words = [w for w in re.split(r'[^a-zA-Z]+', user_input) if len(w) > 2]

        for col in ('sector', 'industry'):
            for w in words:
                try:
                    res = equities.search(**{col: w})
                except Exception:
                    continue
                if res is None or len(res) == 0:
                    continue
                for sym in list(res.index)[:25]:
                    sym = str(sym).upper()
                    if sym and sym.isascii() and sym not in found and '.' not in sym:
                        found.append(sym)
                if found:
                    break
    except Exception:
        return []
    return found


def _match_yf_search(user_input: str) -> list[str]:
    """Use yfinance search to supplement. Returns [] on any failure."""
    found: list[str] = []
    try:
        search = yf.Search(user_input, max_results=15)
        quotes = getattr(search, 'quotes', []) or []
        for q in quotes:
            if q.get('quoteType') == 'EQUITY':
                sym = (q.get('symbol') or '').upper()
                if sym and sym not in found:
                    found.append(sym)
    except Exception:
        return []
    return found


def _market_cap(ticker: str) -> float | None:
    """Return market cap for ranking, or None if the ticker fails to load."""
    try:
        info = yf.Ticker(ticker).info
        cap = info.get('marketCap')
        if cap and cap > 0:
            return float(cap)
        # Ticker loads but has no cap -> keep it, rank it low.
        if info.get('regularMarketPrice') or info.get('currentPrice'):
            return 0.0
        return None
    except Exception:
        return None


def get_tickers(sector_text: str, n: int = 8) -> list[str]:
    """Map a free-text sector to up to N tickers ranked by market cap."""
    if not sector_text or not sector_text.strip():
        return []

    candidates: list[str] = []

    for source in (_match_hardcoded, _match_financedatabase, _match_yf_search):
        try:
            for t in source(sector_text):
                if t not in candidates:
                    candidates.append(t)
        except Exception:
            continue

    if not candidates:
        # Total fallback: a broad large-cap basket so the app still runs.
        candidates = SECTOR_MAP['ai'][:n]

    # Rank by market cap; drop tickers that fail to load entirely.
    ranked: list[tuple[str, float]] = []
    for t in candidates:
        cap = _market_cap(t)
        if cap is not None:
            ranked.append((t, cap))
        if len(ranked) >= max(n * 3, n + 5):
            # Enough verified candidates to choose a strong top N.
            break

    ranked.sort(key=lambda x: x[1], reverse=True)
    return [t for t, _ in ranked[:n]]


if __name__ == '__main__':
    print(get_tickers('AI semiconductors', 3))
