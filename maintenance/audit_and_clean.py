
import os
import re

AI_DIR = '/Users/fovea/Documents/vsc-codex/VAAXfinal/docs/ai/daily'
XR_DIR = '/Users/fovea/Documents/vsc-codex/VAAXfinal/docs/xr/daily'

AI_KEYWORDS = ['AI', 'GPT', 'LLM', 'OpenAI', 'Neural', 'Learning', 'Agent', 'RAG', 'Prompt', 'Google', 'Anthropic', 'Gemini', 'NPU', 'GPU', 'Modeling', 'Robot']
XR_KEYWORDS = ['XR', 'VR', 'AR', 'MR', 'Spatial', 'Metaverse', 'Vision Pro', 'Quest', 'Headset', 'Augmented', 'Virtual', 'Glasses', 'Immersive', 'Unity', 'Unreal']

def classify(text):
    text_lower = text.lower()
    ai_score = sum(1 for k in AI_KEYWORDS if k.lower() in text_lower)
    xr_score = sum(1 for k in XR_KEYWORDS if k.lower() in text_lower)
    return ai_score, xr_score

def process_file(filepath, category):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return False, None

    original_content = content
    
    # 1. Remove <li>----...</li>
    # Regex: <li>\s*-{3,}[^<]*<\/li> -> Remove
    # Also handle entities if any, but usually it's raw text.
    content = re.sub(r'<li>\s*-{3,}.*?<\/li>', '', content)
    
    # 2. Fix double bullets: <li>- Text -> <li>Text
    # Looking for: <li> followed by optional whitespace, then a bullet char (-, •, ❑, *, etc), then optional whitespace.
    # Group 1: (<li>\s*)
    # Non-capturing group for bullet: (?:-|•|❑|\*|&bull;)
    content = re.sub(r'(<li>\s*)(?:-|•|❑|\*|&bull;)\s*', r'\1', content)

    # Classification Check (heuristic)
    ai_score, xr_score = classify(content)
    
    warning = None
    # Threshold: meaningful difference.
    if category == 'ai' and xr_score > (ai_score * 2) and xr_score > 3: 
        warning = f"[WARN] {os.path.basename(filepath)} (AI folder) looks like XR? (AI:{ai_score}, XR:{xr_score})"
    elif category == 'xr' and ai_score > (xr_score * 2) and ai_score > 3:
        warning = f"[WARN] {os.path.basename(filepath)} (XR folder) looks like AI? (AI:{ai_score}, XR:{xr_score})"

    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True, warning
    return False, warning

def main():
    print("Auditing AI...")
    if os.path.exists(AI_DIR):
        for filename in sorted(os.listdir(AI_DIR)):
            if not filename.endswith('.html'): continue
            changed, warning = process_file(os.path.join(AI_DIR, filename), 'ai')
            if changed: print(f"Fixed: {filename}")
            if warning: print(warning)
    else:
        print(f"Directory not found: {AI_DIR}")

    print("\nAuditing XR...")
    if os.path.exists(XR_DIR):
        for filename in sorted(os.listdir(XR_DIR)):
            if not filename.endswith('.html'): continue
            changed, warning = process_file(os.path.join(XR_DIR, filename), 'xr')
            if changed: print(f"Fixed: {filename}")
            if warning: print(warning)

if __name__ == '__main__':
    main()
