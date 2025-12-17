import sqlite3
import datetime
import os
from typing import Optional

DB_PATH = "data/usage.db"

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS api_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            service TEXT,
            model TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            context TEXT,
            cost REAL
        )
    ''')
    conn.commit()
    conn.close()

def log_api_usage(
    service: str, 
    model: str, 
    input_tokens: int, 
    output_tokens: int, 
    cost: Optional[float] = None,
    context: str = ""
):
    """Logs API usage to the local SQLite database."""
    # Simple cost estimation fallback if not provided
    # Prices are approx. as of late 2024, can be updated
    if cost is None:
        cost = 0.0
        if "gemini" in service.lower() or "flash" in model.lower():
             # Gemini 1.5 Flash: ~$0.075/1M in, $0.3/1M out
             cost = (input_tokens / 1_000_000 * 0.075) + (output_tokens / 1_000_000 * 0.3)
        elif "grok" in service.lower() or "llama" in model.lower():
             # Llama 3 70B (Groq approx): ~$0.59/1M in, $0.79/1M out, heavily depends on provider
             cost = (input_tokens / 1_000_000 * 0.59) + (output_tokens / 1_000_000 * 0.79)
             
    timestamp = datetime.datetime.now().isoformat()
    
    try:
        if not os.path.exists(DB_PATH):
            init_db()
            
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''
            INSERT INTO api_usage (timestamp, service, model, input_tokens, output_tokens, context, cost)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (timestamp, service, model, input_tokens, output_tokens, context, cost))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[UsageLogger] Failed to log: {e}")

def get_recent_usage(limit=100):
    if not os.path.exists(DB_PATH):
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT * FROM api_usage ORDER BY timestamp DESC LIMIT ?', (limit,))
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows

def get_daily_stats(days=7):
    if not os.path.exists(DB_PATH):
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # SQLite compliant date substr
    c.execute('''
        SELECT 
            substr(timestamp, 1, 10) as date, 
            SUM(input_tokens) as input_sum,
            SUM(output_tokens) as output_sum,
            SUM(cost) as cost_sum,
            COUNT(*) as calls
        FROM api_usage 
        GROUP BY date 
        ORDER BY date DESC 
        LIMIT ?
    ''', (days,))
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows
