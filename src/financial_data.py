"""yfinance-only financial data fetching & formatting."""

from __future__ import annotations

from datetime import datetime

import yfinance as yf

_INFO_FIELDS = [
    'longName', 'sector', 'industry', 'currentPrice', 'fiftyTwoWeekHigh',
    'fiftyTwoWeekLow', 'marketCap', 'trailingPE', 'forwardPE', 'priceToBook',
    'revenueGrowth', 'profitMargins', 'grossMargins', 'debtToEquity',
    'returnOnEquity', 'totalRevenue', 'freeCashflow', 'beta',
    'recommendationMean', 'numberOfAnalystOpinions', 'targetMeanPrice',
    'targetHighPrice',
]


def get_financial_data(ticker: str) -> dict | None:
    """Fetch a clean dict of financials, price history and news for a ticker.

    Returns None if the ticker raises an exception or has no usable data.
    """
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}

        if not info.get('currentPrice') and not info.get('regularMarketPrice'):
            # No live price -> treat as unusable.
            if not info.get('previousClose'):
                return None

        data: dict = {'ticker': ticker.upper()}
        for field in _INFO_FIELDS:
            data[field] = info.get(field)

        if not data.get('currentPrice'):
            data['currentPrice'] = info.get('regularMarketPrice') or info.get('previousClose')

        # Price history for charting.
        history: list[dict] = []
        try:
            hist = t.history(period='3mo')
            if hist is not None and not hist.empty:
                for idx, row in hist.iterrows():
                    history.append({
                        'date': idx.strftime('%Y-%m-%d'),
                        'price': round(float(row['Close']), 2),
                    })
        except Exception:
            history = []
        data['price_history'] = history

        # News headlines.
        news: list[dict] = []
        try:
            raw_news = t.news or []
            for item in raw_news[:5]:
                content = item.get('content', item) if isinstance(item, dict) else {}
                title = item.get('title') or content.get('title')
                publisher = item.get('publisher')
                link = item.get('link')
                ts = item.get('providerPublishTime')
                if not title and isinstance(content, dict):
                    title = content.get('title')
                    provider = content.get('provider') or {}
                    publisher = publisher or provider.get('displayName')
                    link = link or (content.get('canonicalUrl') or {}).get('url')
                if title:
                    news.append({
                        'title': title,
                        'publisher': publisher or 'Unknown',
                        'link': link or '',
                        'providerPublishTime': ts,
                    })
        except Exception:
            news = []
        data['news'] = news

        return data
    except Exception:
        return None


def _fmt_money(value) -> str:
    if value is None:
        return 'N/A'
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 'N/A'
    if abs(v) >= 1e12:
        return f'${v / 1e12:.2f}T'
    if abs(v) >= 1e9:
        return f'${v / 1e9:.2f}B'
    if abs(v) >= 1e6:
        return f'${v / 1e6:.2f}M'
    return f'${v:,.2f}'


def _fmt_pct(value) -> str:
    if value is None:
        return 'N/A'
    try:
        return f'{float(value) * 100:.2f}%'
    except (TypeError, ValueError):
        return 'N/A'


def _fmt_num(value) -> str:
    if value is None:
        return 'N/A'
    try:
        return f'{float(value):.2f}'
    except (TypeError, ValueError):
        return 'N/A'


def get_financial_summary_text(data: dict) -> str:
    """Human-readable metrics block suitable for an LLM prompt."""
    if not data:
        return 'No financial data available.'

    name = data.get('longName') or data.get('ticker')
    lines = [
        f"Company: {name} ({data.get('ticker')})",
        f"Sector / Industry: {data.get('sector') or 'N/A'} / {data.get('industry') or 'N/A'}",
        f"Current Price: {_fmt_money(data.get('currentPrice'))}",
        f"52-Week Range: {_fmt_money(data.get('fiftyTwoWeekLow'))} - {_fmt_money(data.get('fiftyTwoWeekHigh'))}",
        f"Market Cap: {_fmt_money(data.get('marketCap'))}",
        f"Trailing P/E: {_fmt_num(data.get('trailingPE'))}",
        f"Forward P/E: {_fmt_num(data.get('forwardPE'))}",
        f"Price/Book: {_fmt_num(data.get('priceToBook'))}",
        f"Revenue Growth (YoY): {_fmt_pct(data.get('revenueGrowth'))}",
        f"Profit Margin: {_fmt_pct(data.get('profitMargins'))}",
        f"Gross Margin: {_fmt_pct(data.get('grossMargins'))}",
        f"Debt/Equity: {_fmt_num(data.get('debtToEquity'))}",
        f"Return on Equity: {_fmt_pct(data.get('returnOnEquity'))}",
        f"Total Revenue: {_fmt_money(data.get('totalRevenue'))}",
        f"Free Cash Flow: {_fmt_money(data.get('freeCashflow'))}",
        f"Beta: {_fmt_num(data.get('beta'))}",
        f"Analyst Recommendation Mean (1=Strong Buy, 5=Sell): {_fmt_num(data.get('recommendationMean'))}",
        f"Number of Analyst Opinions: {data.get('numberOfAnalystOpinions') or 'N/A'}",
        f"Mean Target Price: {_fmt_money(data.get('targetMeanPrice'))}",
        f"High Target Price: {_fmt_money(data.get('targetHighPrice'))}",
    ]
    return '\n'.join(lines)


if __name__ == '__main__':
    d = get_financial_data('NVDA')
    if d:
        print(get_financial_summary_text(d))
