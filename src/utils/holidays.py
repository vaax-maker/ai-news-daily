"""Korean Holiday Utilities for Calendar Display"""

import datetime

def is_korean_holiday(date_obj: datetime.date) -> bool:
    """
    Check if the given date is a Korean public holiday.
    Uses the get_calendar_data function internally.
    """
    holidays = get_calendar_data(date_obj.year)
    date_str = date_obj.strftime("%Y-%m-%d")
    return date_str in holidays


def get_calendar_data(year: int) -> dict:
    """
    Returns a dictionary of Korean public holidays for the given year,
    and also previous/next year to cover January/December edge cases in calendar views.
    
    Format: { "YYYY-MM-DD": "Holiday Name" }
    
    Note: This uses hardcoded data for comprehensive coverage, 
    as third-party libraries often lack future lunar calendar dates.
    """
    holidays_map = {}
    
    # Define holidays for each year
    KOREAN_HOLIDAYS = {
        2024: {
            "2024-01-01": "신정",
            "2024-02-09": "설날 전날",
            "2024-02-10": "설날",
            "2024-02-11": "설날 다음날",
            "2024-02-12": "대체휴일",
            "2024-03-01": "삼일절",
            "2024-05-05": "어린이날",
            "2024-05-15": "부처님오신날",
            "2024-06-06": "현충일",
            "2024-08-15": "광복절",
            "2024-09-16": "추석 전날",
            "2024-09-17": "추석",
            "2024-09-18": "추석 다음날",
            "2024-10-03": "개천절",
            "2024-10-09": "한글날",
            "2024-12-25": "크리스마스"
        },
        2025: {
            "2025-01-01": "신정",
            "2025-01-28": "설날 전날",
            "2025-01-29": "설날",
            "2025-01-30": "설날 다음날",
            "2025-03-01": "삼일절",
            "2025-05-05": "어린이날/부처님오신날",
            "2025-06-06": "현충일",
            "2025-08-15": "광복절",
            "2025-10-03": "개천절",
            "2025-10-05": "추석 전날",
            "2025-10-06": "추석",
            "2025-10-07": "추석 다음날",
            "2025-10-08": "대체휴일",
            "2025-10-09": "한글날",
            "2025-12-25": "크리스마스"
        },
        2026: {
            "2026-01-01": "신정",
            "2026-02-16": "설날 전날",
            "2026-02-17": "설날",
            "2026-02-18": "설날 다음날",
            "2026-03-01": "삼일절",
            "2026-05-05": "어린이날",
            "2026-05-24": "부처님오신날",
            "2026-06-06": "현충일",
            "2026-08-15": "광복절",
            "2026-09-24": "추석 전날",
            "2026-09-25": "추석",
            "2026-09-26": "추석 다음날",
            "2026-10-03": "개천절",
            "2026-10-09": "한글날",
            "2026-12-25": "크리스마스"
        },
        2027: {
            "2027-01-01": "신정",
            "2027-02-05": "설날 전날",
            "2027-02-06": "설날",
            "2027-02-07": "설날 다음날",
            "2027-03-01": "삼일절",
            "2027-05-05": "어린이날",
            "2027-05-13": "부처님오신날",
            "2027-06-06": "현충일",
            "2027-08-15": "광복절",
            "2027-09-14": "추석 전날",
            "2027-09-15": "추석",
            "2027-09-16": "추석 다음날",
            "2027-10-03": "개천절",
            "2027-10-09": "한글날",
            "2027-12-25": "크리스마스"
        }
    }
    
    # Add holidays for year-1, year, year+1
    for y in [year - 1, year, year + 1]:
        if y in KOREAN_HOLIDAYS:
            holidays_map.update(KOREAN_HOLIDAYS[y])
    
    return holidays_map
