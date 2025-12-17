"""Government Announcements Fetcher with improved security."""

import os
import logging
import requests
import xml.etree.ElementTree as ET
from typing import List, Dict
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

# Default API key (fallback) - should be overridden by environment variable
DEFAULT_GOV_API_KEY = "b333fbc99c073b3c163fabc773d9be9b4ae29d18e69a2522f825630386066c82"
REQUEST_TIMEOUT = 30


def fetch_gov_announcements(limit: int = 30) -> List[Dict[str, str]]:
    """
    과학기술정보통신부 사업공고 API 호출
    
    Args:
        limit: Maximum number of announcements to fetch
        
    Returns:
        List of announcement dictionaries
    """
    url = "http://apis.data.go.kr/1721000/msitannouncementinfo/businessAnnouncMentList"
    
    # Use environment variable for API key, fallback to default
    service_key = os.getenv("GOV_API_KEY", DEFAULT_GOV_API_KEY)
    
    params = {
        "serviceKey": service_key,
        "numOfRows": limit,
        "pageNo": 1,
        "type": "xml"
    }
    
    query = urlencode(params, safe="=")
    full_url = f"{url}?{query}"
    
    logger.info(f"[Gov] API 요청: {url}")
    
    items_list: List[Dict[str, str]] = []
    
    try:
        # Use requests instead of urllib for better SSL handling
        response = requests.get(full_url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        
        xml_data = response.content
        root = ET.fromstring(xml_data)
        
        xml_items = root.findall(".//item")
        logger.info(f"[Gov] Fetched {len(xml_items)} announcements")
        
        for item in xml_items:
            subject = item.findtext("subject", "")
            view_url = item.findtext("viewUrl", "")
            dept_name = item.findtext("deptName", "")
            manager_name = item.findtext("managerName", "")
            press_dt = item.findtext("pressDt", "")
            
            items_list.append({
                "title": subject,
                "link": view_url,
                "dept": dept_name,
                "manager": manager_name,
                "date": press_dt,
                "summary": "",
                "source_name": "과학기술정보통신부",
                "image_url": "",
                "published_display": press_dt
            })

    except requests.RequestException as e:
        logger.error(f"[Gov] API request failed: {e}")
    except ET.ParseError as e:
        logger.error(f"[Gov] XML parse error: {e}")
    except Exception as e:
        logger.error(f"[Gov] Unexpected error: {e}")
        
    return items_list
