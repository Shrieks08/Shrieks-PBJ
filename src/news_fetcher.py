"""News headlines from yfinance (with feedparser RSS fallback)."""

from __future__ import annotations

from datetime import datetime

import yfinance as yf


def _humanize_time(ts) -> str:
    if not ts:
        return ''
    try:
        return datetime.fromtimestamp(int(ts)).strftime('%Y-%m-%d %H:%M')
    except (ValueError, TypeError, OSError):
        # Already a string date?
        return str(ts)


def _from_yfinance(ticker: str) -> list[dict]:
    items: list[dict] = []
    t = yf.Ticker(ticker)
    raw = t.news or []
    for entry in raw:
        content = entry.get('content', entry) if isinstance(entry, dict) else {}
        title = entry.get('title') or content.get('title')
        publisher = entry.get('publisher')
        link = entry.get('link')
        ts = entry.get('providerPublishTime')

        if isinstance(content, dict):
            title = title or content.get('title')
            provider = content.get('provider') or {}
            publisher = publisher or provider.get('displayName')
            link = link or (content.get('canonicalUrl') or {}).get('url')
            ts = ts or content.get('pubDate')

        if title:
            items.append({
                'title': title,
                'publisher': publisher or 'Unknown',
                'link': link or '',
                'providerPublishTime': _humanize_time(ts),
            })
    return items


def _from_rss(ticker: str) -> list[dict]:
    items: list[dict] = []
    try:
        import feedparser

        url = f'https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US'
        feed = feedparser.parse(url)
        for entry in feed.entries[:5]:
            items.append({
                'title': entry.get('title', ''),
                'publisher': entry.get('publisher', 'Yahoo Finance'),
                'link': entry.get('link', ''),
                'providerPublishTime': entry.get('published', ''),
            })
    except Exception:
        return []
    return items


def get_news(ticker: str) -> list[dict]:
    """Return the 5 most recent news items for a ticker."""
    try:
        items = _from_yfinance(ticker)
        if not items:
            items = _from_rss(ticker)
        return items[:5]
    except Exception:
        try:
            return _from_rss(ticker)[:5]
        except Exception:
            return []


def get_news_text(ticker: str, news_items: list[dict]) -> str:
    """Format news as bullet points for an AI prompt."""
    if not news_items:
        return f'No recent news found for {ticker}.'
    lines = [f'Recent news headlines for {ticker}:']
    for item in news_items:
        when = item.get('providerPublishTime') or ''
        lines.append(f"  - {item['title']} ({item.get('publisher', 'Unknown')}) {when}".rstrip())
    return '\n'.join(lines)


if __name__ == '__main__':
    n = get_news('NVDA')
    print(get_news_text('NVDA', n))
