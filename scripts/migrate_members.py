import yaml
import os
import json
import shutil
from collections import defaultdict

CONFIG_PATH = "config/members.yaml"
DATA_DIR = "data/members"

# Mapping: Old Name/Key -> New Korean Name
MAPPING = {
    # Duplicates / Variations
    "LG 유플러스": "LG유플러스",
    "LG유플러스": "LG유플러스",
    "DEXTER studios": "덱스터스튜디오",
    "DEXTER STUDIOS": "덱스터스튜디오",
    "Jtbc": "JTBC",
    "Munhwa Broadcasting Corp.": "MBC",
    "KBS": "KBS",
    "Soongsil University": "숭실대학교",
    
    # English -> Korean
    "ALCHERA": "알체라",
    "KMA": "한국능률협회", # Assuming KMA in this context
    "MIXCON ENTERTAINMENT": "믹스콘엔터테인먼트",
    "VIVE STUDIOS": "비브스튜디오스",
    "concreate": "콘크리에이트",
    "AMBERIN": "앰버린",
    "ZENSTEM": "젠스템",
    "READY MADE": "레디메이드",
    "AIXLAB": "AIX랩",
    "LOCO": "로코",
    "MLINE": "엠라인스튜디오",
    "SM ENTERTAINMENT GROUP": "SM엔터테인먼트",
    "GALAXY CORP.": "갤럭시코퍼레이션",
    "COXSPACE": "콕스스페이스",
    "VENTURE SQUARE": "벤처스퀘어",
    "DOORIBUN": "두리번",
    "DATAKING": "데이터킹",
    "DIVEXR": "다이브엑스알",
    "kt engcore": "KT이엔지코어",
    "HNIX": "에이치엔아이엑스",
    "BIBIMBLE": "비빔블",
    "HTC": "HTC", # Keep as HTC for now or 에이치티씨? Keeping HTC is safer for brand recognition, or 에이치티씨 per user request? Let's go Korean: 에이치티씨
    "STUDIO SHOH ENTERTAINMENT": "스튜디오쇼",
    "SUPER VR": "슈퍼브이알",
    "CODEREACH": "코드리치",
    "DT": "디티",
    "AICON": "에이아이콘",
    "Caretive / Pulse9": "펄스나인",
    "Gcam": "지캠",
    "EQUAL SOUL": "이퀄소울",
    "NFINITY 7": "엔피니티세븐",
    "OVER THE HAND": "오버더핸드",
    "STMicroelectronics Asia Pacific Pte. Ltd": "ST마이크로일렉트로닉스",
    "TANGKA": "탕카",
    "STORYTACO": "스토리타코",
    "Contents Cloud": "콘텐츠클라우드",
    "VRUNCH": "브이런치",
    "Humelo": "휴멜로",
    "GAUSS LAB": "가우스랩",
    "DEEP INSPECTION": "딥인스펙션",
    "MIRACLE": "미라클",
    "VENTA X": "벤타엑스",
    "ANIPEN": "애니펜",
    "Visual Light": "비주얼라이트",
    "LITA": "리타",
    "SPACEELVIS": "스페이스엘비스",
    "PARABLE Ent.": "패러블엔터테인먼트",
    "ADVANCED RF TECHNOLOGIES,": "어드밴스드RF", # Removed comma
    "ZYX Technology .": "직스테크놀로지",
    "VUDEX": "뷰덱스",
    "VVR .": "브이브이알"
}

def load_yaml():
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def save_yaml(data):
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)

def load_json_news(member_key):
    # Filename sanitization same as main.py
    safe_name = member_key.replace("/", "_").replace("\\", "_")
    path = os.path.join(DATA_DIR, f"{safe_name}.json")
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_json_news(member_key, news_list):
    safe_name = member_key.replace("/", "_").replace("\\", "_")
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, f"{safe_name}.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(news_list, f, ensure_ascii=False, indent=2)

def migrate():
    data = load_yaml()
    members = data.get("members", {})
    
    new_members = {}
    
    # Process each existing member
    for old_key, config in members.items():
        # Determine New Name
        new_name = MAPPING.get(old_key, old_key) # Default to self if not mapped
        
        # If new_name matches the MAPPING target (Korean), strip English if it was mapped
        # Or if it's already Korean, keep it.
        
        # Merge Logic
        if new_name not in new_members:
            new_members[new_name] = {
                "name": new_name,
                "keywords": set(),
                "representative": config.get("representative", "")
            }
        
        # Add keywords
        old_keywords = config.get("keywords", [])
        if old_keywords:
            new_members[new_name]["keywords"].update(old_keywords)
        else:
             # If no keywords, at least add the name
             new_members[new_name]["keywords"].add(new_name)
        
        # Migrate Data (News)
        old_news = load_json_news(old_key)
        
        # If we already have news for this new_name (from a previous merged entry), load it
        existing_news = load_json_news(new_name)
        
        # Merge news (Deduplicate by link)
        merged_news = existing_news
        existing_links = {item['link'] for item in merged_news}
        
        for item in old_news:
            if item['link'] not in existing_links:
                merged_news.append(item)
                existing_links.add(item['link'])
        
        # Save merged news to NEW name
        if merged_news:
            save_json_news(new_name, merged_news)
            
        # If old_key != new_name and old_key file existed, we should effectively "delete" the old file
        # But to be safe, we just leave it for now or delete?
        # Let's delete old file if it's different from new file
        if old_key != new_name:
            old_safe = old_key.replace("/", "_").replace("\\", "_")
            old_path = os.path.join(DATA_DIR, f"{old_safe}.json")
            if os.path.exists(old_path):
                os.remove(old_path)
                print(f"Migrated & Deleted: {old_key} -> {new_name}")
        else:
            print(f"Processed: {old_key}")

    # Convert sets back to lists for YAML
    final_members_dict = {}
    for name, data in new_members.items():
        data["keywords"] = list(data["keywords"])
        final_members_dict[name] = data
        
    # Validation: Any English keys left?
    # We might have missed some. user can review.
    
    data["members"] = final_members_dict
    save_yaml(data)
    print("Migration Complete.")

if __name__ == "__main__":
    migrate()
