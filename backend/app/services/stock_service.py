import yfinance as yf
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
import requests
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import asyncio

class StockService:
    def __init__(self):
        self.cache = {}
        self.news_cache = {}
        self.executor = ThreadPoolExecutor(max_workers=10)
        
    def _get_cached(self, key: str, max_age_seconds: int = 60) -> Optional[Any]:
        if key in self.cache:
            cached_data, cached_time = self.cache[key]
            if (datetime.now() - cached_time).total_seconds() < max_age_seconds:
                return cached_data
        return None
    
    def _set_cached(self, key: str, data: Any):
        self.cache[key] = (data, datetime.now())

    def _safe_float(self, val):
        try:
            return float(val) if val is not None else 0
        except:
            return 0
    
    def _clean_value(self, val):
        """Convert numpy/pandas types to JSON-serializable Python types"""
        if val is None:
            return None
        if isinstance(val, (np.integer, np.int64, np.int32)):
            return int(val)
        if isinstance(val, (np.floating, np.float64, np.float32)):
            v = float(val)
            if v != v:  # NaN check
                return None
            return v
        if isinstance(val, np.bool_):
            return bool(val)
        if isinstance(val, pd.Timestamp):
            return str(val)
        if isinstance(val, (np.bool_, np.string_)):
            return str(val)
        return val
    
    def _clean_dict(self, d: Dict) -> Dict:
        """Recursively clean a dict of NaN and numpy types"""
        if not d:
            return d
        result = {}
        for k, v in d.items():
            if isinstance(v, dict):
                result[k] = self._clean_dict(v)
            elif isinstance(v, list):
                result[k] = [self._clean_value(x) for x in v]
            else:
                result[k] = self._clean_value(v)
        return result

    async def get_stock_data(self, ticker: str) -> Dict[str, Any]:
        loop = asyncio.get_event_loop()
        try:
            stock = await loop.run_in_executor(self.executor, yf.Ticker, ticker)
            info = await loop.run_in_executor(self.executor, lambda: stock.info)
            return {"ticker": ticker, "data": info}
        except Exception as e:
            return {"error": str(e), "ticker": ticker}

    async def get_realtime_quote(self, ticker: str) -> Dict[str, Any]:
        loop = asyncio.get_event_loop()
        try:
            stock = await loop.run_in_executor(self.executor, yf.Ticker, ticker)
            info = await loop.run_in_executor(self.executor, lambda: stock.info)
            return {
                "ticker": ticker.upper(),
                "price": self._safe_float(info.get("currentPrice") or info.get("regularMarketPrice")),
                "previous_close": self._safe_float(info.get("regularMarketPreviousClose") or info.get("previousClose")),
                "change": self._safe_float(info.get("regularMarketChange")),
                "change_percent": round(self._safe_float(info.get("regularMarketChangePercent")), 2),
                "volume": int(info.get("volume", 0) or 0),
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            return {"error": str(e)}

    async def get_market_news(self, ticker: str = "") -> List[Dict[str, Any]]:
        cache_key = f"news_{ticker}"
        cached = self._get_cached(cache_key, 180)
        if cached:
            return cached
        
        news_items = []
        seen_titles = set()
        
        def add_news(title, link, publisher, published, source):
            if title and title not in seen_titles and len(title) > 10:
                seen_titles.add(title)
                news_items.append({
                    "title": title[:300],
                    "link": link or "",
                    "publisher": publisher or "Unknown",
                    "published": published or "",
                    "source": source
                })
        
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        
        # 1. Yahoo Finance via API (fastest)
        try:
            url = f"https://query1.finance.yahoo.com/v1/finance/search?q={ticker or 'stock market'}&newsCount=15&category=news"
            response = requests.get(url, headers=headers, timeout=8)
            if response.status_code == 200:
                data = response.json()
                articles = data.get("news", []) or []
                for item in articles:
                    add_news(
                        item.get("title", ""),
                        item.get("link", ""),
                        item.get("publisher", "Yahoo Finance"),
                        item.get("time", ""),
                        "Yahoo Finance"
                    )
        except:
            pass
        
        # 2. yfinance news (backup)
        if len(news_items) < 5:
            try:
                loop = asyncio.get_event_loop()
                stock = await loop.run_in_executor(self.executor, yf.Ticker, ticker or "SPY")
                news = await loop.run_in_executor(self.executor, lambda: stock.news)
                if news and len(news) > 0:
                    for item in news[:10]:
                        add_news(
                            item.get("title", ""),
                            item.get("link", ""),
                            item.get("publisher", "Yahoo Finance"),
                            item.get("published", ""),
                            "Yahoo Finance"
                        )
            except:
                pass
        
        # 3. Finnhub (fast, free)
        if len(news_items) < 8:
            try:
                url = "https://finnhub.io/api/v1/news?category=general"
                response = requests.get(url, headers=headers, timeout=5)
                if response.status_code == 200:
                    articles = response.json()[:15]
                    for item in articles:
                        headline = item.get("headline", "")
                        if not ticker or ticker.upper() in headline.upper():
                            add_news(
                                headline,
                                item.get("url", ""),
                                item.get("source", "Finnhub"),
                                item.get("datetime", ""),
                                "Finnhub"
                            )
            except:
                pass
        
        if len(news_items) == 0:
            news_items = [{
                "title": f"Market update for {ticker}" if ticker else "Market news",
                "link": f"https://finance.yahoo.com/quote/{ticker}" if ticker else "https://finance.yahoo.com",
                "publisher": "Yahoo Finance",
                "published": datetime.now().isoformat(),
                "source": "Fallback"
            }]
        
        self._set_cached(cache_key, news_items[:15])
        return news_items[:15]

    async def get_stock_news_sentiment(self, ticker: str) -> Dict[str, Any]:
        news = await self.get_market_news(ticker)
        
        positive_keywords = ["surge", "gain", "bullish", "upgrade", "beat", "growth", "profit", "rally", "soar", "outperform", "record", "high", "breakout", "beat"]
        negative_keywords = ["drop", "fall", "bearish", "downgrade", "miss", "loss", "crash", "warn", "risk", "lawsuit", "recall", "investigation", "plunge", "sell"]
        
        positive_count = 0
        negative_count = 0
        
        for item in news[:10]:
            title = (item.get("title", "") or "").lower()
            if any(kw in title for kw in positive_keywords):
                positive_count += 1
            elif any(kw in title for kw in negative_keywords):
                negative_count += 1
        
        total = positive_count + negative_count
        sentiment_score = ((positive_count - negative_count) / (total or 1)) * 100 if total > 0 else 0
        
        return {
            "ticker": ticker,
            "sentiment_score": round(sentiment_score, 2),
            "sentiment_label": "Positive" if sentiment_score > 20 else "Negative" if sentiment_score < -20 else "Neutral",
            "positive_articles": positive_count,
            "negative_articles": negative_count,
            "neutral_articles": len(news) - positive_count - negative_count,
            "recent_headlines": [n.get("title", "") for n in news[:5]],
            "sources": list(set([n.get("source", "Unknown") for n in news[:5]])),
            "timestamp": datetime.now().isoformat()
        }

    async def get_movers(self) -> Dict[str, Any]:
        cache_key = "movers"
        cached = self._get_cached(cache_key, 300)
        if cached:
            return cached
        
        movers = {"gainers": [], "losers": []}
        
        try:
            tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "NFLX", "AMD", "INTC",
                      "JPM", "BAC", "WFC", "GS", "V", "MA", "JNJ", "UNH", "PFE", "ABBV"]
            
            loop = asyncio.get_event_loop()
            
            def fetch_ticker(t):
                try:
                    stock = yf.Ticker(t)
                    info = stock.info
                    price = self._safe_float(info.get("currentPrice") or info.get("regularMarketPrice"))
                    prev = self._safe_float(info.get("regularMarketPreviousClose") or info.get("previousClose"))
                    if prev and price > 0:
                        change = ((price - prev) / prev) * 100
                        return {
                            "ticker": t,
                            "name": info.get("shortName", t) or t,
                            "price": price,
                            "change_percent": round(change, 2),
                            "volume": int(info.get("volume", 0) or 0)
                        }
                except:
                    pass
                return None
            
            results = await asyncio.gather(*[loop.run_in_executor(self.executor, fetch_ticker, t) for t in tickers])
            
            for r in results:
                if r:
                    if r["change_percent"] > 0:
                        movers["gainers"].append(r)
                    else:
                        movers["losers"].append(r)
            
            movers["gainers"].sort(key=lambda x: x["change_percent"], reverse=True)
            movers["losers"].sort(key=lambda x: x["change_percent"])
            movers["gainers"] = movers["gainers"][:10]
            movers["losers"] = movers["losers"][:10]
            
        except Exception as e:
            movers["error"] = str(e)
        
        self._set_cached(cache_key, movers)
        return movers

    async def get_company_events(self, ticker: str) -> Dict[str, Any]:
        try:
            loop = asyncio.get_event_loop()
            stock = await loop.run_in_executor(self.executor, yf.Ticker, ticker)
            info = await loop.run_in_executor(self.executor, lambda: stock.info)
            
            events = {"earnings_date": None, "dividend_date": None, "ex_dividend_date": None}
            
            # Try to get earnings date from calendar (dict format)
            try:
                calendar = await loop.run_in_executor(self.executor, lambda: stock.calendar)
                if calendar and isinstance(calendar, dict):
                    earnings_dates = calendar.get("Earnings Date")
                    if earnings_dates and len(earnings_dates) > 0:
                        events["earnings_date"] = str(earnings_dates[0])
                    
                    div_date = calendar.get("Dividend Date")
                    if div_date:
                        events["dividend_date"] = str(div_date)
                    
                    ex_div = calendar.get("Ex-Dividend Date")
                    if ex_div:
                        events["ex_dividend_date"] = str(ex_div)
            except:
                pass
            
            # Also check info for earnings date as backup
            if not events["earnings_date"]:
                earnings_ts = info.get("earningsDate")
                if earnings_ts is not None:
                    try:
                        events["earnings_date"] = str(earnings_ts)[:10]
                    except:
                        pass
            
            return events
        except Exception as e:
            return {"earnings_date": None, "dividend_date": None}

    async def get_financials(self, ticker: str) -> Dict[str, Any]:
        try:
            loop = asyncio.get_event_loop()
            stock = await loop.run_in_executor(self.executor, yf.Ticker, ticker)
            
            def get_financials_sync():
                return {
                    "income_stmt": stock.income_stmt,
                    "balance_sheet": stock.balance_sheet,
                    "cashflow": stock.cashflow
                }
            
            financials = await loop.run_in_executor(self.executor, get_financials_sync)
            
            return {
                "ticker": ticker,
                "income_statement": self._parse_financial_data(financials["income_stmt"]),
                "balance_sheet": self._parse_financial_data(financials["balance_sheet"]),
                "cash_flow": self._parse_financial_data(financials["cashflow"]),
            }
        except Exception as e:
            return {"error": str(e)}

    def _parse_financial_data(self, df: pd.DataFrame) -> Dict[str, Any]:
        if df is None or df.empty:
            return {}
        result = {}
        try:
            for col in df.columns:
                date_str = str(col.date()) if hasattr(col, 'date') else str(col)
                result[date_str] = {}
                for idx in df.index:
                    val = df.loc[idx, col]
                    if pd.notna(val):
                        result[date_str][str(idx)] = float(val)
        except:
            pass
        return result

    async def get_complete_analysis(self, ticker: str) -> Dict[str, Any]:
        cache_key = f"analysis_{ticker.upper()}"
        cached = self._get_cached(cache_key, 300)
        if cached:
            return cached
        
        loop = asyncio.get_event_loop()
        try:
            # First verify the ticker exists
            stock = await loop.run_in_executor(self.executor, yf.Ticker, ticker.upper())
            info = await loop.run_in_executor(self.executor, lambda: stock.info)
            
            # Check if we got valid data
            if not info or not info.get("shortName"):
                return {"error": f"Ticker '{ticker.upper()}' not found", "ticker": ticker.upper()}
            
            analysis = {
                "ticker": ticker.upper(),
                "timestamp": datetime.now().isoformat(),
                "sources": ["Yahoo Finance", "yfinance"],
                "business_model": self._analyze_business_model(info),
                "revenue_drivers": self._analyze_revenue_drivers(info),
                "competitive_position": self._analyze_competitive_position(info),
                "financial_health": await self._analyze_financial_health_async(ticker),
                "valuation": self._analyze_valuation(info),
                "industry": self._analyze_industry(info),
                "risks": self._analyze_risks(info),
                "technical": await self._analyze_technical(ticker),
                "realtime_quote": await self.get_realtime_quote(ticker),
                "events": await self.get_company_events(ticker),
            }
            
            self._set_cached(cache_key, analysis)
            return analysis
        except Exception as e:
            error_msg = str(e)
            # Check for common errors
            if "404" in error_msg or "Not Found" in error_msg:
                return {"error": f"Ticker '{ticker.upper()}' not found. Please check the symbol and try again.", "ticker": ticker.upper()}
            return {"error": f"Failed to get analysis: {error_msg}", "ticker": ticker.upper()}

    async def analyze_position(self, ticker: str, entry_price: float = None) -> Dict[str, Any]:
        """Analyze a stock position and provide buy/sell/hold recommendations"""
        try:
            loop = asyncio.get_event_loop()
            
            # Get current data
            stock = await loop.run_in_executor(self.executor, yf.Ticker, ticker.upper())
            info = await loop.run_in_executor(self.executor, lambda: stock.info)
            technical = await self._analyze_technical(ticker)
            valuation = self._analyze_valuation(info)
            
            current_price = self._safe_float(info.get("currentPrice"))
            if not current_price:
                return {"error": "Unable to get current price"}
            
            # If user provided entry price, use it; otherwise use current
            avg_entry = entry_price if entry_price else current_price
            
            signals = []
            recommendation = "HOLD"
            confidence = 50
            
            # 1. TECHNICAL SIGNALS
            rsi = technical.get("rsi", 50)
            if rsi < 30:
                signals.append({"type": "Technical", "signal": "STRONG_BUY", "reason": f"RSI {rsi:.0f} - Oversold", "weight": 15})
            elif rsi < 40:
                signals.append({"type": "Technical", "signal": "BUY", "reason": f"RSI {rsi:.0f} - Approaching support", "weight": 10})
            elif rsi > 70:
                signals.append({"type": "Technical", "signal": "STRONG_SELL", "reason": f"RSI {rsi:.0f} - Overbought", "weight": 15})
            elif rsi > 60:
                signals.append({"type": "Technical", "signal": "SELL", "reason": f"RSI {rsi:.0f} - Nearing resistance", "weight": 10})
            else:
                signals.append({"type": "Technical", "signal": "NEUTRAL", "reason": f"RSI {rsi:.0f} - Neutral", "weight": 5})
            
            # MACD
            macd_hist = technical.get("macd_histogram", 0)
            if macd_hist > 2:
                signals.append({"type": "Momentum", "signal": "BUY", "reason": "Strong bullish momentum", "weight": 12})
            elif macd_hist > 0:
                signals.append({"type": "Momentum", "signal": "BUY", "reason": "Bullish MACD", "weight": 8})
            elif macd_hist < -2:
                signals.append({"type": "Momentum", "signal": "SELL", "reason": "Strong bearish momentum", "weight": 12})
            elif macd_hist < 0:
                signals.append({"type": "Momentum", "signal": "SELL", "reason": "Bearish MACD", "weight": 8})
            
            # Trend
            ma50 = technical.get("ma_50", 0)
            ma200 = technical.get("ma_200", 0)
            if ma200 and current_price > ma200:
                signals.append({"type": "Trend", "signal": "BUY", "reason": "Above 200-day MA (bullish)", "weight": 12})
            elif ma200 and current_price < ma200:
                signals.append({"type": "Trend", "signal": "SELL", "reason": "Below 200-day MA (bearish)", "weight": 12})
            elif ma50 and current_price > ma50:
                signals.append({"type": "Trend", "signal": "BUY", "reason": "Above 50-day MA (short-term up)", "weight": 8})
            elif ma50 and current_price < ma50:
                signals.append({"type": "Trend", "signal": "SELL", "reason": "Below 50-day MA (short-term down)", "weight": 8})
            
            # 2. VALUATION SIGNALS
            pe = self._safe_float(info.get("trailingPE"))
            if pe and pe > 0:
                if pe < 15:
                    signals.append({"type": "Valuation", "signal": "BUY", "reason": f"P/E {pe:.0f} - Attractive", "weight": 12})
                elif pe < 20:
                    signals.append({"type": "Valuation", "signal": "BUY", "reason": f"P/E {pe:.0f} - Reasonable", "weight": 8})
                elif pe > 50:
                    signals.append({"type": "Valuation", "signal": "SELL", "reason": f"P/E {pe:.0f} - Expensive", "weight": 12})
                elif pe > 35:
                    signals.append({"type": "Valuation", "signal": "SELL", "reason": f"P/E {pe:.0f} - High", "weight": 8})
            
            peg = self._safe_float(info.get("pegRatio"))
            if peg and peg > 0:
                if peg < 1:
                    signals.append({"type": "Valuation", "signal": "BUY", "reason": f"PEG {peg:.2f} - Growth at fair price", "weight": 10})
                elif peg > 2:
                    signals.append({"type": "Valuation", "signal": "SELL", "reason": f"PEG {peg:.2f} - Overvalued", "weight": 10})
            
            # 3. ANALYST SIGNALS
            target = self._safe_float(info.get("targetMeanPrice"))
            if target and current_price:
                upside = ((target - current_price) / current_price) * 100
                if upside > 30:
                    signals.append({"type": "Analyst", "signal": "BUY", "reason": f"{upside:.0f}% upside to target", "weight": 12})
                elif upside > 15:
                    signals.append({"type": "Analyst", "signal": "BUY", "reason": f"{upside:.0f}% upside", "weight": 8})
                elif upside < -15:
                    signals.append({"type": "Analyst", "signal": "SELL", "reason": f"{abs(upside):.0f}% downside", "weight": 12})
            
            rating = info.get("recommendationKey", "")
            if rating in ["strongBuy", "buy"]:
                signals.append({"type": "Analyst", "signal": "BUY", "reason": f"Rating: {rating.replace('_', ' ').title()}", "weight": 10})
            elif rating in ["strongSell", "sell"]:
                signals.append({"type": "Analyst", "signal": "SELL", "reason": f"Rating: {rating.replace('_', ' ').title()}", "weight": 10})
            
            # 4. MOMENTUM SIGNALS
            change_1m = technical.get("1m_change", 0)
            if change_1m > 15:
                signals.append({"type": "Momentum", "signal": "SELL", "reason": f"+{change_1m:.0f}% - Take profits", "weight": 10})
            elif change_1m > 8:
                signals.append({"type": "Momentum", "signal": "HOLD", "reason": f"+{change_1m:.0f}% - Strong run", "weight": 5})
            elif change_1m < -15:
                signals.append({"type": "Momentum", "signal": "BUY", "reason": f"{change_1m:.0f}% - Potential bottom", "weight": 10})
            
            # 5. PRICE LEVEL SIGNALS
            price_position = technical.get("price_position", 50)
            if price_position < 15:
                signals.append({"type": "Technical", "signal": "BUY", "reason": f"At 52-week low - high upside", "weight": 15})
            elif price_position > 85:
                signals.append({"type": "Technical", "signal": "SELL", "reason": f"Near 52-week high - limited upside", "weight": 15})
            
            # 6. RISK SIGNALS
            beta = self._safe_float(info.get("beta"))
            if beta > 1.5:
                signals.append({"type": "Risk", "signal": "SELL", "reason": f"High beta ({beta:.1f})", "weight": 8})
            elif beta < 0.8:
                signals.append({"type": "Risk", "signal": "BUY", "reason": f"Low beta ({beta:.1f}) - defensive", "weight": 6})
            
            debt_to_eq = self._safe_float(info.get("debtToEquity"))
            if debt_to_eq > 150:
                signals.append({"type": "Financial", "signal": "SELL", "reason": f"High debt ({debt_to_eq:.0f}%)", "weight": 10})
            elif debt_to_eq < 50:
                signals.append({"type": "Financial", "signal": "BUY", "reason": f"Low debt ({debt_to_eq:.0f}%)", "weight": 6})
            
            # CALCULATE FINAL RECOMMENDATION
            buy_score = sum(s["weight"] for s in signals if s["signal"] in ["BUY", "STRONG_BUY"])
            sell_score = sum(s["weight"] for s in signals if s["signal"] in ["SELL", "STRONG_SELL"])
            
            if buy_score > sell_score + 20:
                recommendation = "STRONG_BUY"
                confidence = min(95, 50 + (buy_score - sell_score))
            elif buy_score > sell_score:
                recommendation = "BUY"
                confidence = min(85, 50 + (buy_score - sell_score))
            elif sell_score > buy_score + 20:
                recommendation = "STRONG_SELL"
                confidence = min(95, 50 + (sell_score - buy_score))
            elif sell_score > buy_score:
                recommendation = "SELL"
                confidence = min(85, 50 + (sell_score - buy_score))
            else:
                recommendation = "HOLD"
                confidence = 50
            
            # Determine action
            if recommendation == "STRONG_BUY":
                action = "ADD"
                short_action = "Add"
            elif recommendation == "BUY":
                action = "ACCUMULATE"
                short_action = "Buy"
            elif recommendation == "STRONG_SELL":
                action = "REDUCE"
                short_action = "Reduce"
            elif recommendation == "SELL":
                action = "SELL PARTIAL"
                short_action = "Sell"
            else:
                action = "HOLD"
                short_action = "Hold"
            
            # Position metrics
            support = technical.get("support", current_price)
            resistance = technical.get("resistance", current_price)
            risk = current_price - support
            reward = resistance - current_price
            risk_reward = round(reward / risk, 2) if risk > 0 else 0
            
            # Calculate P&L if entry provided
            pnl_percent = 0
            pnl_amount = 0
            if entry_price and entry_price > 0:
                pnl_percent = ((current_price - entry_price) / entry_price) * 100
                pnl_amount = current_price - entry_price
            
            # Time horizon recommendation
            signal_str = str(technical.get("signal", "")).lower()
            trend_str = str(technical.get("trend", "")).lower()
            
            if "bullish" in signal_str and "up" in trend_str:
                time_horizon = "Long-term hold - trend is bullish"
            elif "bearish" in signal_str:
                time_horizon = "Short-term only - consider exiting"
            else:
                time_horizon = "Medium-term hold - monitor for trend change"
            
            # Position sizing advice
            beta = self._safe_float(info.get("beta"))
            volatility = technical.get("volatility", "Medium")
            if volatility == "High" or beta > 1.5:
                position_size = "Reduce position to 5-10% of portfolio"
            elif volatility == "Low" and beta < 1:
                position_size = "Can hold up to 15-20% of portfolio"
            else:
                position_size = "Maintain 10-15% of portfolio"
            
            # Key levels to watch
            levels = {
                "immediate_support": round(support, 2),
                "second_support": round(support * 0.95, 2),
                "immediate_resistance": round(resistance, 2),
                "second_resistance": round(resistance * 1.05, 2),
            }
            
            position_metrics = {
                "current_price": current_price,
                "support_level": support,
                "resistance_level": resistance,
                "risk_reward_ratio": risk_reward,
                "distance_to_support": round((current_price - support) / current_price * 100, 1),
                "distance_to_resistance": round((resistance - current_price) / current_price * 100, 1),
                "52_week_high": technical.get("52_week_high"),
                "52_week_low": technical.get("52_week_low"),
                "volatility": technical.get("volatility"),
                "momentum": technical.get("momentum"),
                "entry_price": avg_entry,
                "pnl_percent": round(pnl_percent, 2),
                "pnl_amount": round(pnl_amount, 2),
                "in_profit": pnl_percent > 0 if entry_price else None,
            }
            
            return {
                "ticker": ticker.upper(),
                "recommendation": recommendation,
                "action": action,
                "short_action": short_action,
                "confidence": confidence,
                "buy_score": buy_score,
                "sell_score": sell_score,
                "signals": signals[:8],  # Top 8 signals
                "position_metrics": position_metrics,
                "advanced_analysis": {
                    "time_horizon": time_horizon,
                    "position_size_advice": position_size,
                    "key_levels": levels,
                    "stop_loss": round(support * 0.95, 2),
                    "take_profit_1": round(resistance, 2),
                    "take_profit_2": round(resistance * 1.10, 2),
                },
                "timestamp": datetime.now().isoformat(),
            }
            
        except Exception as e:
            return {"error": str(e)}

    def _analyze_business_model(self, info: Dict) -> Dict[str, Any]:
        return {
            "description": (info.get("longBusinessSummary") or info.get("businessSummary") or "N/A")[:800],
            "sector": info.get("sector") or "N/A",
            "industry": info.get("industry") or "N/A",
            "employees": info.get("fullTimeEmployees") or 0,
            "website": info.get("website") or "N/A",
            "ceo": info.get("ceo") or "N/A",
            "headquarters": f"{info.get('city', 'N/A')}, {info.get('country', 'N/A')}"
        }

    def _analyze_revenue_drivers(self, info: Dict) -> Dict[str, Any]:
        revenue_growth = self._safe_float(info.get("revenueGrowth"))
        earnings_growth = self._safe_float(info.get("earningsGrowth"))
        gross_margin = self._safe_float(info.get("grossMargins"))
        operating_margin = self._safe_float(info.get("operatingMargins"))
        profit_margin = self._safe_float(info.get("profitMargins"))
        
        return {
            "revenue_growth": round(revenue_growth * 100, 2),
            "earnings_growth": round(earnings_growth * 100, 2),
            "gross_margin": round(gross_margin * 100, 2),
            "operating_margin": round(operating_margin * 100, 2),
            "profit_margin": round(profit_margin * 100, 2),
            "revenue": self._safe_float(info.get("totalRevenue")),
            "revenue_past_5_years": self._safe_float(info.get("revenuePerShareHistorical5Y")),
            "ebitda": self._safe_float(info.get("ebitda")),
            "ebitda_margin": round(self._safe_float(info.get("ebitdaMargins")) * 100, 2),
            "gross_profit": self._safe_float(info.get("grossProfit")),
            "operating_income": self._safe_float(info.get("operatingIncome")),
            "net_income": self._safe_float(info.get("netIncome")),
            "ebit": self._safe_float(info.get("ebit")),
            "free_cash_flow": self._safe_float(info.get("freeCashflow")),
            "operating_cash_flow": self._safe_float(info.get("operatingCashflow")),
            "capital_expenditure": self._safe_float(info.get("capitalExpenditure")),
            "dividend_yield": round(self._safe_float(info.get("dividendYield")) * 100, 2),
            "dividend_rate": self._safe_float(info.get("dividendRate")),
            "payout_ratio": round(self._safe_float(info.get("payoutRatio")) * 100, 2) if info.get("payoutRatio") else None,
            "revenue_quarterly_growth": round(self._safe_float(info.get("revenueQuarterlyGrowth")) * 100, 2),
            "earnings_quarterly_growth": round(self._safe_float(info.get("earningsQuarterlyGrowth")) * 100, 2),
        }

    def _analyze_competitive_position(self, info: Dict) -> Dict[str, Any]:
        return {
            "market_cap": self._safe_float(info.get("marketCap")),
            "enterprise_value": self._safe_float(info.get("enterpriseValue")),
            "pe_ratio": round(self._safe_float(info.get("trailingPE")), 2),
            "forward_pe": round(self._safe_float(info.get("forwardPE")), 2),
            "peg_ratio": round(self._safe_float(info.get("pegRatio")), 2),
            "debt_to_equity": round(self._safe_float(info.get("debtToEquity")), 2),
            "return_on_equity": round(self._safe_float(info.get("returnOnEquity")) * 100, 2),
            "return_on_assets": round(self._safe_float(info.get("returnOnAssets")) * 100, 2),
            "return_on_capital": round(self._safe_float(info.get("returnOnCapital")) * 100, 2),
            "analyst_rating": info.get("recommendationKey") or "N/A",
            "target_mean_price": self._safe_float(info.get("targetMeanPrice")),
            "target_low_price": self._safe_float(info.get("targetLowPrice")),
            "target_high_price": self._safe_float(info.get("targetHighPrice")),
            "beta": round(self._safe_float(info.get("beta")), 2),
            "average_volume": int(self._safe_float(info.get("averageVolume"))),
            "average_volume_10day": int(self._safe_float(info.get("averageVolume10days"))),
            "current_volume": int(self._safe_float(info.get("volume"))),
            "float_shares": self._safe_float(info.get("floatShares")),
            "shares_outstanding": self._safe_float(info.get("sharesOutstanding")),
            "insider_ownership": round(self._safe_float(info.get("insiderOwnership")) * 100, 2),
            "institutional_ownership": round(self._safe_float(info.get("institutionOwnership")) * 100, 2),
            "exchange": info.get("exchange") or "N/A",
            "currency": info.get("currency") or "USD",
        }

    async def _analyze_financial_health_async(self, ticker: str) -> Dict[str, Any]:
        try:
            loop = asyncio.get_event_loop()
            stock = await loop.run_in_executor(self.executor, yf.Ticker, ticker)
            
            balance_data = await loop.run_in_executor(self.executor, lambda: stock.balance_sheet)
            cashflow_data = await loop.run_in_executor(self.executor, lambda: stock.cashflow)
            info = await loop.run_in_executor(self.executor, lambda: stock.info)
            
            total_debt = 0
            total_equity = 0
            total_assets = 0
            operating_cf = 0
            capex = 0
            
            if balance_data is not None and not balance_data.empty:
                try:
                    if 'Total Debt' in balance_data.index:
                        total_debt = self._safe_float(balance_data.loc['Total Debt'].iloc[0])
                    if 'Total Stockholder Equity' in balance_data.index:
                        total_equity = self._safe_float(balance_data.loc['Total Stockholder Equity'].iloc[0])
                    if 'Total Assets' in balance_data.index:
                        total_assets = self._safe_float(balance_data.loc['Total Assets'].iloc[0])
                except:
                    pass
            
            if cashflow_data is not None and not cashflow_data.empty:
                try:
                    if 'Operating Cash Flow' in cashflow_data.index:
                        operating_cf = self._safe_float(cashflow_data.loc['Operating Cash Flow'].iloc[0])
                    if 'Capital Expenditure' in cashflow_data.index:
                        capex = self._safe_float(cashflow_data.loc['Capital Expenditure'].iloc[0])
                except:
                    pass
            
            return {
                "debt_to_equity": round((total_debt / total_equity * 100) if total_equity > 0 else 0, 2),
                "debt_to_assets": round((total_debt / total_assets * 100) if total_assets > 0 else 0, 2),
                "current_ratio": round(self._safe_float(info.get("currentRatio")), 2),
                "quick_ratio": round(self._safe_float(info.get("quickRatio")), 2),
                "free_cash_flow": operating_cf + capex,
                "operating_cash_flow": operating_cf,
                "cash_position": self._safe_float(info.get("totalCash")),
                "total_debt": total_debt,
                "total_equity": total_equity,
                "red_flags": self._identify_red_flags(info, total_debt),
            }
        except Exception as e:
            return {"error": str(e), "debt_to_equity": 0, "current_ratio": 0}

    def _identify_red_flags(self, info: Dict, debt: float) -> list:
        flags = []
        if self._safe_float(info.get("debtToEquity")) > 200:
            flags.append("High debt-to-equity ratio (>200%)")
        if self._safe_float(info.get("currentRatio")) < 1:
            flags.append("Low current ratio (<1)")
        if self._safe_float(info.get("profitMargins")) < 0:
            flags.append("Negative profit margins")
        if self._safe_float(info.get("operatingMargins")) < 0:
            flags.append("Negative operating margins")
        return flags

    def _analyze_valuation(self, info: Dict) -> Dict[str, Any]:
        pe = self._safe_float(info.get("trailingPE"))
        fwd_pe = self._safe_float(info.get("forwardPE"))
        peg = self._safe_float(info.get("pegRatio"))
        price_to_book = self._safe_float(info.get("priceToBook"))
        price_to_sales = self._safe_float(info.get("priceToSalesTrailing12Months"))
        price_to_cashflow = self._safe_float(info.get("priceToCashflow"))
        ev_to_ebitda = self._safe_float(info.get("enterpriseToEbitda"))
        ev_to_revenue = self._safe_float(info.get("enterpriseToRevenue"))
        
        current_price = self._safe_float(info.get("currentPrice"))
        target_price = self._safe_float(info.get("targetMeanPrice"))
        target_low = self._safe_float(info.get("targetLowPrice"))
        target_high = self._safe_float(info.get("targetHighPrice"))
        
        upside = ((target_price - current_price) / current_price * 100) if current_price > 0 and target_price > 0 else 0
        
        # Discounted Cash Flow estimate (simplified)
        try:
            cashflow = self._safe_float(info.get("operatingCashflow"))
            shares_outstanding = self._safe_float(info.get("sharesOutstanding"))
            growth_rate = self._safe_float(info.get("earningsGrowth")) / 100
            
            if cashflow and shares_outstanding and cashflow > 0:
                cf_per_share = cashflow / shares_outstanding
                # Simplified DCF with 10% discount rate and 3% terminal growth
                if growth_rate > 0:
                    dcf_value = cf_per_share * (1 + growth_rate) / (0.10 - growth_rate)
                else:
                    dcf_value = cf_per_share / 0.10
        except:
            dcf_value = None
        
        # Valuation assessment
        pe_score = 0
        if pe > 0 and pe < 15: pe_score = 2
        elif pe > 0 and pe < 25: pe_score = 1
        elif pe > 50: pe_score = -2
        elif pe > 35: pe_score = -1
        
        peg_score = 0
        if peg > 0 and peg < 1: peg_score = 2
        elif peg > 0 and peg < 1.5: peg_score = 1
        elif peg > 2: peg_score = -2
        elif peg > 1.5: peg_score = -1
        
        pb_score = 0
        if price_to_book > 0 and price_to_book < 3: pb_score = 2
        elif price_to_book > 0 and price_to_book < 5: pb_score = 1
        elif price_to_book > 15: pb_score = -2
        elif price_to_book > 10: pb_score = -1
        
        upside_score = 0
        if upside > 30: upside_score = 2
        elif upside > 15: upside_score = 1
        elif upside < -15: upside_score = -2
        elif upside < 0: upside_score = -1
        
        total_score = pe_score + peg_score + pb_score + upside_score
        
        if total_score >= 5:
            valuation_summary = "Significantly Undervalued"
        elif total_score >= 3:
            valuation_summary = "Undervalued"
        elif total_score >= 1:
            valuation_summary = "Fairly Valued"
        elif total_score >= -1:
            valuation_summary = "Slightly Overvalued"
        elif total_score >= -3:
            valuation_summary = "Overvalued"
        else:
            valuation_summary = "Significantly Overvalued"
        
        return {
            "trailing_pe": round(pe, 2),
            "forward_pe": round(fwd_pe, 2),
            "peg_ratio": round(peg, 2),
            "price_to_book": round(price_to_book, 2),
            "price_to_sales": round(price_to_sales, 2),
            "price_to_cashflow": round(price_to_cashflow, 2),
            "enterprise_value": self._safe_float(info.get("enterpriseValue")),
            "ev_to_ebitda": round(ev_to_ebitda, 2),
            "ev_to_revenue": round(ev_to_revenue, 2),
            "dcf_estimate": round(dcf_value, 2) if dcf_value else None,
            "analyst_targets": {
                "current": current_price,
                "mean": target_price,
                "low": target_low,
                "high": target_high,
                "upside_percent": round(upside, 2),
                "consensus": info.get("recommendationKey", "N/A"),
                "num_analysts": info.get("numberOfAnalystOpinions", 0),
            },
            "valuation_summary": valuation_summary,
            "valuation_score": total_score,
        }

    def _get_valuation_summary(self, pe: float, peg: float, pb: float, upside: float) -> str:
        if not pe or pe == 0:
            return "Insufficient data"
        if pe < 15 and peg < 1 and upside > 20:
            return "Undervalued"
        elif pe > 40 or peg > 2:
            return "Overvalued"
        return "Fairly Valued"

    def _analyze_industry(self, info: Dict) -> Dict[str, Any]:
        return {
            "sector": info.get("sector") or "N/A",
            "industry": info.get("industry") or "N/A",
            "industry_avg_pe": round(self._safe_float(info.get("sectorPE")), 2),
            "market_cap_category": self._get_market_cap_category(self._safe_float(info.get("marketCap"))),
        }

    def _get_market_cap_category(self, market_cap: float) -> str:
        if market_cap >= 200_000_000_000:
            return "Large Cap"
        elif market_cap >= 10_000_000_000:
            return "Mid Cap"
        elif market_cap >= 2_000_000_000:
            return "Small Cap"
        return "Micro Cap"

    def _analyze_risks(self, info: Dict) -> Dict[str, Any]:
        risks = []
        sector = info.get("sector") or ""
        industry = info.get("industry") or ""
        
        # Financial Risks
        debt_to_equity = self._safe_float(info.get("debtToEquity"))
        if debt_to_equity > 150:
            risks.append({"type": "Financial", "severity": "High", "description": f"Very high debt-to-equity ({debt_to_equity:.0f}%)"})
        elif debt_to_equity > 100:
            risks.append({"type": "Financial", "severity": "Medium", "description": f"High debt-to-equity ({debt_to_equity:.0f}%)"})
            
        current_ratio = self._safe_float(info.get("currentRatio"))
        if current_ratio < 0.8:
            risks.append({"type": "Financial", "severity": "High", "description": f"Low current ratio ({current_ratio:.2f}) - may have liquidity issues"})
        elif current_ratio < 1:
            risks.append({"type": "Financial", "severity": "Medium", "description": f"Weak current ratio ({current_ratio:.2f})"})
            
        # Market Risks
        beta = self._safe_float(info.get("beta"))
        if beta > 1.5:
            risks.append({"type": "Market", "severity": "High", "description": f"High volatility (Beta: {beta:.2f}) - more volatile than market"})
        elif beta > 1.2:
            risks.append({"type": "Market", "severity": "Medium", "description": f"Above-average volatility (Beta: {beta:.2f})"})
            
        # Profitability Risks
        profit_margin = self._safe_float(info.get("profitMargins"))
        if profit_margin < 0:
            risks.append({"type": "Operational", "severity": "High", "description": "Negative profit margins - company is not profitable"})
        elif profit_margin < 5:
            risks.append({"type": "Operational", "severity": "Medium", "description": f"Low profit margins ({profit_margin:.1f}%)"})
            
        operating_margin = self._safe_float(info.get("operatingMargins"))
        if operating_margin < 0:
            risks.append({"type": "Operational", "severity": "High", "description": "Negative operating margins"})
            
        # Cyclical Risks
        if sector in ["Technology", "Consumer Cyclical", "Consumer Discretionary", "Real Estate"]:
            risks.append({"type": "Cyclical", "severity": "Medium", "description": f"Exposure to {sector} economic cycles"})
            
        # Industry-specific risks
        if "Semiconductor" in industry or "Semiconductors" in industry:
            risks.append({"type": "Industry", "severity": "Medium", "description": "Cyclical semiconductor industry - highly sensitive to tech spending cycles"})
        if "Retail" in industry:
            risks.append({"type": "Industry", "severity": "Medium", "description": "Competitive retail industry with thin margins"})
        if "Banking" in industry or "Financial Services" in industry:
            risks.append({"type": "Industry", "severity": "Medium", "description": "Regulatory and interest rate risks"})
            
        # Concentration Risks
        if info.get("shortName"):
            ticker = info.get("symbol", "")
            # Add specific risks based on known company characteristics
            
        # Earnings Risk
        earnings_growth = self._safe_float(info.get("earningsGrowth"))
        if earnings_growth < -20:
            risks.append({"type": "Growth", "severity": "High", "description": f"Declining earnings ({earnings_growth:.1f}% decline)"})
        elif earnings_growth < 0:
            risks.append({"type": "Growth", "severity": "Medium", "description": f"Negative earnings growth ({earnings_growth:.1f}%)"})
            
        return {
            "identified_risks": risks,
            "risk_summary": f"{len(risks)} risks identified",
            "risk_score": min(100, len(risks) * 15 + 30),
            "risk_level": "High" if len(risks) >= 4 else "Medium" if len(risks) >= 2 else "Low"
        }

    async def _analyze_technical(self, ticker: str) -> Dict[str, Any]:
        loop = asyncio.get_event_loop()
        try:
            stock = await loop.run_in_executor(self.executor, yf.Ticker, ticker)
            hist = await loop.run_in_executor(self.executor, lambda: stock.history(period="1y"))
            
            if hist.empty:
                return {"error": "Insufficient data"}

            close_prices = hist['Close']
            high_prices = hist['High']
            low_prices = hist['Low']
            volume = hist['Volume']
            
            current_price = float(close_prices.iloc[-1])
            current_volume = int(volume.iloc[-1])
            
            # Moving Averages
            ma_20 = float(close_prices.tail(20).mean())
            ma_50 = float(close_prices.tail(50).mean())
            ma_100 = float(close_prices.tail(100).mean()) if len(close_prices) >= 100 else None
            ma_200 = float(close_prices.tail(200).mean()) if len(close_prices) >= 200 else None
            
            # RSI (14-day)
            delta = close_prices.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = float(100 - (100 / (1 + rs)).iloc[-1]) if not loss.iloc[-1] == 0 else 50
            
            # MACD
            ema_12 = close_prices.ewm(span=12, adjust=False).mean()
            ema_26 = close_prices.ewm(span=26, adjust=False).mean()
            macd_line = ema_12 - ema_26
            signal_line = macd_line.ewm(span=9, adjust=False).mean()
            macd_histogram = macd_line - signal_line
            macd_value = float(macd_line.iloc[-1])
            macd_signal = float(signal_line.iloc[-1])
            macd_hist = float(macd_histogram.iloc[-1])
            
            # Support and Resistance
            recent_high = float(high_prices.tail(50).max())
            recent_low = float(low_prices.tail(50).min())
            support_1 = recent_low
            resistance_1 = recent_high
            
            # Price position in range
            price_position = ((current_price - recent_low) / (recent_high - recent_low) * 100) if recent_high > recent_low else 50
            
            # Volatility (ATR-like)
            high_low = high_prices - low_prices
            atr = float(high_low.tail(14).mean())
            atr_percent = (atr / current_price * 100) if current_price > 0 else 0
            
            # Momentum
            roc_20 = ((current_price - float(close_prices.tail(20).iloc[0])) / float(close_prices.tail(20).iloc[0]) * 100)
            roc_50 = ((current_price - float(close_prices.tail(50).iloc[0])) / float(close_prices.tail(50).iloc[0]) * 100)
            
            # Volume analysis
            avg_volume_20 = float(volume.tail(20).mean())
            volume_ratio = current_volume / avg_volume_20 if avg_volume_20 > 0 else 1
            
            # Determine overall signal
            bullish_signals = 0
            bearish_signals = 0
            
            if current_price > ma_50: bullish_signals += 1
            else: bearish_signals += 1
            
            if current_price > ma_200 or not ma_200: bullish_signals += 1
            else: bearish_signals += 1
            
            if rsi < 70 and rsi > 30: 
                if rsi > 50: bullish_signals += 1
                else: bearish_signals += 1
            elif rsi >= 70: bearish_signals += 1
            else: bullish_signals += 1
            
            if macd_hist > 0: bullish_signals += 1
            else: bearish_signals += 1
            
            if roc_20 > 0: bullish_signals += 1
            else: bearish_signals += 1
            
            if bullish_signals > bearish_signals + 1:
                signal = "Strong Bullish"
            elif bullish_signals > bearish_signals:
                signal = "Bullish"
            elif bearish_signals > bullish_signals + 1:
                signal = "Strong Bearish"
            else:
                signal = "Bearish"
            
            # Trend determination
            if current_price > ma_50 > ma_200:
                trend = "Strong Uptrend"
            elif current_price > ma_50:
                trend = "Uptrend"
            elif current_price < ma_50 < ma_200:
                trend = "Strong Downtrend"
            elif current_price < ma_50:
                trend = "Downtrend"
            else:
                trend = "Sideways"
            
            return {
                "current_price": round(current_price, 2),
                "ma_20": round(ma_20, 2),
                "ma_50": round(ma_50, 2),
                "ma_100": round(ma_100, 2) if ma_100 else None,
                "ma_200": round(ma_200, 2) if ma_200 else None,
                "rsi": round(rsi, 2),
                "macd": round(macd_value, 2),
                "macd_signal": round(macd_signal, 2),
                "macd_histogram": round(macd_hist, 2),
                "support": round(support_1, 2),
                "resistance": round(resistance_1, 2),
                "price_position": round(price_position, 1),
                "atr": round(atr, 2),
                "atr_percent": round(atr_percent, 2),
                "volatility": "High" if atr_percent > 3 else "Medium" if atr_percent > 1.5 else "Low",
                "momentum": "Strong" if abs(roc_20) > 5 else "Moderate" if abs(roc_20) > 2 else "Weak",
                "roc_20": round(roc_20, 2),
                "roc_50": round(roc_50, 2),
                "volume": current_volume,
                "avg_volume_20": round(avg_volume_20, 0),
                "volume_ratio": round(volume_ratio, 2),
                "trend": trend,
                "signal": signal,
                "1m_change": round(((current_price - float(close_prices.tail(21).iloc[0])) / float(close_prices.tail(21).iloc[0]) * 100), 2),
                "3m_change": round(((current_price - float(close_prices.tail(63).iloc[0])) / float(close_prices.tail(63).iloc[0]) * 100), 2),
                "6m_change": round(((current_price - float(close_prices.iloc[0])) / float(close_prices.iloc[0]) * 100), 2),
                "ytd_change": round(((current_price - float(close_prices.iloc[0])) / float(close_prices.iloc[0]) * 100), 2),
                "52_week_high": round(recent_high, 2),
                "52_week_low": round(recent_low, 2),
            }
        except Exception as e:
            return {"error": str(e)}

    async def search_stocks(self, query: str) -> Dict[str, Any]:
        import urllib.parse
        
        cache_key = f"search_{query.lower()}"
        cached = self._get_cached(cache_key, 600)
        if cached:
            return cached
        
        query_clean = query.strip()
        results = []
        seen_symbols = set()
        
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        
        # 1. Yahoo Finance official search API
        try:
            encoded_query = urllib.parse.quote(query_clean)
            url = f"https://query1.finance.yahoo.com/v1/finance/search?q={encoded_query}&quotesCount=15&newsCount=0"
            response = requests.get(url, headers=headers, timeout=8)
            if response.status_code == 200:
                data = response.json()
                quotes = data.get("quotes", [])
                for quote in quotes:
                    symbol = quote.get("symbol", "")
                    if symbol and symbol not in seen_symbols:
                        quote_type = quote.get("quoteType", "")
                        exchange = quote.get("exchange", "")
                        if quote_type in ["EQUITY", "ETF"] and exchange in ["NASDAQ", "NYSE", "AMEX"]:
                            seen_symbols.add(symbol)
                            results.append({
                                "symbol": symbol,
                                "name": quote.get("shortname") or quote.get("longname") or symbol,
                                "sector": quote.get("sector") or "N/A",
                                "exchange": exchange,
                                "quote_type": quote_type
                            })
        except Exception:
            pass
        
        # 2. Direct ticker lookup if no search results
        if len(results) == 0:
            try:
                loop = asyncio.get_event_loop()
                stock = await loop.run_in_executor(self.executor, yf.Ticker, query_clean.upper())
                info = await loop.run_in_executor(self.executor, lambda: stock.info)
                if info and info.get("shortName"):
                    results.append({
                        "symbol": query_clean.upper(),
                        "name": info.get("shortName") or info.get("longName") or query_clean.upper(),
                        "sector": info.get("sector") or "N/A",
                        "exchange": info.get("exchange") or "N/A",
                        "quote_type": "EQUITY"
                    })
            except:
                pass
        
        # 3. Fallback: popular tickers
        if len(results) == 0:
            popular = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD", "INTC", "NFLX",
                      "JPM", "BAC", "WFC", "V", "MA", "JNJ", "UNH", "PFE", "XOM", "CVX"]
            query_lower = query_clean.lower()
            
            loop = asyncio.get_event_loop()
            for symbol in popular[:10]:
                if symbol in seen_symbols:
                    continue
                try:
                    stock = await loop.run_in_executor(self.executor, yf.Ticker, symbol)
                    info = await loop.run_in_executor(self.executor, lambda: stock.info)
                    if info:
                        name = info.get("shortName") or ""
                        if name and (query_lower in name.lower() or query_lower in symbol.lower()):
                            results.append({
                                "symbol": symbol,
                                "name": name,
                                "sector": info.get("sector") or "N/A",
                                "exchange": info.get("exchange") or "N/A",
                                "quote_type": "EQUITY"
                            })
                            if len(results) >= 5:
                                break
                except:
                    continue
        
        response = {"results": results[:15], "query": query_clean}
        self._set_cached(cache_key, response)
        return response

    async def get_market_overview(self) -> Dict[str, Any]:
        cache_key = "market_overview"
        cached = self._get_cached(cache_key, 300)
        if cached:
            return cached
        
        indices = {"^GSPC": "S&P 500", "^DJI": "Dow Jones", "^IXIC": "NASDAQ"}
        overview = {}
        
        loop = asyncio.get_event_loop()
        for symbol, name in indices.items():
            try:
                ticker = await loop.run_in_executor(self.executor, yf.Ticker, symbol)
                hist = await loop.run_in_executor(self.executor, lambda: ticker.history(period="5d"))
                if not hist.empty:
                    current = hist['Close'].iloc[-1]
                    prev = hist['Close'].iloc[0]
                    change = ((current - prev) / prev) * 100
                    overview[name] = {"symbol": symbol, "value": round(float(current), 2), "change_percent": round(float(change), 2)}
            except:
                continue
        
        self._set_cached(cache_key, overview)
        return overview

    async def get_options_data(self, ticker: str) -> Dict[str, Any]:
        """Get options chain with implied volatility - key for earnings plays"""
        try:
            loop = asyncio.get_event_loop()
            stock = await loop.run_in_executor(self.executor, yf.Ticker, ticker.upper())
            
            # Get options dates
            try:
                opt_dates = await loop.run_in_executor(self.executor, lambda: stock.options)
            except:
                opt_dates = []
            
            iv = None
            put_volume = 0
            call_volume = 0
            put_call_ratio = 0
            
            try:
                info = await loop.run_in_executor(self.executor, lambda: stock.info)
                iv = info.get("impliedVolatility")
                if iv and iv > 0:
                    iv = round(iv * 100, 1)
            except:
                pass
            
            # Get near-term options if available
            options_chain = {}
            if opt_dates and len(opt_dates) > 0:
                nearest = opt_dates[0] if len(opt_dates) > 1 else opt_dates[0]
                try:
                    opt = await loop.run_in_executor(self.executor, lambda: stock.option_chain(nearest))
                    put_volume = int(opt.puts['volume'].sum()) if hasattr(opt, 'puts') and not opt.puts.empty else 0
                    call_volume = int(opt.calls['volume'].sum()) if hasattr(opt, 'calls') and not opt.calls.empty else 0
                    put_call_ratio = float(put_volume / call_volume) if call_volume > 0 else 0
                    
                    # Get OTM options for price targets (skip for now to avoid complexity)
                    options_chain = {}
                    try:
                        if hasattr(opt, 'calls') and not opt.calls.empty:
                            calls = opt.calls
                            itm_calls = calls[calls['inTheMoney'] == False].head(3)
                            call_data = itm_calls[['strike', 'lastPrice', 'volume']].to_dict('records')
                            options_chain['next_call'] = [self._clean_dict(row) for row in call_data]
                        if hasattr(opt, 'puts') and not opt.puts.empty:
                            puts = opt.puts
                            itm_puts = puts[puts['inTheMoney'] == False].head(3)
                            put_data = itm_puts[['strike', 'lastPrice', 'volume']].to_dict('records')
                            options_chain['next_put'] = [self._clean_dict(row) for row in put_data]
                    except:
                        options_chain = {}
                except:
                    pass
            
            return {
                "iv": iv,
                "iv_rank": self._calculate_iv_rank(iv),
                "put_volume": put_volume,
                "call_volume": call_volume,
                "put_call_ratio": round(put_call_ratio, 2),
                "next_expiry": opt_dates[0] if opt_dates else None,
                "expirations": list(opt_dates[:6]) if opt_dates else [],
                "options_chain": options_chain
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _calculate_iv_rank(self, iv: float) -> Optional[float]:
        """Calculate IV rank (where current IV is relative to 52w range)"""
        if not iv:
            return None
        return min(100, max(0, iv / 2))
    
    async def get_institutional_ownership(self, ticker: str) -> Dict[str, Any]:
        """Get institutional ownership and recent activity"""
        try:
            loop = asyncio.get_executor()
            stock = await loop.run_in_executor(self.executor, yf.Ticker, ticker.upper())
            info = await loop.run_in_executor(self.executor, lambda: stock.info)
            
            holders = {
                "institutional_ownership": info.get("institutionalOwnership", 0) * 100 if info.get("institutionalOwnership") else 0,
                "total_held": info.get("totalHeld", 0),
                "held_percent_insiders": info.get("heldPercentInsiders", 0) * 100 if info.get("heldPercentInsiders") else 0,
            }
            
            try:
                inst_holders = await loop.run_in_executor(self.executor, lambda: stock.institutional_holders)
                if inst_holders is not None and not inst_holders.empty:
                    top_holders = inst_holders.head(10)
                    holders["top_holders"] = [
                        {"name": row['Holder'], "shares": row['Shares'], "pct": row['pctHeld'] * 100}
                        for _, row in top_holders.iterrows()
                    ]
            except:
                pass
            
            return holders
        except:
            return {}
    
    async def get_insider_activity(self, ticker: str) -> Dict[str, Any]:
        """Get recent insider buying and selling"""
        try:
            loop = asyncio.get_event_loop()
            stock = await loop.run_in_executor(self.executor, yf.Ticker, ticker.upper())
            
            try:
                insiders = await loop.run_in_executor(self.executor, lambda: stock.insider_holders)
                transactions = await loop.run_in_executor(self.executor, lambda: stock.insider_transactions)
                
                result = {"recent_transactions": []}
                
                if transactions is not None and not transactions.empty:
                    recent = transactions.head(20)
                    buys = recent[recent['Transaction'] == 'Purchase']
                    sells = recent[recent['Transaction'] == 'Sale']
                    
                    result["buy_count"] = int(len(buys))
                    result["sell_count"] = int(len(sells))
                    result["buy_value"] = float(buys['Value'].sum()) if 'Value' in buys.columns and not buys.empty else 0
                    result["sell_value"] = float(sells['Value'].sum()) if 'Value' in sells.columns and not sells.empty else 0
                    
                    result["recent_transactions"] = [
                        {
                            "owner": row['Owner'],
                            "transaction": row['Transaction'],
                            "shares": row['Shares'],
                            "value": row.get('Value', 0),
                            "date": str(row['Start'])
                        }
                        for _, row in recent.head(10).iterrows()
                    ]
                
                return result
            except:
                return {"recent_transactions": []}
        except:
            return {"recent_transactions": []}
    
    async def get_analyst_targets(self, ticker: str) -> Dict[str, Any]:
        """Get analyst price targets and ratings"""
        try:
            loop = asyncio.get_event_loop()
            stock = await loop.run_in_executor(self.executor, yf.Ticker, ticker.upper())
            info = await loop.run_in_executor(self.executor, lambda: stock.info)
            
            targets = {
                "target_mean": info.get("targetMeanPrice"),
                "target_high": info.get("targetHighPrice"),
                "target_low": info.get("targetLowPrice"),
                "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
                "recommendation": info.get("recommendationKey"),
                "rating_count": info.get("numberOfAnalystOpinions"),
            }
            
            if targets["target_mean"] and targets["current_price"]:
                upside = ((targets["target_mean"] - targets["current_price"]) / targets["current_price"]) * 100
                targets["upside_percent"] = round(upside, 1)
            
            return targets
        except:
            return {}
    
    async def get_relative_strength(self, ticker: str) -> Dict[str, Any]:
        """Compare stock performance vs sector and SPY"""
        try:
            loop = asyncio.get_event_loop()
            stock = await loop.run_in_executor(self.executor, yf.Ticker, ticker.upper())
            info = await loop.run_in_executor(self.executor, lambda: stock.info)
            
            sector = info.get("sector") or "Unknown"
            industry = info.get("industry", "")
            
            periods = ["1m", "3m", "6m", "1y"]
            results = {"sector": sector, "industry": industry, "vs_sector": {}, "vs_spy": {}}
            
            for period in periods:
                try:
                    hist = await loop.run_in_executor(self.executor, lambda: stock.history(period=period))
                    if not hist.empty:
                        stock_return = ((hist['Close'].iloc[-1] - hist['Close'].iloc[0]) / hist['Close'].iloc[0]) * 100
                        results["vs_sector"][period] = round(stock_return, 1)
                except:
                    pass
            
            try:
                spy = await loop.run_in_executor(self.executor, lambda: yf.Ticker("SPY").history(period="3mo"))
                if not spy.empty:
                    spy_return = ((spy['Close'].iloc[-1] - spy['Close'].iloc[0]) / spy['Close'].iloc[0]) * 100
                    results["spys_return"] = round(spy_return, 1)
            except:
                pass
            
            return results
        except:
            return {}
    
    def calculate_dcf(self, ticker: str) -> Dict[str, Any]:
        """Simplified DCF fair value calculation"""
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            if not info:
                return {}
            
            fcf = info.get("freeCashflow")
            if not fcf or fcf <= 0:
                return {}
            
            shares = info.get("sharesOutstanding", 1)
            growth = info.get("revenueGrowth", 0.05)
            
            if not growth:
                growth = 0.05
            
            cash = info.get("totalCash", 0) or 0
            debt = info.get("totalDebt", 0) or 0
            net_cash = cash - debt
            
            projections = []
            fcf_current = fcf
            discount_rate = 0.10
            
            for i in range(1, 6):
                fcf_current *= (1 + growth)
                discounted = fcf_current / ((1 + discount_rate) ** i)
                projections.append(discounted)
            
            terminal_value = (fcf_current * 1.03) / (discount_rate - 0.03)
            terminal_discounted = terminal_value / ((1 + discount_rate) ** 5)
            
            enterprise_value = sum(projections) + terminal_discounted
            equity_value = enterprise_value + net_cash
            fair_value = equity_value / shares
            
            current_price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
            margin_safety = ((fair_value - current_price) / fair_value) * 100 if fair_value > 0 else 0
            
            return {
                "fair_value": round(fair_value, 2),
                "current_price": current_price,
                "margin_of_safety": round(margin_safety, 1),
                "recommendation": "BUY" if margin_safety > 20 else "HOLD" if margin_safety > 0 else "SELL"
            }
        except:
            return {}
    
    async def get_gap_analysis(self, ticker: str) -> Dict[str, Any]:
        """Analyze price gaps - key technical signal"""
        try:
            loop = asyncio.get_event_loop()
            stock = await loop.run_in_executor(self.executor, yf.Ticker, ticker.upper())
            hist = await loop.run_in_executor(self.executor, lambda: stock.history(period="60d"))
            
            if hist.empty or len(hist) < 30:
                return {}
            
            gaps = []
            for i in range(1, len(hist)):
                prev_high = hist['High'].iloc[i-1]
                curr_low = hist['Low'].iloc[i]
                
                gap_up = hist['Low'].iloc[i] > hist['High'].iloc[i-1]
                gap_down = hist['High'].iloc[i] < hist['Low'].iloc[i-1]
                
                if gap_up or gap_down:
                    gap_pct = abs((curr_low - prev_high) / prev_high * 100)
                    if gap_pct > 2:
                        gaps.append({
                            "date": str(hist.index[i].date()),
                            "type": "gap_up" if gap_up else "gap_down",
                            "percent": round(gap_pct, 2),
                            "filled": False
                        })
            
            last_close = hist['Close'].iloc[-1]
            first_open = hist['Open'].iloc[0]
            recent_gap = (last_close - first_open) / first_open * 100
            
            return {
                "gaps": gaps[-10:],
                "trend_60d": round(recent_gap, 1),
                "gap_fill_count": sum(1 for g in gaps if not g.get('filled', True))
            }
        except:
            return {}