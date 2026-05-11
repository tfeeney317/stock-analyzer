from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.services.stock_service import StockService
from app.services.watchlist_service import WatchlistService

app = FastAPI(title="Stock Analyzer API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

stock_service = StockService()
watchlist_service = WatchlistService()

@app.get("/")
def root():
    return {"message": "Stock Analyzer API", "version": "1.0.0"}

@app.get("/api/stock/{ticker}")
async def get_stock_data(ticker: str):
    """Get comprehensive stock data including price, info, financials"""
    return await stock_service.get_stock_data(ticker.upper())

@app.get("/api/stock/{ticker}/financials")
async def get_financials(ticker: str):
    """Get detailed financial statements"""
    return await stock_service.get_financials(ticker.upper())

@app.get("/api/stock/{ticker}/analysis")
async def get_analysis(ticker: str):
    """Get complete stock analysis"""
    return await stock_service.get_complete_analysis(ticker.upper())

@app.get("/api/search")
async def search_stocks(q: str):
    """Search for stocks by name or ticker"""
    return await stock_service.search_stocks(q)

@app.get("/api/market/overview")
async def get_market_overview():
    """Get market overview with major indices"""
    return await stock_service.get_market_overview()

@app.get("/api/stock/{ticker}/quote")
async def get_realtime_quote(ticker: str):
    """Get real-time stock quote"""
    return await stock_service.get_realtime_quote(ticker.upper())

@app.get("/api/stock/{ticker}/news")
async def get_stock_news(ticker: str):
    """Get latest news for a stock"""
    return await stock_service.get_market_news(ticker.upper())

@app.get("/api/stock/{ticker}/sentiment")
async def get_stock_sentiment(ticker: str):
    """Get news sentiment analysis for a stock"""
    return await stock_service.get_stock_news_sentiment(ticker.upper())

@app.get("/api/stock/{ticker}/events")
async def get_company_events(ticker: str):
    """Get upcoming company events (earnings, dividends)"""
    return await stock_service.get_company_events(ticker.upper())

@app.get("/api/stock/{ticker}/position")
async def get_position_analysis(ticker: str, entry_price: float = None):
    """Get position analysis for stock holders - buy/sell/hold recommendation"""
    return await stock_service.analyze_position(ticker.upper(), entry_price)

@app.get("/api/market/movers")
async def get_movers():
    """Get top gainers and losers"""
    return await stock_service.get_movers()

@app.get("/api/market/news")
async def get_market_news():
    """Get general market news"""
    return await stock_service.get_market_news("")

@app.get("/api/watchlist")
async def get_watchlist():
    """Get watchlist with current prices"""
    prices = watchlist_service.get_watchlist_prices()
    return {"watchlist": watchlist_service.get_watchlist(), "prices": prices}

@app.post("/api/watchlist/add")
async def add_to_watchlist(ticker: str, name: str = ""):
    """Add stock to watchlist"""
    return watchlist_service.add_to_watchlist(ticker, name)

@app.post("/api/watchlist/remove")
async def remove_from_watchlist(ticker: str):
    """Remove stock from watchlist"""
    return watchlist_service.remove_from_watchlist(ticker)

@app.get("/api/watchlist/prices")
async def get_watchlist_prices():
    """Get real-time prices for watchlist"""
    return watchlist_service.get_watchlist_prices()

@app.get("/api/alerts")
async def get_alerts():
    """Get all alerts"""
    return {"alerts": watchlist_service.get_alerts()}

@app.post("/api/alerts/create")
async def create_alert(ticker: str, alert_type: str, threshold: float):
    """Create a price alert"""
    return watchlist_service.create_alert(ticker, alert_type, threshold)

@app.post("/api/alerts/delete")
async def delete_alert(alert_id: int):
    """Delete an alert"""
    return watchlist_service.delete_alert(alert_id)

@app.get("/api/alerts/check")
async def check_alerts():
    """Check if any alerts are triggered"""
    return {"triggered": watchlist_service.check_all_alerts()}

@app.get("/api/alerts/types")
async def get_alert_types():
    """Get available alert types"""
    return {"types": watchlist_service.get_available_alert_types()}

@app.get("/api/alerts/history")
async def get_alert_history():
    """Get alert history"""
    return {"history": watchlist_service.get_alert_history()}

@app.post("/api/alerts/clear")
async def clear_alerts():
    """Clear triggered alerts"""
    return watchlist_service.clear_triggered_alerts()

# Notification endpoints
from app.services.notification_service import notification_service

@app.get("/api/notifications/config")
async def get_notification_config():
    """Get notification configuration"""
    return {"config": notification_service.get_config()}

@app.post("/api/notifications/config")
async def update_notification_config(config: dict):
    """Update notification configuration"""
    return notification_service.update_config(config)

@app.post("/api/notifications/test")
async def test_notification(method: str):
    """Test a specific notification method"""
    return notification_service.test_notification(method)

# New powerful analysis endpoints
@app.get("/api/stock/options/{ticker}")
async def get_options(ticker: str):
    """Get options chain with IV data"""
    return await stock_service.get_options_data(ticker)

@app.get("/api/stock/ownership/{ticker}")
async def get_ownership(ticker: str):
    """Get institutional ownership"""
    return await stock_service.get_institutional_ownership(ticker)

@app.get("/api/stock/insiders/{ticker}")
async def get_insiders(ticker: str):
    """Get insider activity"""
    return await stock_service.get_insider_activity(ticker)

@app.get("/api/stock/targets/{ticker}")
async def get_targets(ticker: str):
    """Get analyst price targets"""
    return await stock_service.get_analyst_targets(ticker)

@app.get("/api/stock/strength/{ticker}")
async def get_strength(ticker: str):
    """Get relative strength vs sector/SPY"""
    return await stock_service.get_relative_strength(ticker)

@app.get("/api/stock/dcf/{ticker}")
async def get_dcf(ticker: str):
    """Get DCF fair value"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, stock_service.calculate_dcf, ticker)

@app.get("/api/stock/gaps/{ticker}")
async def get_gaps(ticker: str):
    """Get gap analysis"""
    return await stock_service.get_gap_analysis(ticker)