# 🔍 AI Stock Research Agent

An agentic stock research and watchlist-building assistant. Type any sector or field,
and the app discovers relevant publicly-traded stocks, pulls live financials, SEC insider
filings, congressional trades and news, then runs a Gemini-powered analysis with conviction
scores and categorised watchlists — all from free data sources.

## Setup

1. Copy these files into an empty directory.
2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate      # Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Set your Gemini API key (or enter it in the sidebar at runtime):
   ```bash
   export GEMINI_API_KEY=AIza...   # Windows: set GEMINI_API_KEY=...
   ```
   Get a free key at https://aistudio.google.com/apikey
5. Launch the app:
   ```bash
   streamlit run app.py
   ```
   Open http://localhost:8501.

## How to use

- **Gemini API key** — paste it in the sidebar (free key from Google AI Studio).
- **Sector text box** — type any field, e.g. `AI infrastructure`, `defense tech`, `biotech`.
- **Number of stocks slider** — choose how many stocks to analyse (3–15).
- **Run Analysis** — the app discovers stocks, fetches data, and builds the report.

Results are organised into 8 tabs:

| Tab | Contents |
|-----|----------|
| 📊 Daily Brief | AI-generated market summary for the sector |
| 🏆 Top Picks | Per-stock report cards, ranked by conviction |
| 🏛 Politician Trading | Congressional trades found across the stocks |
| 👔 Insider Activity | SEC Form 4 insider filings |
| 📈 Momentum Plays | Stocks the AI tagged as momentum |
| 💎 Long-Term Compounders | Quality compounders |
| ⚡ High Risk/Reward | Higher-risk, higher-upside ideas |
| 💰 Undervalued | Stocks flagged as undervalued |

## Data sources

| Source | Data | Cost |
|--------|------|------|
| yfinance | Prices, fundamentals, news | Free, no key |
| SEC EDGAR | Form 4 insider filings | Free, no auth |
| Senate / House Stock Watcher | Congressional trades | Free, no auth |
| Google Gemini API | AI analysis | Free API key required |

## Limitations

- yfinance data may lag real time by ~15 minutes.
- Politician trading data updates daily and may lag official reports.
- Insider data depends on SEC filing speed (Form 4s appear ~2 business days after a trade).

## Disclaimer

This tool is for research support only and does not constitute financial advice.
Always conduct your own due diligence before making any investment decision.
