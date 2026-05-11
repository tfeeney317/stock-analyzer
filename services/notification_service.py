import os
import json
import requests
from datetime import datetime
from typing import Dict, List, Optional

class NotificationService:
    def __init__(self):
        self.config_file = "/Users/feeneyfam/stock-analyzer/data/notifications.json"
        self.config = self._load_config()
        
    def _load_config(self) -> Dict:
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    return json.load(f)
        except:
            pass
        return {
            "discord_webhook": "",
            "telegram_bot_token": "",
            "telegram_chat_id": "",
            "pushover_token": "",
            "pushover_user": "",
            "email_enabled": False,
            "email_smtp": "",
            "email_port": 587,
            "email_user": "",
            "email_password": "",
            "email_to": "",
            "enabled": True
        }
    
    def _save_config(self):
        os.makedirs("/Users/feeneyfam/stock-analyzer/data", exist_ok=True)
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=2)
    
    def update_config(self, config: Dict) -> Dict:
        self.config.update(config)
        self._save_config()
        return {"success": True, "config": self.config}
    
    def get_config(self) -> Dict:
        return {k: v for k, v in self.config.items() if v}
    
    def send_alert(self, alert: Dict) -> Dict:
        """Send alert notification via all configured methods"""
        if not self.config.get("enabled", True):
            return {"success": False, "message": "Notifications disabled"}
        
        results = []
        
        message = self._format_message(alert)
        
        # Discord
        if self.config.get("discord_webhook"):
            result = self._send_discord(message)
            results.append(result)
        
        # Telegram
        if self.config.get("telegram_bot_token") and self.config.get("telegram_chat_id"):
            result = self._send_telegram(message)
            results.append(result)
        
        # Pushover
        if self.config.get("pushover_token") and self.config.get("pushover_user"):
            result = self._send_pushover(alert)
            results.append(result)
        
        # Email
        if self.config.get("email_enabled") and self.config.get("email_to"):
            result = self._send_email(alert)
            results.append(result)
        
        return {"success": True, "results": results}
    
    def _format_message(self, alert: Dict) -> str:
        ticker = alert.get("ticker", "")
        alert_type = alert.get("type", "")
        message = alert.get("message", "")
        details = alert.get("details", "")
        
        return f"🚨 **{ticker} Alert**\n\n*Type:* {alert_type}\n{message}\n{details}"
    
    def _send_discord(self, message: str) -> Dict:
        try:
            webhook_url = self.config["discord_webhook"]
            payload = {
                "content": message,
                "username": "Stock Alert Bot"
            }
            response = requests.post(webhook_url, json=payload, timeout=10)
            return {"method": "discord", "success": response.status_code == 204}
        except Exception as e:
            return {"method": "discord", "success": False, "error": str(e)}
    
    def _send_telegram(self, message: str) -> Dict:
        try:
            token = self.config["telegram_bot_token"]
            chat_id = self.config["telegram_chat_id"]
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
            response = requests.post(url, json=payload, timeout=10)
            return {"method": "telegram", "success": response.status_code == 200}
        except Exception as e:
            return {"method": "telegram", "success": False, "error": str(e)}
    
    def _send_pushover(self, alert: Dict) -> Dict:
        try:
            token = self.config["pushover_token"]
            user = self.config["pushover_user"]
            url = "https://api.pushover.net/1/messages.json"
            payload = {
                "token": token,
                "user": user,
                "title": f"{alert.get('ticker')} Alert",
                "message": f"{alert.get('message')}\n{alert.get('details', '')}",
                "priority": 1
            }
            response = requests.post(url, json=payload, timeout=10)
            return {"method": "pushover", "success": response.status_code == 200}
        except Exception as e:
            return {"method": "pushover", "success": False, "error": str(e)}
    
    def _send_email(self, alert: Dict) -> Dict:
        try:
            import smtplib
            from email.mime.text import MIMEText
            
            smtp = self.config.get("email_smtp", "smtp.gmail.com")
            port = self.config.get("email_port", 587)
            user = self.config.get("email_user")
            password = self.config.get("email_password")
            to = self.config.get("email_to")
            
            subject = f"Stock Alert: {alert.get('ticker')} - {alert.get('type')}"
            body = f"{alert.get('message')}\n\n{alert.get('details', '')}"
            
            msg = MIMEText(body)
            msg["Subject"] = subject
            msg["From"] = user
            msg["To"] = to
            
            server = smtplib.SMTP(smtp, port)
            server.starttls()
            server.login(user, password)
            server.send_message(msg)
            server.quit()
            
            return {"method": "email", "success": True}
        except Exception as e:
            return {"method": "email", "success": False, "error": str(e)}
    
    def test_notification(self, method: str) -> Dict:
        test_alert = {
            "ticker": "TEST",
            "type": "Test",
            "message": "Test notification successful!",
            "details": "Your notification settings are working correctly."
        }
        
        if method == "discord":
            return self._send_discord("Test: Stock Alert system is working!")
        elif method == "telegram":
            return self._send_telegram("Test: Stock Alert system is working!")
        elif method == "pushover":
            return self._send_pushover(test_alert)
        elif method == "email":
            return self._send_email(test_alert)
        
        return {"success": False, "message": "Unknown method"}

notification_service = NotificationService()