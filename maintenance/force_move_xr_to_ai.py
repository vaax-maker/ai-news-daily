
import os
import shutil

AI_DIR = '/Users/fovea/Documents/vsc-codex/VAAXfinal/docs/ai/daily'
XR_DIR = '/Users/fovea/Documents/vsc-codex/VAAXfinal/docs/xr/daily'

# List of files identified manually or by previous log as needing move
# Based on user request "Move them" and previous log:
FILES_TO_MOVE = [
    '2025-06-12_100000.html', '2025-06-25_100000.html', '2025-07-07_100000.html',
    '2025-07-11_100000.html', '2025-07-17_100000.html', '2025-07-18_100000.html',
    '2025-07-20_100000.html', '2025-07-22_100000.html', '2025-07-28_100000.html',
    '2025-07-29_100000.html', '2025-08-01_100000.html', '2025-08-07_100000.html',
    '2025-08-12_100000.html', '2025-11-18_100000.html'
    # Add key files identified in logs
]

def main():
    if not os.path.exists(AI_DIR): os.makedirs(AI_DIR)
    
    for filename in FILES_TO_MOVE:
        src = os.path.join(XR_DIR, filename)
        if not os.path.exists(src):
            print(f"Source not found: {src}")
            continue
            
        dst = os.path.join(AI_DIR, filename)
        if os.path.exists(dst):
            # Collision: Rename source to avoid overwrite
            base, ext = os.path.splitext(filename)
            new_name = f"{base}_from_xr{ext}"
            dst = os.path.join(AI_DIR, new_name)
            print(f"Collision for {filename}. Renaming to {new_name}")
        
        shutil.move(src, dst)
        print(f"Moved {src} -> {dst}")

if __name__ == '__main__':
    main()
