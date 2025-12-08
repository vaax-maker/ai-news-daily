import csv
import yaml
import re
import os

# CSV Path
CSV_PATH = "/Users/fovea/Documents/vsc-codex/vaax/VAAX 회원명단 - 시트1.csv"
OUTPUT_PATH = "config/members.yaml"

def clean_company_name(name):
    if not name or name == "#ERROR!":
        return None
    # Remove common suffixes/prefixes
    name = re.sub(r'\(주\)', '', name)
    name = re.sub(r'주식회사', '', name)
    name = re.sub(r'inc\.', '', name, flags=re.IGNORECASE)
    name = re.sub(r'co\.,\s*ltd', '', name, flags=re.IGNORECASE)
    name = name.strip()
    return name

def generate_id(name):
    # Generate a simple ID from English name or transliteration if possible, 
    # but for now, we might just use a sanitized version of the name or a counter if needed.
    # Since manual ID assignment is hard automatically, we'll try to use the cleaned name as ID (safechars).
    # If the name is Korean, we keep it as display name and use a hash or counter for ID?
    # Better: Use the name itself as key, but url-encode or just use it if YAML supports unicode keys (it does).
    # Ideally we want English IDs for filenames. 
    # For now, let's use a simple counter-based ID like 'member_001', 'member_002' OR 
    # if we can, just use the Korean name as the key in YAML.
    return name

def main():
    members = {}
    
    if not os.path.exists(CSV_PATH):
        print(f"File not found: {CSV_PATH}")
        return

    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        # Skip top 2 lines (header info)
        next(f) 
        next(f)
        
        reader = csv.DictReader(f)
        
        seen_companies = set()
        
        for row in reader:
            raw_company = row.get('회사', '').strip()
            name = row.get('이름', '').strip()
            
            cleaned_company = clean_company_name(raw_company)
            
            if not cleaned_company:
                continue
                
            if cleaned_company in seen_companies:
                continue
            
            seen_companies.add(cleaned_company)
            
            # Simple keyword generation: Company name itself
            keywords = [cleaned_company]
            
            # Additional keywords from CSV if any (Column '회사 키워드 5종' might be empty but let's check)
            extra_kw = row.get('회사 키워드 5종', '').strip()
            if extra_kw:
                keywords.extend([k.strip() for k in extra_kw.split(',') if k.strip()])

            members[cleaned_company] = {
                "name": cleaned_company,
                "keywords": keywords,
                "representative": name
            }

    print(f"Found {len(members)} unique companies.")
    
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        yaml.dump({"members": members}, f, allow_unicode=True, sort_keys=False)
    
    print(f"Saved to {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
