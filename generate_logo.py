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

# Typography setup
# We want 3 lines to equal H_logo.
# Rough estimate: 3 * (FontSize * 1.2) = H_logo => FontSize = H_logo / 3.6
font_size = int(H_logo / 3.4) 
font = None
if font_path.endswith(".ttc"):
     font = ImageFont.truetype(font_path, font_size, index=font_index)
else:
     font = ImageFont.truetype(font_path, font_size)

# Calculate exact text size
dummy_draw = ImageDraw.Draw(Image.new("RGBA", (1,1)))

line_heights = []
line_widths = []
for line in LINES:
    lb = dummy_draw.textbbox((0, 0), line, font=font)
    line_widths.append(lb[2] - lb[0])
    line_heights.append(lb[3] - lb[1])

# Spacing
line_spacing = int(font_size * 0.2)
# Correction: Vertical text block should NOT include the "since 2016" in the "Height match" constraint?
# User said "3 lines text height match logo height". "Since 2016" is separate "below".
total_text_height = sum(line_heights) + (len(LINES) - 1) * line_spacing

# Re-scale factor
# We want total_text_height == H_logo
scale_factor = H_logo / total_text_height
new_font_size = int(font_size * scale_factor * 0.98) # almost exact match

if font_path.endswith(".ttc"):
     font = ImageFont.truetype(font_path, new_font_size, index=font_index)
else:
     font = ImageFont.truetype(font_path, new_font_size)

# Recalculate measurements with new font
line_heights = []
line_widths = []
for line in LINES:
    lb = dummy_draw.textbbox((0, 0), line, font=font)
    line_widths.append(lb[2] - lb[0])
    line_heights.append(lb[3] - lb[1])
    
line_spacing = int(new_font_size * 0.2)
text_block_height = sum(line_heights) + (line_spacing * (len(LINES) - 1))

# Since 2016
since_font_size = int(new_font_size * 0.45)
if font_path.endswith(".ttc"):
     since_font = ImageFont.truetype(font_path, since_font_size, index=font_index)
else:
     since_font = ImageFont.truetype(font_path, since_font_size)
since_bbox = dummy_draw.textbbox((0, 0), SINCE_TEXT, font=since_font)
since_w = since_bbox[2] - since_bbox[0]
since_h = since_bbox[3] - since_bbox[1]

# Canvas
padding_x = int(new_font_size * 0.4)
max_text_w = max(line_widths)
total_w = W_logo + padding_x + max(max_text_w, since_w) + 20
total_h = max(H_logo, text_block_height + since_h + 10) 

canvas = Image.new("RGBA", (total_w, total_h + 50), (255, 255, 255, 255))
draw = ImageDraw.Draw(canvas)

# Paste Logo
y_offset = 20
x_offset = 10
canvas.paste(logo, (x_offset, y_offset))

# Draw Text
text_x = x_offset + W_logo + padding_x
text_y = y_offset

# Line 1
line1_parts = ["VR-AR-AI-XR", "기술과"]
current_x = text_x
l1_bbox = draw.textbbox((current_x, text_y), line1_parts[0], font=font)
draw.text((current_x, text_y), line1_parts[0], font=font, fill=COLOR_LIME)
current_x += (l1_bbox[2] - l1_bbox[0])
draw.text((current_x, text_y), line1_parts[1], font=font, fill=COLOR_GRAY)

# Line 2
current_y = text_y + line_heights[0] + line_spacing
draw.text((text_x, current_y), LINES[1], font=font, fill=COLOR_GRAY)

# Line 3
line3_parts = ["성장나눔", " 커뮤니티"]
current_y += line_heights[1] + line_spacing
current_x = text_x
l3_bbox = draw.textbbox((current_x, current_y), line3_parts[0], font=font)
draw.text((current_x, current_y), line3_parts[0], font=font, fill=COLOR_LIME)
current_x += (l3_bbox[2] - l3_bbox[0])
draw.text((current_x, current_y), line3_parts[1], font=font, fill=COLOR_GRAY)

# Since 2016
# Position: Bottom right of text block? Or just below?
# Let's put it aligned to the left of the text block, below line 3.
since_y = current_y + line_heights[2] + int(line_spacing/2)
draw.text((text_x, since_y), SINCE_TEXT, font=since_font, fill=COLOR_GRAY)

# Final Crop
bbox = canvas.getbbox()
if bbox:
    final_img = canvas.crop(bbox)
    # Add minimal padding 5px
    w, h = final_img.size
    final_canvas = Image.new("RGBA", (w+10, h+10), (255, 255, 255, 255))
    final_canvas.paste(final_img, (5, 5))
    final_canvas.save(OUTPUT_PATH)
    print(f"Saved to {OUTPUT_PATH}")
else:
    print("Error: Empty image")
