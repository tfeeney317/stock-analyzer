import yfinance as yf
from datetime import datetime
from typing import Dict, Any, List, Optional
import json
import os
import threading

class WatchlistService:
    def __init__(self):
        self.watchlist_file = "/Users/feeneyfam/stock-analyzer/data/watchlist.json"
        self.alerts_file = "/Users/feeneyfam/stock-analyzer/data/alerts.json"
        self._ensure_data_dir()
        self.watchlist = self._load_watchlist()
        self.alerts = self._load_alerts()
        self.previous_data = {}  # Store previous data for comparison
        self.alert_history_file = "/Users/feeneyfam/stock-analyzer/data/alert_history.json"
        self.alert_history = self._load_alert_history()
        
        # Start background monitoring
        self.monitor_thread = None
        self.running = False

    def _ensure_data_dir(self):
        os.makedirs("/Users/feeneyfam/stock-analyzer/data", exist_ok=True)

    def _load_watchlist(self) -> List[Dict]:
        try:
            if os.path.exists(self.watchlist_file):
                with open(self.watchlist_file, 'r') as f:
                    return json.load(f)
        except:
            pass
        return []

    def _save_watchlist(self):
        with open(self.watchlist_file, 'w') as f:
            json.dump(self.watchlist, f)

    def _load_alerts(self) -> List[Dict]:
        try:
            if os.path.exists(self.alerts_file):
                with open(self.alerts_file, 'r') as f:
                    return json.load(f)
        except:
            pass
        return []

    def _save_alerts(self):
        with open(self.alerts_file, 'w') as f:
            json.dump(self.alerts, f)

    def _load_alert_history(self) -> List[Dict]:
        try:
            if os.path.exists(self.alert_history_file):
                with open(self.alert_history_file, 'r') as f:
                    return json.load(f)
        except:
            pass
        return []

    def _save_alert_history(self):
        with open(self.alert_history_file, 'w') as f:
            json.dump(self.alert_history[-100:], f)  # Keep last 100 alerts

    def get_watchlist_prices(self) -> List[Dict]:
        result = []
        for stock in self.watchlist:
            ticker = stock.get("ticker", "").upper()
            if not ticker:
                continue
            try:
                yf_stock = yf.Ticker(ticker)
                info = yf_stock.info
                price = info.get("currentPrice", info.get("regularMarketPrice", 0))
                prev_close = info.get("regularMarketPreviousClose", price)
                change = price - prev_close
                change_percent = (change / prev_close * 100) if prev_close > 0 else 0
                
                result.append({
                    "ticker": ticker,
                    "name": info.get("shortName", ticker),
                    "price": price,
                    "previous_close": prev_close,
                    "change": change,
                    "change_percent": round(change_percent, 2),
                    "volume": info.get("volume", 0),
                    "day_high": info.get("regularMarketDayHigh", 0),
                    "day_low": info.get("regularMarketDayLow", 0),
                    "last_updated": datetime.now().isoformat()
                })
            except Exception as e:
                result.append({
                    "ticker": ticker,
                    "name": stock.get("name", ticker),
                    "error": str(e)
                })
        return result

    def add_to_watchlist(self, ticker: str, name: str = "") -> Dict:
        from .notification_service import notification_service
        
        ticker = ticker.upper()
        if any(s.get("ticker") == ticker for s in self.watchlist):
            return {"success": False, "message": "Already in watchlist"}
        
        if not name:
            try:
                yf_stock = yf.Ticker(ticker)
                name = yf_stock.info.get("shortName", ticker)
            except:
                name = ticker
        
        self.watchlist.append({"ticker": ticker, "name": name, "added_at": datetime.now().isoformat()})
        self._save_watchlist()
        
        # Auto-create all default alerts for this stock
        default_alerts = [
            "price_rise_5",
            "cross_ma50", 
            "unusual_volume",
            "new_high",
            "earnings",
            "upgrade"
        ]
        
        for alert_type in default_alerts:
            # Check if alert already exists for this ticker/type
            exists = any(a.get("ticker") == ticker and a.get("alert_type") == alert_type for a in self.alerts)
            if not exists:
                alert = {
                    "id": len(self.alerts) + 1,
                    "ticker": ticker,
                    "alert_type": alert_type,
                    "threshold": None,
                    "enabled": True,
                    "created_at": datetime.now().isoformat(),
                    "triggered": False,
                    "triggered_at": None
                }
                self.alerts.append(alert)
        
        self._save_alerts()
        
        return {"success": True, "watchlist": self.watchlist, "alerts_created": len(default_alerts)}

    def remove_from_watchlist(self, ticker: str) -> Dict:
        ticker = ticker.upper()
        self.watchlist = [s for s in self.watchlist if s.get("ticker") != ticker]
        self._save_watchlist()
        return {"success": True, "watchlist": self.watchlist}

    def get_watchlist(self) -> List[Dict]:
        return self.watchlist

    def create_alert(self, ticker: str, alert_type: str, threshold: float = None) -> Dict:
        """Create a new alert type"""
        alert = {
            "id": len(self.alerts) + 1,
            "ticker": ticker.upper(),
            "alert_type": alert_type,  # All the new alert types
            "threshold": threshold,
            "enabled": True,
            "created_at": datetime.now().isoformat(),
            "triggered": False,
            "triggered_at": None,
            "last_triggered": None
        }
        self.alerts.append(alert)
        self._save_alerts()
        return {"success": True, "alert": alert, "alerts": self.alerts}

    def delete_alert(self, alert_id: int) -> Dict:
        self.alerts = [a for a in self.alerts if a.get("id") != alert_id]
        self._save_alerts()
        return {"success": True, "alerts": self.alerts}

    def get_alerts(self) -> List[Dict]:
        return self.alerts

    def get_detailed_analysis(self, ticker: str) -> Dict:
        """Get detailed stock analysis for alert checking"""
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            # Get historical data for MA and volume
            hist = stock.history(period="60d")
            
            current_price = info.get("currentPrice", 0)
            volume = info.get("volume", 0)
            avg_volume_20 = hist['Volume'].tail(20).mean() if len(hist) >= 20 else volume
            
            # Calculate 50-day MA
            ma50 = hist['Close'].tail(50).mean() if len(hist) >= 50 else None
            prev_ma50 = hist['Close'].tail(51).head(50).mean() if len(hist) >= 51 else None
            
            # Get previous close
            prev_close = info.get("regularMarketPreviousClose", current_price)
            
            return {
                "ticker": ticker,
                "current_price": current_price,
                "previous_close": prev_close,
                "price_change_percent": ((current_price - prev_close) / prev_close * 100) if prev_close > 0 else 0,
                "volume": volume,
                "avg_volume_20": avg_volume_20,
                "volume_ratio": volume / avg_volume_20 if avg_volume_20 > 0 else 1,
                "ma50": ma50,
                "prev_ma50": prev_ma50,
                "above_ma50": current_price > ma50 if ma50 else None,
                "was_above_ma50": prev_close > prev_ma50 if (prev_ma50 and prev_close) else None,
                "52_week_high": info.get("fiftyTwoWeekHigh", 0),
                "analyst_rating": info.get("recommendationKey", ""),
                "earnings_date": info.get("earningsDate", {}),
                "is_ath": current_price >= info.get("fiftyTwoWeekHigh", 0) if info.get("fiftyTwoWeekHigh") else False
            }
        except Exception as e:
            return {"error": str(e)}

    def check_all_alerts(self) -> List[Dict]:
        """Check all enabled alerts for all watchlist stocks"""
        triggered = []
        
        for stock in self.watchlist:
            ticker = stock.get("ticker", "").upper()
            if not ticker:
                continue
            
            # Get detailed analysis
            analysis = self.get_detailed_analysis(ticker)
            if "error" in analysis:
                continue
            
            # Store previous data for comparison
            prev_data = self.previous_data.get(ticker, {})
            
            for alert in self.alerts:
                if not alert.get("enabled", True) or alert.get("triggered"):
                    continue
                
                if alert.get("ticker") != ticker:
                    continue
                
                alert_type = alert.get("alert_type", "")
                triggered_alert = None
                
                # Check each alert type
                if alert_type == "price_rise_5":
                    if analysis["price_change_percent"] > 5:
                        triggered_alert = {
                            "type": "Price Rise",
                            "message": f"{ticker} rose {analysis['price_change_percent']:.1f}% today",
                            "details": f"Current: ${analysis['current_price']:.2f}, Previous: ${analysis['previous_close']:.2f}"
                        }
                
                elif alert_type == "cross_ma50":
                    if analysis["above_ma50"] is not None and analysis["was_above_ma50"] is not None:
                        if analysis["above_ma50"] != analysis["was_above_ma50"]:
                            direction = "above" if analysis["above_ma50"] else "below"
                            triggered_alert = {
                                "type": "MA Cross",
                                "message": f"{ticker} crossed {direction} 50-day MA",
                                "details": f"Price: ${analysis['current_price']:.2f}, MA50: ${analysis['ma50']:.2f}"
                            }
                
                elif alert_type == "unusual_volume":
                    if analysis["volume_ratio"] > 1.5:  # 50% above average
                        triggered_alert = {
                            "type": "Unusual Volume",
                            "message": f"{ticker} has {analysis['volume_ratio']:.1f}x average volume",
                            "details": f"Volume: {analysis['volume']:,} vs avg {analysis['avg_volume_20']:,.0f}"
                        }
                
                elif alert_type == "new_high":
                    if analysis["is_ath"]:
                        # Check if we already triggered this recently
                        if not prev_data.get("new_high_triggered"):
                            triggered_alert = {
                                "type": "New High",
                                "message": f"{ticker} reached new 52-week high",
                                "details": f"Price: ${analysis['current_price']:.2f}"
                            }
                
                elif alert_type == "earnings":
                    earnings_date = analysis.get("earnings_date")
                    if earnings_date:
                        # Could add logic to alert before earnings
                        pass
                
                elif alert_type == "upgrade":
                    rating = analysis.get("analyst_rating", "")
                    prev_rating = prev_data.get("analyst_rating", "")
                    if rating in ["strongBuy", "buy"] and prev_rating not in ["strongBuy", "buy", ""]:
                        triggered_alert = {
                            "type": "Upgrade",
                            "message": f"{ticker} upgraded to {rating.replace('_', ' ').title()}",
                            "details": f"Analyst rating: {rating}"
                        }
                
                # Check price threshold alerts
                elif alert_type == "above":
                    if analysis["current_price"] > alert.get("threshold", 0):
                        triggered_alert = {
                            "type": "Price Above",
                            "message": f"{ticker} above ${alert['threshold']:.2f}",
                            "details": f"Current: ${analysis['current_price']:.2f}"
                        }
                
                elif alert_type == "below":
                    if analysis["current_price"] < alert.get("threshold", 0):
                        triggered_alert = {
                            "type": "Price Below",
                            "message": f"{ticker} below ${alert['threshold']:.2f}",
                            "details": f"Current: ${analysis['current_price']:.2f}"
                        }
                
                if triggered_alert:
                    alert["triggered"] = True
                    alert["triggered_at"] = datetime.now().isoformat()
                    alert["triggered_price"] = analysis["current_price"]
                    triggered_alert["alert_id"] = alert["id"]
                    triggered_alert["ticker"] = ticker
                    triggered_alert["timestamp"] = datetime.now().isoformat()
                    triggered.append(triggered_alert)
                    
                    # Add to history
                    self.alert_history.append(triggered_alert)
                    
                    # Send notification
                    try:
                        from .notification_service import notification_service
                        notification_service.send_alert(triggered_alert)
                    except:
                        pass
            
            # Update previous data
            self.previous_data[ticker] = {
                "current_price": analysis.get("current_price"),
                "analyst_rating": analysis.get("analyst_rating"),
                "new_high_triggered": analysis.get("is_ath", False)
            }
        
        if triggered:
            self._save_alerts()
            self._save_alert_history()
        
        return triggered

    def get_alert_history(self) -> List[Dict]:
        return self.alert_history[-50:]  # Last 50 alerts

    def clear_triggered_alerts(self):
        """Reset triggered alerts so they can trigger again"""
        for alert in self.alerts:
            alert["triggered"] = False
            alert["triggered_at"] = None
        self._save_alerts()
        return {"success": True, "alerts": self.alerts}

    def get_available_alert_types(self) -> List[Dict]:
        """Return available alert types with descriptions"""
        return [
            {"type": "price_rise_5", "name": "Price Rises > 5%", "description": "Alert when stock rises more than 5% in a day"},
            {"type": "cross_ma50", "name": "Crosses 50-Day MA", "description": "Alert when stock crosses above/below 50-day moving average"},
            {"type": "unusual_volume", "name": "Unusual Volume", "description": "Alert when volume is 50% above average"},
            {"type": "new_high", "name": "New 52-Week High", "description": "Alert when stock reaches new 52-week high"},
            {"type": "earnings", "name": "Earnings", "description": "Alert when earnings date approaches"},
            {"type": "upgrade", "name": "Analyst Upgrade", "description": "Alert when analyst upgrades to Buy/Strong Buy"},
            {"type": "above", "name": "Price Above", "description": "Alert when price goes above target"},
            {"type": "below", "name": "Price Below", "description": "Alert when price goes below target"},
        ]