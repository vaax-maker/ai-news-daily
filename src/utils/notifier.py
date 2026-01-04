import os
import datetime
import requests
import logging

logger = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self, token=None, chat_id=None):
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self.base_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    def send_message(self, text: str):
        if not self.token or not self.chat_id:
            logger.warning("[Notifier] Telegram token or chat_id not configured. Skipping.")
            return False

        try:
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "disable_web_page_preview": True
            }
            resp = requests.post(self.base_url, json=payload, timeout=10)
            resp.raise_for_status()
            logger.info("[Notifier] Message sent successfully.")
            return True
        except Exception as e:
            logger.error(f"[Notifier] Failed to send message: {e}")
            return False

def format_daily_briefing(ai_items, xr_items, gov_items, briefing_url, max_chars=450):
    """
    Format:
    [Header]
    
    [AI]
    - Title..
    - Title..
    
    [XR]
    ...
    
    [Full Report Link]
    """
    from src.utils.common import get_kst_now
    now = get_kst_now()
    weekday_map = {0:'월', 1:'화', 2:'수', 3:'목', 4:'금', 5:'토', 6:'일'}
    wd = weekday_map[now.weekday()]
    
    # Short header
    header = f"{now.strftime('%m/%d')}({wd}) {now.strftime('%H:%M')} VAAX\n"
    
    footer = f"\n\n{briefing_url}"
    
    # Calculate available space
    reserved = len(header) + len(footer) + 15
    available_chars = max_chars - reserved
    if available_chars < 50: available_chars = 50
    
    content_lines = []
    current_length = 0
    
    # Helper to clean title
    def clean_title(text):
        import re
        text = re.sub(r'\b[a-zA-Z0-9-]+\.[a-zA-Z0-9-]{2,}\b', '', text)
        text = re.sub(r'\s+-\s*$', '', text).strip()
        return text

    def add_items(items, header_title):
        nonlocal current_length
        added_count = 0
        
        valid_items = []
        for item in items:
            raw = item.get('title', '').strip()
            if raw and clean_title(raw):
                valid_items.append(clean_title(raw))
                
        if not valid_items:
            return False
            
        # Short Header
        header_line = f"\n[{header_title}]\n"
        content_lines.append(header_line)
        current_length += len(header_line)

        for title in valid_items:
            line = f"-{title}\n\n"
            
            if current_length + len(line) > available_chars and added_count > 0:
                break
            
            content_lines.append(line)
            current_length += len(line)
            added_count += 1
            
        return added_count > 0

    # Build sequence
    add_items(ai_items, "AI")
    add_items(xr_items, "XR")
    add_items(gov_items, "Gov")
        
    body = "".join(content_lines)
    return f"{header}{body}{footer}"

def send_daily_briefing(dashboard_data):
    """
    Orchestrates the notification.
    dashboard_data: dict containing 'ai', 'xr', 'gov' lists and 'briefing_url'.
    """
    notifier = TelegramNotifier()
    
    ai_items = dashboard_data.get("ai", [])
    xr_items = dashboard_data.get("xr", [])
    gov_items = dashboard_data.get("gov", [])
    briefing_url = dashboard_data.get("briefing_url", "https://vaax-maker.github.io/ai-news-daily/index.html")
    
    # Filter for ONLY new items to avoid repetition
    # main.py/storage.py now tag items with 'is_new' boolean.
    # If key is missing (e.g. legacy data), treat as False to be safe (or True? Safe is False to avoid spam)
    # User requested: "Compare with previous... exclude repetitive".
    
    def filter_new(items):
        return [item for item in items if item.get("is_new", False)]

    new_ai = filter_new(ai_items)
    new_xr = filter_new(xr_items)
    new_gov = filter_new(gov_items)
    
    # If all empty, maybe we shouldn't send? 
    # But main.py checks total_new_items > 0. 
    # So at least one list should have something.
    
    # Strict limit: 420 chars
    message = format_daily_briefing(new_ai, new_xr, new_gov, briefing_url=briefing_url, max_chars=420)
    
    print("--- PREVIEW MESSAGE ---")
    print(message)
    print("-----------------------")
    
    if os.getenv("ENABLE_NOTIFICATION", "false").lower() == "true":
        notifier.send_message(message)
    else:
        logger.info("[Notifier] Notification disabled (ENABLE_NOTIFICATION != true)")
