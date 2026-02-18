from src.utils.common import shorten_korean_title
from src.utils.notifier import format_daily_briefing

def verify():
    # 1. Test shorten_korean_title
    long_title = "이것은 60자 제한을 테스트하기 위한 매우 길지만 완전한 한 문장의 제목입니다. 잘리지 않아야 합니다."
    shortened = shorten_korean_title(long_title)
    print(f"Original Length: {len(long_title)}")
    print(f"Shortened: {shortened}")
    print(f"Shortened Length: {len(shortened)}")
    
    if "…" in shortened and len(long_title) <= 60:
        print("FAIL: Title incorrectly truncated!")
    else:
        print("PASS: Truncation logic as expected.")
    
    # 2. Test Telegram format with long titles
    ai_items = [{"title": "완전한 문장 제목 1번입니다. 길지만 텔레그램에서는 잘리지 않고 표시되어야 합니다."} for _ in range(5)]
    xr_items = []
    gov_items = []
    
    message = format_daily_briefing(ai_items, xr_items, gov_items, briefing_url="http://test.com", max_chars=400)
    print("\n--- Telegram Preview (Max 400 chars) ---")
    print(message)
    print(f"Total length: {len(message)}")
    
    if "…" in message:
        print("FAIL: Found '…' in message body!")
    else:
        print("PASS: No truncation found in briefing.")

if __name__ == "__main__":
    verify()
