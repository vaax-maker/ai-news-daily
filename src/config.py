import os
import yaml
from dataclasses import dataclass, field
from typing import List, Dict, Optional

@dataclass
class CategoryConfig:
    key: str
    display_name: str
    rss_feeds: List[str]
    archive_dir: str
    index_path: str
    max_articles: int = 15
    fallback_image_url: str = ""
    selection_mode: str = "time"
    keyword_filters: List[str] = field(default_factory=list)
    use_ai_ranking: bool = False
    is_table_view: bool = False

@dataclass
class MemberConfig:
    id: str
    name: str
    keywords: List[str]
    representative: str = ""

def load_categories(path: str = "config/categories.yaml") -> Dict[str, CategoryConfig]:
    if not os.path.exists(path):
        return {}
    
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    
    configs = {}
    for key, val in data.get("categories", {}).items():
        # Environment variable overrides
        sel_mode = os.getenv(f"{key.upper()}_SELECTION_MODE", val.get("selection_mode", "time"))
        
        # Keyword filters from env (comma separated)
        env_kw = os.getenv(f"{key.upper()}_KEYWORDS", "")
        if env_kw:
            kw_list = [k.strip() for k in env_kw.split(",") if k.strip()]
        else:
            kw_list = val.get("keyword_filters", [])

        use_ai = os.getenv(f"{key.upper()}_USE_AI_RANKING", str(val.get("use_ai_ranking", False))).lower() == "true"

        configs[key] = CategoryConfig(
            key=key,
            display_name=val.get("display_name", key.upper()),
            rss_feeds=val.get("rss_feeds", []),
            archive_dir=val.get("archive_dir", f"docs/{key}/daily"),
            index_path=val.get("index_path", f"docs/{key}/index.html"),
            max_articles=val.get("max_articles", 15),
            fallback_image_url=val.get("fallback_image_url", ""),
            selection_mode=sel_mode,
            keyword_filters=kw_list,
            use_ai_ranking=use_ai,
            is_table_view=val.get("is_table_view", False)
        )
    return configs

def load_members(path: str = "config/members.yaml") -> Dict[str, MemberConfig]:
    if not os.path.exists(path):
        return {}

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
        
    configs = {}
    for key, val in data.get("members", {}).items():
        configs[key] = MemberConfig(
            id=key, # Using the key as ID
            name=val.get("name", key),
            keywords=val.get("keywords", []),
            representative=val.get("representative", "")
        )
    return configs
