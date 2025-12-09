import os
import sys
import yaml

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import load_members

def cleanup_members():
    # Load active members
    members_config = load_members()
    active_ids = set(members_config.keys())
    
    data_dir = "data/members"
    if not os.path.exists(data_dir):
        print("Data directory not found.")
        return

    files = os.listdir(data_dir)
    deleted_count = 0
    
    print(f"Checking {len(files)} files in {data_dir}...")
    
    for f in files:
        if not f.endswith(".json"):
            continue
            
        member_id = f.replace(".json", "")
        
        # Check against active IDs
        # Note: filenames might be safe names (slashes replaced), but MemberConfig uses raw keys.
        # Strict checking: we need to handle potential safe name conversion if keys have special chars.
        # But config keys seem to be Korean names mostly.
        
        # Let's see if we can match.
        if member_id not in active_ids:
            # Try decodings just in case? No, file system is utf-8 usually.
            # What if safe_name was used?
            # In main.py: safe_name = m_key.replace("/", "_").replace("\\", "_")
            # So we should check if member_id matches any safe_name of active_ids
            
            is_active = False
            for aid in active_ids:
                safe_aid = aid.replace("/", "_").replace("\\", "_")
                if member_id == safe_aid:
                    is_active = True
                    break
            
            if not is_active:
                path = os.path.join(data_dir, f)
                print(f"[DELETE] {f} (Not in config)")
                try:
                    os.remove(path)
                    deleted_count += 1
                except Exception as e:
                    print(f"Error deleting {path}: {e}")
                    
    print(f"Cleanup complete. Deleted {deleted_count} files.")

if __name__ == "__main__":
    cleanup_members()
