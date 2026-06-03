"""Gemini-powered stock analysis engine."""

from __future__ import annotations

import json
import os
import re
import threading
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

# Ensure .env is loaded before reading the model override (import order in
# app.py would otherwise read this before load_dotenv() runs).
load_dotenv()

# Model can be overridden with the GEMINI_MODEL env var. Default is
# gemini-2.5-flash-lite for the most generous free-tier rate limits; set
# GEMINI_MODEL=gemini-2.5-flash (or another model) to override.
MODEL = os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash-lite')

# Free-tier friendly pacing/retry settings.
_MIN_INTERVAL_SECONDS = 6.0   # space calls out to stay under per-minute quota
_MAX_RETRIES = 3
_MAX_BACKOFF_SECONDS = 45

SYSTEM_PROMPT = """
You are an elite market intelligence and stock research agent focused on identifying
high-potential investment opportunities using real-time analysis of:
- Politician trading disclosures
- Insider buying/selling activity (SEC Form 4 filings)
- AI and semiconductor trends
- Cloud infrastructure spending
- Defense and energy investments
- Geopolitical developments
- Earnings reports and macro-economic events
- Supply-chain shifts and emerging technologies

Focus sectors: AI, semiconductors, robotics, cybersecurity, defense, energy,
cloud computing, quantum computing, biotech, infrastructure, advanced manufacturing.

Requirements:
- Evidence-based reasoning only. Clearly distinguish facts from speculation.
- Avoid hype and unsubstantiated claims.
- Include recent catalysts when provided in the data.
- Mention major risks clearly.
- Be concise but analytically deep.
- Return strictly valid JSON when instructed to do so.
"""

_FIELDS = [
    'why_it_matters', 'recent_catalysts', 'insider_summary', 'politician_summary',
    'financial_strength', 'valuation_snapshot', 'growth_drivers',
    'competitive_advantages', 'geopolitical_exposure', 'risks', 'bull_case',
    'bear_case',
]

_VALID_CATEGORIES = {'momentum', 'compounder', 'high_risk', 'undervalued', 'avoid'}


def _unavailable_analysis() -> dict:
    result = {f: 'Analysis unavailable' for f in _FIELDS}
    result['conviction_score'] = 0
    result['category'] = 'avoid'
    return result


def _classify_error(msg: str) -> str:
    """Return 'quota', 'overloaded', or 'other' for a raw error string."""
    lowered = msg.lower()
    if '429' in msg or 'resource_exhausted' in lowered or 'quota' in lowered:
        return 'quota'
    if '503' in msg or 'unavailable' in lowered or 'overloaded' in lowered:
        return 'overloaded'
    return 'other'


def _parse_retry_delay(msg: str) -> int | None:
    """Pull the server-suggested retryDelay (seconds) out of an error string."""
    m = re.search(r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+)s", msg)
    if m:
        return min(int(m.group(1)) + 1, _MAX_BACKOFF_SECONDS)
    return None


def _short_error(msg: str) -> str:
    """Turn a giant raw API error into a concise, user-readable message."""
    kind = _classify_error(msg)
    if kind == 'quota':
        return ('Gemini free-tier quota exceeded. Wait ~1 minute and retry, analyse '
                'fewer stocks, or set GEMINI_MODEL=gemini-2.5-flash-lite for higher limits.')
    if kind == 'overloaded':
        return 'Gemini model temporarily overloaded (503). Please retry in a moment.'
    return msg[:200]


def _extract_json(text: str) -> dict | None:
    """Pull the first JSON object out of a model response."""
    if not text:
        return None
    text = text.strip()
    start = text.find('{')
    end = text.rfind('}')
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


class AIAnalyst:
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)
        self._lock = threading.Lock()
        self._last_call = 0.0

    def _throttle(self):
        """Block until at least _MIN_INTERVAL_SECONDS since the last call."""
        with self._lock:
            wait = _MIN_INTERVAL_SECONDS - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()

    def _generate(self, prompt: str, max_tokens: int, as_json: bool) -> str:
        """Gemini call with throttling and retry/backoff. Raises on final failure."""
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=max_tokens,
            temperature=0.4,
            # Disable "thinking" so the token budget goes to the answer, not
            # hidden reasoning (otherwise responses can come back empty).
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
        if as_json:
            config.response_mime_type = 'application/json'

        last_msg = ''
        for attempt in range(_MAX_RETRIES):
            self._throttle()
            try:
                resp = self.client.models.generate_content(
                    model=MODEL, contents=prompt, config=config,
                )
                return resp.text or ''
            except Exception as exc:
                last_msg = str(exc)
                kind = _classify_error(last_msg)
                if kind == 'other' or attempt == _MAX_RETRIES - 1:
                    break
                delay = _parse_retry_delay(last_msg)
                if delay is None:
                    delay = min(2 ** attempt * 3, _MAX_BACKOFF_SECONDS)  # 3, 6, 12...
                time.sleep(delay)

        raise RuntimeError(_short_error(last_msg))

    def analyze_stock(self, ticker, financial_data, insider_data,
                      politician_data, news_data, sector) -> dict:
        """Analyse a single stock and return a structured dict."""
        user_prompt = f"""Analyse the stock {ticker} in the context of the sector: "{sector}".

=== FINANCIAL DATA ===
{financial_data}

=== INSIDER ACTIVITY (SEC Form 4) ===
{insider_data}

=== CONGRESSIONAL TRADING ===
{politician_data}

=== RECENT NEWS ===
{news_data}

Based ONLY on the data above plus your market knowledge, respond with a STRICTLY VALID
JSON object (no markdown, no commentary) using EXACTLY these fields:
{{
  "why_it_matters": "...",
  "recent_catalysts": "...",
  "insider_summary": "...",
  "politician_summary": "...",
  "financial_strength": "...",
  "valuation_snapshot": "...",
  "growth_drivers": "...",
  "competitive_advantages": "...",
  "geopolitical_exposure": "...",
  "risks": "...",
  "bull_case": "...",
  "bear_case": "...",
  "conviction_score": 7,
  "category": "momentum|compounder|high_risk|undervalued|avoid"
}}

conviction_score is an integer 1-10. category must be exactly one of:
momentum, compounder, high_risk, undervalued, avoid."""

        try:
            text = self._generate(user_prompt, max_tokens=1500, as_json=True)
            parsed = _extract_json(text)
            if parsed is None:
                return _unavailable_analysis()

            result = _unavailable_analysis()
            for f in _FIELDS:
                if parsed.get(f):
                    result[f] = str(parsed[f])

            try:
                score = int(round(float(parsed.get('conviction_score', 0))))
            except (TypeError, ValueError):
                score = 0
            result['conviction_score'] = max(0, min(10, score))

            category = str(parsed.get('category', 'avoid')).strip().lower()
            result['category'] = category if category in _VALID_CATEGORIES else 'avoid'
            return result
        except Exception as exc:
            result = _unavailable_analysis()
            result['error'] = str(exc)
            return result

    def generate_market_brief(self, sector, stocks_data) -> str:
        """Produce a ~300-word daily market brief for the sector."""
        prompt = f"""You are writing a Daily Market Brief for the sector: "{sector}".

Here is a summary of the analysed stocks:
{stocks_data}

Write a concise (~300 words) Daily Market Brief in markdown covering:
1. Sector macro tailwinds and headwinds
2. The top themes emerging from these stocks
3. 2-3 standout opportunities (name the tickers)

Be evidence-based and avoid hype."""
        try:
            text = self._generate(prompt, max_tokens=900, as_json=False)
            return text or 'Market brief unavailable.'
        except Exception as exc:
            return f'Market brief unavailable: {exc}'

    def categorize_stocks(self, analyses: dict) -> dict:
        """Group analysed stocks by category into four lists.

        `analyses` maps ticker -> analysis dict (must contain 'category').
        """
        groups: dict[str, list[str]] = {
            'momentum': [],
            'compounders': [],
            'high_risk': [],
            'undervalued': [],
        }
        mapping = {
            'momentum': 'momentum',
            'compounder': 'compounders',
            'high_risk': 'high_risk',
            'undervalued': 'undervalued',
        }
        for ticker, analysis in analyses.items():
            cat = (analysis or {}).get('category', 'avoid')
            bucket = mapping.get(cat)
            if bucket:
                groups[bucket].append(ticker)
        return groups
