"""AI Stock Research Agent — Streamlit entry point."""

from __future__ import annotations

import json
import os

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

from src.ai_analyst import AIAnalyst
from src.financial_data import get_financial_data, get_financial_summary_text
from src.insider_trading import get_insider_activity
from src.news_fetcher import get_news, get_news_text
from src.politician_trading import get_politician_trades, get_summary_text
from src.stock_discovery import get_tickers

load_dotenv()

st.set_page_config(page_title='AI Stock Research Agent', page_icon='🔍', layout='wide')


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
def render_sidebar():
    st.sidebar.title('🔍 AI Stock Research Agent')

    api_key = st.sidebar.text_input(
        'Gemini API Key',
        type='password',
        value=os.environ.get('GEMINI_API_KEY', ''),
        help='Get one at aistudio.google.com/apikey',
    )
    if not api_key:
        api_key = os.environ.get('GEMINI_API_KEY', '')

    finnhub_key = st.sidebar.text_input(
        'Finnhub API Key (optional)',
        type='password',
        value=os.environ.get('FINNHUB_API_KEY', ''),
        help='Only a PAID Finnhub plan returns congressional data. Without it, the '
             'Politician tab shows free historical Senate data (2012–2020).',
    )
    if not finnhub_key:
        finnhub_key = os.environ.get('FINNHUB_API_KEY', '')

    sector = st.sidebar.text_area(
        'Enter a sector or field to research',
        height=120,
        placeholder='e.g. AI infrastructure · quantum computing · defense tech · '
                    'biotech · clean energy · cybersecurity · robotics',
    )

    num_stocks = st.sidebar.slider('Number of stocks to analyse', 3, 15, 8)

    run = st.sidebar.button(
        '🚀 Run Analysis',
        type='primary',
        disabled=(not api_key or not sector.strip()),
        use_container_width=True,
    )

    with st.sidebar.expander('ℹ️ About & Data Sources'):
        st.markdown(
            '- **Financials:** yfinance (free)\n'
            '- **Insider trades:** SEC EDGAR (free)\n'
            '- **Politician trades:** Senate Stock Watcher (historical, free)\n'
            '- **AI analysis:** Google Gemini\n\n'
            'Data may lag real time. For research support only.'
        )

    return api_key, finnhub_key, sector, num_stocks, run


# --------------------------------------------------------------------------- #
# Analysis pipeline
# --------------------------------------------------------------------------- #
def run_analysis(api_key: str, finnhub_key: str, sector: str, num_stocks: int) -> dict:
    analyst = AIAnalyst(api_key)
    progress = st.progress(0.0)
    status = st.empty()

    status.text('Discovering stocks in sector...')
    with st.spinner('Discovering relevant stocks...'):
        tickers = get_tickers(sector, num_stocks)

    if not tickers:
        st.error('No stocks could be discovered for that sector. Try a different term.')
        return {}

    st.success(f'Discovered {len(tickers)} stocks: {", ".join(tickers)}')

    stocks: dict[str, dict] = {}
    total = len(tickers)

    for i, ticker in enumerate(tickers):
        base = i / total

        status.text(f'Fetching financial data for {ticker}...')
        fin = get_financial_data(ticker)
        if fin is None:
            st.warning(f'Skipping {ticker}: financial data unavailable.')
            progress.progress((i + 1) / total)
            continue
        progress.progress(min(base + 0.25 / total, 1.0))

        status.text(f'Checking insider activity for {ticker}...')
        insider = get_insider_activity(ticker)
        progress.progress(min(base + 0.45 / total, 1.0))

        status.text(f'Checking congressional trading for {ticker}...')
        trades = get_politician_trades(ticker, api_key=finnhub_key)
        politician_text = get_summary_text(ticker, trades)
        progress.progress(min(base + 0.60 / total, 1.0))

        status.text(f'Fetching news for {ticker}...')
        news = get_news(ticker)
        news_text = get_news_text(ticker, news)
        progress.progress(min(base + 0.70 / total, 1.0))

        status.text(f'Running AI analysis for {ticker}...')
        with st.spinner(f'Gemini is analysing {ticker}...'):
            analysis = analyst.analyze_stock(
                ticker,
                get_financial_summary_text(fin),
                insider,
                politician_text,
                news_text,
                sector,
            )
        if analysis.get('error'):
            st.error(f'AI analysis failed for {ticker}: {analysis["error"]}')

        stocks[ticker] = {
            'financial': fin,
            'insider': insider,
            'trades': trades,
            'news': news,
            'analysis': analysis,
        }
        progress.progress((i + 1) / total)

    status.text('Generating market brief...')
    with st.spinner('Generating Daily Market Brief...'):
        brief_input = '\n\n'.join(
            f"{t}: conviction {d['analysis'].get('conviction_score')}/10, "
            f"category {d['analysis'].get('category')}. "
            f"{d['analysis'].get('why_it_matters', '')}"
            for t, d in stocks.items()
        )
        brief = analyst.generate_market_brief(sector, brief_input) if stocks else 'No data.'

    categories = analyst.categorize_stocks({t: d['analysis'] for t, d in stocks.items()})

    progress.progress(1.0)
    status.text('Done.')

    return {'sector': sector, 'stocks': stocks, 'brief': brief,
            'categories': categories, 'has_finnhub': bool(finnhub_key)}


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def _conviction_badge(score: int) -> str:
    if score >= 8:
        return f'🟢 **Conviction: {score}/10**'
    if score >= 5:
        return f'🟡 **Conviction: {score}/10**'
    return f'🔴 **Conviction: {score}/10**'


def render_stock_card(ticker: str, data: dict, key_prefix: str = ''):
    fin = data['financial']
    analysis = data['analysis']

    name = fin.get('longName') or ticker
    price = fin.get('currentPrice')
    low = fin.get('fiftyTwoWeekLow')
    high = fin.get('fiftyTwoWeekHigh')

    c1, c2, c3 = st.columns(3)
    c1.metric(name, ticker)
    c2.metric('Price', f'${price:,.2f}' if price else 'N/A')
    range_str = (
        f'${low:,.2f} - ${high:,.2f}' if (low and high) else 'N/A'
    )
    c3.metric('52-Week Range', range_str)

    st.markdown(_conviction_badge(int(analysis.get('conviction_score', 0))))

    history = fin.get('price_history') or []
    if history:
        df = pd.DataFrame(history)
        fig = px.line(df, x='date', y='price', title=f'{ticker} — 3-Month Price')
        fig.update_layout(height=300, margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig, use_container_width=True, key=f'chart_{key_prefix}{ticker}')

    sections = [
        ('Why It Matters Now', 'why_it_matters'),
        ('Recent Catalysts', 'recent_catalysts'),
        ('Insider & Politician Activity', None),
        ('Financial Strength', 'financial_strength'),
        ('Valuation Snapshot', 'valuation_snapshot'),
        ('Growth Drivers', 'growth_drivers'),
        ('Competitive Advantages', 'competitive_advantages'),
        ('Geopolitical Exposure', 'geopolitical_exposure'),
        ('Risks', 'risks'),
        ('Bull Case', 'bull_case'),
        ('Bear Case', 'bear_case'),
    ]
    for label, field in sections:
        st.markdown(f'**{label}**')
        if field is None:
            st.markdown(
                f"- _Insider:_ {analysis.get('insider_summary', 'N/A')}\n"
                f"- _Politicians:_ {analysis.get('politician_summary', 'N/A')}"
            )
        else:
            st.markdown(analysis.get(field, 'N/A'))

    st.markdown('---')
    st.markdown('**Key Metrics**')
    m1, m2, m3 = st.columns(3)
    m1.metric('P/E (trailing)', _num(fin.get('trailingPE')))
    m1.metric('Debt/Equity', _num(fin.get('debtToEquity')))
    m2.metric('Revenue Growth', _pct(fin.get('revenueGrowth')))
    m2.metric('Return on Equity', _pct(fin.get('returnOnEquity')))
    m3.metric('Profit Margin', _pct(fin.get('profitMargins')))
    m3.metric('Analyst Target', f"${fin['targetMeanPrice']:,.2f}" if fin.get('targetMeanPrice') else 'N/A')


def _num(v) -> str:
    try:
        return f'{float(v):.2f}'
    except (TypeError, ValueError):
        return 'N/A'


def _pct(v) -> str:
    try:
        return f'{float(v) * 100:.1f}%'
    except (TypeError, ValueError):
        return 'N/A'


def render_results(results: dict):
    stocks = results['stocks']
    if not stocks:
        st.info('No stocks were successfully analysed.')
        return

    tabs = st.tabs([
        '📊 Daily Brief', '🏆 Top Picks', '🏛 Politician Trading',
        '👔 Insider Activity', '📈 Momentum Plays', '💎 Long-Term Compounders',
        '⚡ High Risk/Reward', '💰 Undervalued',
    ])

    # Tab 1 — Daily Brief
    with tabs[0]:
        st.markdown(results['brief'])

    # Tab 2 — Top Picks (sorted by conviction)
    with tabs[1]:
        ordered = sorted(
            stocks.items(),
            key=lambda kv: kv[1]['analysis'].get('conviction_score', 0),
            reverse=True,
        )
        for ticker, data in ordered:
            score = data['analysis'].get('conviction_score', 0)
            with st.expander(f"{ticker} — {data['financial'].get('longName', ticker)} ({score}/10)"):
                render_stock_card(ticker, data, key_prefix='top_')

    # Tab 3 — Politician Trading
    with tabs[2]:
        rows = []
        for ticker, data in stocks.items():
            for tx in data['trades']:
                rows.append({'Ticker': ticker, **tx})
        sources = {tx.get('source', '') for r in stocks.values() for tx in r['trades']}
        if any('historical' in s.lower() for s in sources):
            st.caption('⏳ Source: Senate Stock Watcher — real disclosures but '
                       'historical (~2012–2020). Free live congressional data is no '
                       'longer available; add a paid Finnhub/FMP key to auto-upgrade to current data.')
        if rows:
            df = pd.DataFrame(rows).sort_values('date', ascending=False)
            st.dataframe(df, use_container_width=True)
        else:
            st.info('No Senate trades on record for the analysed tickers.')

    # Tab 4 — Insider Activity
    with tabs[3]:
        for ticker, data in stocks.items():
            st.markdown(f'**{ticker}**')
            st.text(data['insider'])
            st.markdown('---')

    # Tabs 5-8 — categorised subsets
    category_tabs = [
        (tabs[4], 'momentum'),
        (tabs[5], 'compounders'),
        (tabs[6], 'high_risk'),
        (tabs[7], 'undervalued'),
    ]
    for tab, cat in category_tabs:
        with tab:
            tickers = results['categories'].get(cat, [])
            if not tickers:
                st.info('No stocks in this category.')
                continue
            for ticker in tickers:
                data = stocks.get(ticker)
                if not data:
                    continue
                score = data['analysis'].get('conviction_score', 0)
                with st.expander(f"{ticker} — {data['financial'].get('longName', ticker)} ({score}/10)"):
                    render_stock_card(ticker, data, key_prefix=f'{cat}_')

    # Bottom — download + disclaimer
    st.markdown('---')
    export = {
        'sector': results['sector'],
        'brief': results['brief'],
        'stocks': {
            t: {
                'analysis': d['analysis'],
                'price': d['financial'].get('currentPrice'),
                'name': d['financial'].get('longName'),
                'trades': d['trades'],
            }
            for t, d in stocks.items()
        },
    }
    st.download_button(
        'Download Full Report as JSON',
        data=json.dumps(export, indent=2, default=str),
        file_name='stock_research_report.json',
        mime='application/json',
    )
    st.markdown(
        "<p style='color:red;font-weight:bold;'>⚠️ This output is for research "
        "support only and not financial advice.</p>",
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    api_key, finnhub_key, sector, num_stocks, run = render_sidebar()

    st.title('🔍 AI Stock Research Agent')
    st.caption('Discover and analyse publicly-traded stocks in any sector using free data + Gemini.')

    if run:
        results = run_analysis(api_key, finnhub_key, sector, num_stocks)
        if results:
            st.session_state['results'] = results

    if 'results' in st.session_state:
        render_results(st.session_state['results'])
    else:
        st.info('Enter your Gemini API key and a sector in the sidebar, then click '
                '**Run Analysis** to begin.')


if __name__ == '__main__':
    main()
