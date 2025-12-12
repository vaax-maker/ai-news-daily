
import os
import shutil
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

def main():
    print("Checking XR content for AI classification...")
    if os.path.exists(XR_DIR):
        for filename in sorted(os.listdir(XR_DIR)):
            if not filename.endswith('.html'): continue
            
            filepath = os.path.join(XR_DIR, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception as e:
                print(f"Error reading {filename}: {e}")
                continue

            ai_score, xr_score = classify(content)
            
            # Moves files heavily skewed towards AI
            if ai_score > (xr_score * 2) and ai_score > 3:
                print(f"Moving {filename} to AI folder (AI:{ai_score}, XR:{xr_score})")
                dest_path = os.path.join(AI_DIR, filename)
                if os.path.exists(dest_path):
                    print(f"  -> Destination {filename} already exists! Skipping move.")
                else:
                    shutil.move(filepath, dest_path)

if __name__ == '__main__':
    main()
