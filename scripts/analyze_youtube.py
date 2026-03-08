import os
import sys
import json
import re
from youtube_transcript_api import YouTubeTranscriptApi
from openai import OpenAI
from urllib.parse import urlparse, parse_qs

def extract_video_id(url):
    """Extracts the YouTube video ID from a URL."""
    query = urlparse(url)
    if query.hostname == 'youtu.be':
        return query.path[1:]
    if query.hostname in ('www.youtube.com', 'youtube.com'):
        if query.path == '/watch':
            p = parse_qs(query.query)
            return p.get('v', [None])[0]
        if query.path[:7] == '/embed/':
            return query.path.split('/')[2]
        if query.path[:3] == '/v/':
            return query.path.split('/')[2]
    return None

import subprocess

def get_video_transcript(video_id):
    """Fetches the transcript for a YouTube video using yt-dlp."""
    try:
        # We will use yt-dlp to download the subtitles as VTT and parse them
        url = f"https://www.youtube.com/watch?v={video_id}"
        
        # We write to stdout directly or a temp file
        temp_file = f"temp_subs_{video_id}"
        
        # Download subtitle (Try Korean first to avoid 429 Too Many Requests)
        for lang in ["ko", "en"]:
            cmd = [
                "yt-dlp",
                "--write-auto-sub",
                "--write-sub",
                "--sub-lang", lang,
                "--skip-download",
                "--sub-format", "vtt",
                "-o", temp_file,
                url
            ]
            
            try:
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                # Check if it succeeded for this language
                if any(f.startswith(temp_file) and f.endswith(".vtt") for f in os.listdir(".")):
                    break
            except subprocess.CalledProcessError:
                continue

        # Find the downloaded vtt file
        vtt_file = None
        for file in os.listdir("."):
            if file.startswith(temp_file) and file.endswith(".vtt"):
                vtt_file = file
                break
                
        if not vtt_file:
            return None
            
        # Parse VTT file to extract text with timestamps
        formatted_transcript = ""
        with open(vtt_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            # Look for timestamp line like "00:00:01.000 --> 00:00:03.000"
            if "-->" in line:
                start_time_str = line.split("-->")[0].strip()
                # Parse "HH:MM:SS.mmm" or "MM:SS.mmm"
                parts = start_time_str.split('.')[0].split(':')
                if len(parts) == 3:
                    h, m, s = map(int, parts)
                    total_seconds = h * 3600 + m * 60 + s
                elif len(parts) == 2:
                    m, s = map(int, parts)
                    total_seconds = m * 60 + s
                else:
                    total_seconds = 0
                    
                minutes = total_seconds // 60
                seconds = total_seconds % 60
                
                # Next lines are the text until empty line
                text_lines = []
                i += 1
                while i < len(lines) and lines[i].strip() != "":
                    # Clean up html tags from vtt (like <c>...</c>)
                    clean_text = re.sub(r'<[^>]+>', '', lines[i].strip())
                    if clean_text:
                        text_lines.append(clean_text)
                    i += 1
                
                if text_lines:
                    text_content = " ".join(text_lines)
                    formatted_transcript += f"[{minutes:02d}:{seconds:02d}] {text_content}\n"
            i += 1
            
        # Clean up temp files
        for file in os.listdir("."):
            if file.startswith(f"temp_subs_{video_id}"):
                try:
                    os.remove(file)
                except:
                    pass
            
        return formatted_transcript
        
    except subprocess.CalledProcessError as e:
        print(f"Error fetching transcript via yt-dlp: {e}")
        # The video might be age restricted or members only
        return "RESTRICTED_VIDEO_ERROR"
    except Exception as e:
        print(f"Error parsing transcript: {e}")
        return None

def generate_report(video_id, transcript, api_key):
    """Generates the HTML report using OpenAI GPT-4o."""
    client = OpenAI(api_key=api_key)
    
    # OpenAI o3-mini uses reasoning_effort instead of temperature, and prefers developer instructions.
    # To enforce the exact format requested by the user, we provide the full HTML skeleton.
    prompt = f"""
당신은 수석 웹 퍼블리싱 전문가이자 전문 에디터입니다.
제공된 영상의 자막(Transcript)을 상세하게 분석하여, 아래 주어진 [HTML 템플릿]의 {{TITLE}}, {{META_TAGS}}, {{BODY_CONTENT}} 부분만 채워서 완성된 HTML을 반환하세요.
출력은 마크다운 코드블럭(```html ... ```) 없이 **오직 순수한 HTML 코드 전체만** 출력해야 합니다. (`<!DOCTYPE html>` 부터 시작)

# 필수 작성 규칙 (엄수할 것)
1. **{{TITLE}}**: 영상의 전체 내용을 아우르는 핵심적이고 매력적인 제목을 한 줄 작성하세요.
2. **{{META_TAGS}}**: 영상의 핵심 키워드를 콤마(,)로 구분하여 3~5개 작성하세요.
3. **{{BODY_CONTENT}}**: 아래 지침에 따라 본문을 구성하세요.
   - **타임스탬프 문단 강제 규칙**: 모든 본문 단락은 예외 없이, 반드시 아래 HTML 구조로 작성해야 합니다.
     `<p><span class="timestamp" data-time="초단위">[MM:SS]</span> 해당 시간대 발화 내용의 상세한 설명...</p>`
     (예: 1분 30초면 `data-time="90"` 그리고 텍스트는 `[01:30]`)
   - **Anti-Summarization**: 내용을 너무 짧게 요약하지 마세요. 영상에 등장한 구체적인 수치, 논리 전개, 예시 등을 정보 손실 없이 최대한 길고 상세하게 풀어 쓰세요.
   - **소제목(h2) 활용**: 내용의 흐름이 바뀔 때마다 적절한 `<h2>소제목</h2>`을 중간중간 넣어 가독성을 높이세요.
   - **주식 종목/데이터 표 (옵션)**: 영상에서 주식 종목이나 가격, 특정 수치 비교가 등장했다면 본문 뒷부분에 `<table> ... </table>` 형태로 정리하여 제공하세요 (없으면 생략).

# [HTML 템플릿] (이 구조를 그대로 복사해서 빈칸을 채우세요)
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{TITLE}}</title>
    <style>
        /* fovea.css - Mobile Optimized Version */
        :root {{
            --primary-color: #65a30d;
            --primary-color-hover: #4d7c0f;
            --secondary-color: #475569;
            --background-color: #ffffff;
            --text-main: #111827;
            --text-muted: #4b5563;
            --border-color: #d1d5db;
            --touch-highlight: rgba(101, 163, 13, 0.1);
        }}
        html {{ font-size: 16px; scroll-behavior: smooth; }}
        body {{
            font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, Roboto, sans-serif;
            line-height: 1.4;
            color: var(--text-main);
            background-color: var(--background-color);
            max-width: 900px;
            margin: 0 auto;
            padding: 40px 20px;
            word-break: keep-all;
            -webkit-font-smoothing: antialiased;
        }}
        h1 {{
            margin-top: 1.2em;
            margin-bottom: 0.6em;
            font-size: 2.2rem;
            letter-spacing: -0.02em;
            border-bottom: 3px solid var(--primary-color);
            padding-bottom: 12px;
        }}
        h2 {{
            margin-top: 2.5em;
            margin-bottom: 1.2em;
            font-size: 1.75rem;
            color: var(--secondary-color);
            border-left: 6px solid var(--primary-color);
            padding-left: 18px;
        }}
        h3 {{
            font-size: 1.25rem;
            margin-top: 1.5em;
            color: var(--primary-color);
        }}
        .timestamp {{
            color: var(--primary-color);
            font-weight: 700;
            cursor: pointer;
            padding: 2px 6px;
            border-radius: 4px;
            transition: background-color 0.2s;
            display: inline-block;
            text-decoration: underline;
        }}
        .timestamp:active {{ background-color: var(--touch-highlight); }}
        .tag {{
            display: inline-block;
            background-color: #f3f4f6;
            color: #374151;
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 0.85rem;
            margin-right: 6px;
            margin-bottom: 8px;
            border: 1px solid var(--border-color);
        }}
        .video-container {{
            position: relative;
            width: 100%;
            padding-bottom: 56.25%;
            margin-bottom: 30px;
        }}
        .video-container iframe {{
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            border-radius: 12px;
        }}
        .meta-info {{
            background: #f8fafc;
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 30px;
            border: 1px solid var(--border-color);
        }}
        .editor-note {{
            background: #fffbeb;
            border: 1px solid #fef3c7;
            padding: 20px;
            border-radius: 12px;
            margin: 20px 0;
            font-size: 0.95rem;
        }}
        .editor-note strong {{ color: #92400e; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th, td {{
            border: 1px solid var(--border-color);
            padding: 12px;
            text-align: center;
        }}
        th {{ background-color: #f9fafb; }}
        footer {{
            margin-top: 50px;
            padding-top: 20px;
            border-top: 1px solid var(--border-color);
            text-align: center;
            color: var(--text-muted);
            font-size: 0.9rem;
        }}
        @media (max-width: 768px) {{
            body {{ padding: 20px 16px; }}
            h1 {{ font-size: 1.65rem; }}
            h2 {{ font-size: 1.35rem; }}
            .meta-info {{ padding: 12px; font-size: 0.85rem; }}
        }}
        /* Responsive Wrapper - Auto-injected */
        html {{ font-size: 16px; }}
        body {{ max-width: 900px; margin: 0 auto; padding: 1rem; line-height: 1.7; word-break: keep-all; }}
        img, video, iframe {{ max-width: 100%; height: auto; }}
        table {{ width: 100%; display: block; overflow-x: auto; }}
        pre, code {{ overflow-x: auto; white-space: pre-wrap; word-wrap: break-word; }}
        @media (max-width: 768px) {{
            body {{ padding: 0.75rem; font-size: 15px; }}
            h1 {{ font-size: 1.5rem; }}
            h2 {{ font-size: 1.25rem; }}
            h3 {{ font-size: 1.1rem; }}
        }}
    </style>
</head>
<body>
    <div class="meta-info">
        <strong>리포트 생성일:</strong> 오늘<br>
        <strong>출처:</strong> <a href="https://www.youtube.com/watch?v={video_id}">YouTube</a><br>
        <strong>핵심 태그:</strong> {{META_TAGS}}
    </div>
    
    <div class="video-container">
        <iframe id="player" src="https://www.youtube.com/embed/{video_id}" frameborder="0" allowfullscreen></iframe>
    </div>
    
    <h1>{{TITLE}}</h1>
    
    {{BODY_CONTENT}}
    
    <script>
        var tag = document.createElement('script');
        tag.src = "https://www.youtube.com/iframe_api";
        var firstScriptTag = document.getElementsByTagName('script')[0];
        firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);

        var player;
        function onYouTubeIframeAPIReady() {{
            player = new YT.Player('player', {{
                height: '100%',
                width: '100%',
                videoId: '{video_id}',
                events: {{ 'onReady': onPlayerReady }}
            }});
        }}

        function onPlayerReady(event) {{
            var timestamps = document.querySelectorAll('.timestamp');
            timestamps.forEach(function(el) {{
                el.addEventListener('click', function() {{
                    var time = this.getAttribute('data-time');
                    if (player && player.seekTo) {{
                        player.seekTo(time, true);
                        player.playVideo();
                    }}
                }});
            }});
        }}
    </script>
</body>
</html>
# 끝 [HTML 템플릿]

아래는 자막 원문 데이터입니다. 이를 바탕으로 리포트를 만드세요.
Transcript:
{transcript}
"""

    response = client.chat.completions.create(
        model="o3-mini",
        messages=[{"role": "user", "content": prompt}],
        reasoning_effort="high"
    )
    text = response.choices[0].message.content
    
    # Strip markdown code blocks if the model included them despite instructions
    if text.startswith("```html"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
        
    return text.strip()

def process_youtube_url(url, api_key):
    """Main pipeline for analyzing a YouTube URL."""
    video_id = extract_video_id(url)
    if not video_id:
        return {"success": False, "message": "유효하지 않은 유튜브 URL입니다."}
        
    print(f"[*] Extracted Video ID: {video_id}")
    
    transcript = get_video_transcript(video_id)
    if transcript == "RESTRICTED_VIDEO_ERROR":
        return {"success": False, "message": "해당 영상은 연령 제한, 멤버십 전용, 또는 비공개 영상이므로 자막을 추출할 수 없습니다. 공개된 일반 영상을 사용해주세요."}
    if not transcript:
        return {"success": False, "message": "자막을 추출할 수 없는 영상입니다. (자막이 비활성화되었거나 자동 생성 자막이 없습니다)"}
        
    print(f"[*] Successfully extracted transcript ({len(transcript)} chars)")
    print("[*] Generating report via OpenAI API... This might take up to 30-60 seconds.")
    
    try:
        html_report = generate_report(video_id, transcript, api_key)
        return {"success": True, "html": html_report, "video_id": video_id}
    except Exception as e:
        print(f"Error generating report: {e}")
        return {"success": False, "message": f"AI 분석 중 오류가 발생했습니다: {str(e)}"}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze_youtube.py <youtube_url>")
        sys.exit(1)
        
    url = sys.argv[1]
    
    # Needs to be run with OPENAI_API_KEY environment variable if testing in CLI
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable is missing.")
        sys.exit(1)
        
    result = process_youtube_url(url, api_key)
    if result["success"]:
        output_file = f"youtube_report_{result['video_id']}.html"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(result["html"])
        print(f"[*] Success! Report saved to {output_file}")
    else:
        print(f"[*] Failed: {result['message']}")
