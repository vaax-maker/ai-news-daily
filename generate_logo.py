from PIL import Image, ImageDraw, ImageFont
import os

# Paths
WORKSPACE = "/Users/fovea/Documents/vsc-codex/VAAXfinal"
ARTIFACT_DIR = "/Users/fovea/.gemini/antigravity/brain/845d992c-4b50-47ee-bfcd-30ed56dee6a9"
LOGO_PATH = os.path.join(ARTIFACT_DIR, "uploaded_image_1765516639461.jpg")
OUTPUT_PATH = os.path.join(ARTIFACT_DIR, "logo_composite_v4.png")

# Content
LINES = [
    "VR-AR-AI-XR기술과",
    "Biz.를 연결하는",
    "성장나눔 커뮤니티"
]
SINCE_TEXT = "since 2016"

# Colors
COLOR_LIME = "#86D32A" 
COLOR_GRAY = "#333333"

# Font loading with fallbacks
font_paths = [
    # Try downloaded first (if valid)
    os.path.join(WORKSPACE, "NotoSansKR-Bold.ttf"),
    # Common Mac Korean Fonts
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    "/Library/Fonts/AppleGothic.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo-Bold.otf",
    "/System/Library/Fonts/AppleSDGothicNeo-Regular.otf",
    "/System/Library/Fonts/NanumGothic.ttf", 
    "/Library/Fonts/NanumGothic.ttf",
]

font_path = None
font_index = 0 # for ttc

for p in font_paths:
    if os.path.exists(p):
        try:
             # Try loading slightly to test
            if p.endswith(".ttc"):
                ImageFont.truetype(p, 10, index=1)
                font_index = 1
            else:
                ImageFont.truetype(p, 10)
            font_path = p
            print(f"Found valid font: {p}")
            break
        except Exception as e:
            print(f"Skipping {p}: {e}")

if not font_path:
    print("Error: No Korean font found.")
    exit(1)

# Load Logo
logo = Image.open(LOGO_PATH).convert("RGBA")
bbox = logo.getbbox() 
if bbox:
    logo = logo.crop(bbox)
W_logo, H_logo = logo.size

# Typography setup for Slogan
# Strategy: Calculate font size to be slightly smaller than Logo Height to allow centering.
# User said "Too high", implies standard top alignment looked high.
# Center alignment means equal space top and bottom.
target_text_height = int(H_logo * 0.85) # 85% of height to allow centering and avoid "top heavy" look.

# Initial guess
font_size = int(target_text_height / 2.2) 

# Font loading helper
def load_font(path, size, index=0):
    if path.endswith(".ttc"):
        return ImageFont.truetype(path, size, index=index)
    return ImageFont.truetype(path, size)

font = load_font(font_path, font_size, font_index)

# Recalculate to match target height
dummy_draw = ImageDraw.Draw(Image.new("RGBA", (1,1)))
def get_text_block_size(lines, fnt, spacing):
    heights = []
    widths = []
    for line in lines:
        lb = dummy_draw.textbbox((0, 0), line, font=fnt)
        widths.append(lb[2] - lb[0])
        heights.append(lb[3] - lb[1])
    total_h = sum(heights) + (spacing * (len(lines) - 1))
    return max(widths), total_h, heights

line_spacing = int(font_size * 0.15)
max_w, total_h, line_hs = get_text_block_size(LINES, font, line_spacing)

# Adjust font size to match target_text_height exactly
scale = target_text_height / total_h
final_font_size = int(font_size * scale)
font = load_font(font_path, final_font_size, font_index)
line_spacing = int(final_font_size * 0.15)
max_w, total_h, line_hs = get_text_block_size(LINES, font, line_spacing)

# Since 2016 setup
# Target width = Width of "VA".
# Heuristic: VAAX is 4 chars. VA is first half. Overlap is small.
# "VA" width approx 45-48% of total logo width.
target_since_width = int(W_logo * 0.46) 

# Find font size for Since 2016
s_size = int(final_font_size * 0.5) # Start guess
s_font = load_font(font_path, s_size, font_index)
s_bbox = dummy_draw.textbbox((0, 0), SINCE_TEXT, font=s_font)
s_current_w = s_bbox[2] - s_bbox[0]

# Scale to match target width exactly
s_scale = target_since_width / s_current_w
final_s_size = int(s_size * s_scale)
s_font = load_font(font_path, final_s_size, font_index)
s_bbox = dummy_draw.textbbox((0, 0), SINCE_TEXT, font=s_font)
since_w = s_bbox[2] - s_bbox[0]
since_h = s_bbox[3] - s_bbox[1]

# Canvas Sizing
padding_x = int(final_font_size * 0.4) # Gap between logo and slogan
total_w = W_logo + padding_x + max_w + 10
# Height: Logo is anchor. Since text is below.
# Total height = H_logo + margin + SinceH
total_h = H_logo + 15 + since_h 

# Check if Slogan is taller than Logo? (Shouldn't be, based on 0.85 target)
# But we need canvas to hold everything.
# Slogan centroid should align with Logo centroid? 
# Or Slogan vertical center == Logo vertical center.

canvas = Image.new("RGBA", (total_w, total_h + 20), (255, 255, 255, 255))
draw = ImageDraw.Draw(canvas)

# Paste Logo at (0, 0) relative to content area
offset_x = 0
offset_y = 0
canvas.paste(logo, (offset_x, offset_y))

# Draw Since 2016
# Position: Below logo.
since_y = offset_y + H_logo + 8 # 8px gap
draw.text((offset_x, since_y), SINCE_TEXT, font=s_font, fill=COLOR_GRAY)
# (It should naturally align left with logo)

# Draw Slogan
# Horizontal: Right of logo
text_x = offset_x + W_logo + padding_x
# Vertical: Center of Slogan aligns with Center of Logo.
# Logo Center Y = offset_y + H_logo / 2
# Slogan Top Y = Logo_Center_Y - (Slogan_Height / 2)
slogan_top_y = (offset_y + (H_logo / 2)) - (total_h // 2) 
# Wait, total_h variable above is CANVAS total height. 
# We need text block height:
_, txt_block_h, _ = get_text_block_size(LINES, font, line_spacing)
slogan_top_y = (offset_y + (H_logo / 2)) - (txt_block_h / 2)

current_y = slogan_top_y

# Line 1
line1_parts = ["VR-AR-AI-XR", " 기술과 Biz를"]
# Manual construction of line 1
current_x = text_x
l1_bbox = draw.textbbox((current_x, current_y), line1_parts[0], font=font)
draw.text((current_x, current_y), line1_parts[0], font=font, fill=COLOR_LIME)
current_x += (l1_bbox[2] - l1_bbox[0])
draw.text((current_x, current_y), line1_parts[1], font=font, fill=COLOR_GRAY)

# Line 2
current_y += line_hs[0] + line_spacing
line2_parts = ["연결하는 ", "성장나눔", " 커뮤니티"]

current_x = text_x
# Part 1: Gray
l2_p1_bbox = draw.textbbox((current_x, current_y), line2_parts[0], font=font)
draw.text((current_x, current_y), line2_parts[0], font=font, fill=COLOR_GRAY)
current_x += (l2_p1_bbox[2] - l2_p1_bbox[0])

# Part 2: Lime
l2_p2_bbox = draw.textbbox((current_x, current_y), line2_parts[1], font=font)
draw.text((current_x, current_y), line2_parts[1], font=font, fill=COLOR_LIME)
current_x += (l2_p2_bbox[2] - l2_p2_bbox[0])

# Part 3: Gray
draw.text((current_x, current_y), line2_parts[2], font=font, fill=COLOR_GRAY)

# Final Crop
bbox = canvas.getbbox()
if bbox:
    final_img = canvas.crop(bbox)
    final_img.save(OUTPUT_PATH)
    print(f"Saved to {OUTPUT_PATH}")
else:
    print("Error: Empty image")
