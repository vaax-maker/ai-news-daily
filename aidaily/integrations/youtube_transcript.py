#!/usr/bin/env python3
"""유튜브 자막/음성 전사 — 2단 폴백 엔진 (yt-dlp → MLX Whisper, M4 로컬 $0).

입력 자동 판별:
  - YouTube URL/ID  → tier1 yt-dlp 자막 → 실패/없음 시 tier2 오디오+Whisper
  - 로컬 오디오/영상 파일(.mp3/.m4a/.wav/.mp4/.mov 등) → 바로 Whisper 전사(음성전사)
youtube-transcript-api(봇차단·PO토큰 빈발) 대체. 자막 미생성 영상·일반 음성도 커버.

usage:
  python3 transcribe.py <youtube_url|video_id|로컬파일경로> [--lang ko]
        [--model mlx-community/whisper-large-v3-turbo] [--asr-only] [--json]
환경변수: WHISPER_MODEL
"""
import argparse, glob, json, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path

MLXW  = shutil.which("mlx_whisper") or os.path.expanduser("~/Library/Python/3.9/bin/mlx_whisper")
MODEL = os.environ.get("WHISPER_MODEL", "mlx-community/whisper-large-v3-turbo")
_AUDIO_EXT = (".mp3", ".m4a", ".wav", ".flac", ".aac", ".ogg", ".opus",
              ".mp4", ".mov", ".mkv", ".webm", ".avi")

# ── VAD(무음 제거) 전처리 설정 ──────────────────────────────────────
# MLX Whisper는 VAD가 없어 무음/음악 구간에서 환각(반복루프)을 낸다. silero-VAD(onnx)로
# 발화 구간만 남긴 wav를 만들어 넘기면 환각↓·속도↑. torch 불필요(onnxruntime만).
# vad_trim.py는 onnxruntime 있는 파이썬(기본 CLT python3.9)에서 돌린다. YT_VAD=0으로 끄기.
FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
_VAD_PY = os.environ.get("YT_VAD_PYTHON", "/usr/bin/python3")
_VAD_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vad_trim.py")
_VAD_ON = os.environ.get("YT_VAD", "1").lower() not in ("0", "off", "false", "")


def _impersonate_target(ytdlp):
    """yt-dlp가 실제로 쓸 수 있는 impersonate 타깃 1개 반환(없으면 None).

    YouTube 봇차단(429)은 `--impersonate`(브라우저 TLS/HTTP 지문 위장)로 우회하는데,
    이건 curl_cffi가 설치된 yt-dlp에서만 동작한다. `--list-impersonate-targets`에서
    '(unavailable)'(=curl_cffi 미설치) 줄을 빼고 사용 가능한 게 있으면 Chrome 우선 선택.
    """
    try:
        out = subprocess.run([ytdlp, "--list-impersonate-targets"],
                             capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return None
    avail = [ln for ln in out.splitlines()
             if ln.strip() and "unavailable" not in ln.lower()
             and not ln.lstrip().startswith(("[", "Client", "----"))]
    if not avail:
        return None
    for ln in avail:
        if ln.lower().startswith("chrome"):
            return "chrome"
    return avail[0].split()[0].lower()


def _resolve_ytdlp():
    """(바이너리경로, impersonate타깃) 결정 — impersonation 지원 yt-dlp 우선.

    봇차단 회피의 핵심은 curl_cffi 내장 yt-dlp이므로, 후보들을 차례로 probe해
    사용 가능한 impersonate 타깃이 있는 첫 바이너리를 고른다. uv tool(~/.local/bin)이나
    홈브루 어느 쪽이 curl_cffi를 가졌든 자동으로 옳은 것을 집는다.
    env로 강제/스킵 가능: YTDLP_BIN(경로), YTDLP_IMPERSONATE(타깃명 또는 'none').
    """
    forced = os.environ.get("YTDLP_IMPERSONATE")
    candidates = [os.environ.get("YTDLP_BIN"),
                  str(Path(__file__).resolve().parents[2] / ".venv-youtube/bin/yt-dlp"),
                  os.path.expanduser("~/.local/bin/yt-dlp"),
                  shutil.which("yt-dlp"),
                  "/opt/homebrew/bin/yt-dlp"]
    seen, fallback = set(), None
    for c in candidates:
        if not c or c in seen or not os.path.exists(c):
            continue
        seen.add(c)
        if fallback is None:
            fallback = c
        if forced:
            return c, (None if forced.lower() in ("none", "off", "0") else forced)
        target = _impersonate_target(c)
        if target:
            return c, target
    return (fallback or "yt-dlp"), None


YTDLP, _IMPERSONATE = _resolve_ytdlp()


def _yt_hardening():
    """yt-dlp 공통 봇차단 회피·안정화 플래그(자막·ASR 두 경로 공유).

    - --impersonate: curl_cffi 브라우저 위장. 429(봇차단) 회피의 핵심.
    - --cookies-from-browser: 로그인 쿠키로 인증(env YT_COOKIES_FROM_BROWSER, 예 'chrome').
      impersonate가 없을 때의 대체 우회책이자, throttle이 심할 땐 병행 가능.
    - 재시도/요청간 sleep: 일시적 429·네트워크 흔들림 흡수(곧장 비싼 ASR로 안 떨어지게).
    """
    args = ["--retries", "3", "--extractor-retries", "3",
            "--sleep-requests", "1", "--no-warnings"]
    if _IMPERSONATE:
        args += ["--impersonate", _IMPERSONATE]
    deno = shutil.which("deno") or ("/opt/homebrew/bin/deno" if os.path.exists("/opt/homebrew/bin/deno") else None)
    if deno:
        args += ["--js-runtimes", f"deno:{deno}"]
    cb = os.environ.get("YT_COOKIES_FROM_BROWSER")
    if cb:
        args += ["--cookies-from-browser", cb]
    return args


def _parse_timed(path):
    """vtt/srt → [{start,text}] (타임스탬프 보존, 중복 제거)."""
    segs, cur = [], None
    for ln in open(path, encoding="utf-8", errors="replace"):
        ln = ln.rstrip("\n")
        m = re.match(r"(\d+):(\d\d):(\d\d)[.,](\d+)\s*-->", ln)
        if m:
            cur = int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]) + float("0." + m[4])
            continue
        ln = re.sub(r"<[^>]+>", "", ln).strip()
        if (ln and "-->" not in ln and not ln.isdigit()
                and not ln.startswith(("WEBVTT", "Kind:", "Language:"))):
            if cur is None or (segs and segs[-1]["text"] == ln):
                continue
            segs.append({"start": cur, "text": ln})
    return segs



def _initial_prompt(title='', channel=''):
    """Short spelling vocabulary, without supplying claims or transcript prose."""
    from aidaily.integrations.terminology import load_glossary, with_title_reference
    names = []
    def add(value):
        value = ' '.join(str(value or '').split())[:240]
        if value and value.casefold() not in {item.casefold() for item in names}:
            names.append(value)
    # Use original wording as a spelling reference; omit URLs from ASR hints.
    context = re.sub(r'https?://\S+', '', f'{title} {channel}')
    add(re.sub(r'https?://\S+', '', title))
    add(re.sub(r'https?://\S+', '', channel))
    glossary = with_title_reference(load_glossary(), title)
    for term in glossary.get('terms', []):
        if not isinstance(term, dict) or not term.get('enabled', True):
            continue
        required = term.get('context') or []
        if required and not any(isinstance(word, str) and word.casefold() in context.casefold() for word in required):
            continue
        canonical = term.get('canonical')
        if isinstance(canonical, str):
            add(canonical)
    return ', '.join(names[:32])[:400]


def _whisper(media_path, lang, wd, *, initial_prompt=""):
    """로컬 미디어 파일 → MLX Whisper 전사. [{start,text}] 또는 None.

    언어 강제 금지(자동 감지): 영어 영상에 --language ko를 주면 Whisper가 반복
    환각(루프)에 빠져 한 단어("새로운")만 수백 회 반복하는 쓰레기 전사가 나온다
    (2026-06-05 PDxKrp-dTDA 사고). condition-on-previous-text False로 반복 루프도 완화.
    """
    command = [MLXW, media_path, "--model", MODEL,
                    "--condition-on-previous-text", "False",
                    "--output-dir", wd, "--output-format", "srt"]
    if initial_prompt:
        command.extend(["--initial-prompt", initial_prompt])
    completed = subprocess.run(command, capture_output=True, text=True, timeout=3600)
    if completed.returncode != 0:
        raise RuntimeError("whisper_process_failed")
    srts = glob.glob(os.path.join(wd, "*.srt"))
    return _parse_timed(srts[0]) if srts else None


def _to_16k_wav(media, wd):
    """미디어 → 16kHz mono wav(VAD·Whisper 공통 입력). 실패 시 None."""
    out = os.path.join(wd, "asr16k.wav")
    try:
        completed = subprocess.run([FFMPEG, "-y", "-i", media, "-ar", "16000", "-ac", "1", out],
                       capture_output=True, timeout=300)
    except Exception:
        return None
    return out if completed.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 0 else None


def _vad_trim(wav16k, wd):
    """silero-VAD로 무음 제거한 speech-only wav 경로. 비활성·실패 시 None(원본 폴백)."""
    if not (_VAD_ON and os.path.exists(_VAD_SCRIPT)):
        return None
    out = os.path.join(wd, "asr_speech.wav")
    try:
        r = subprocess.run([_VAD_PY, _VAD_SCRIPT, wav16k, out],
                           capture_output=True, text=True, timeout=300)
    except Exception:
        return None
    if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 0:
        sys.stderr.write(f"[vad] {r.stdout.strip()}\n")
        return out
    if r.stderr:
        sys.stderr.write(f"[vad] 스킵({r.stderr.strip()}) — 원본 전체로 전사\n")
    return None


def _asr(media, lang, wd, *, initial_prompt=""):
    """미디어 → 16k wav → (VAD 무음제거) → MLX Whisper. (segs, source) 또는 None.

    VAD가 켜져 있고 성공하면 발화 구간만 전사(환각↓·속도↑, source='asr+vad').
    VAD 실패/비활성이면 원본 전체 전사로 자동 폴백(source='asr').
    """
    wav = _to_16k_wav(media, wd)
    src = "asr"
    if wav:
        trimmed = _vad_trim(wav, wd)
        if trimmed:
            wav, src = trimmed, "asr+vad"
    else:
        wav = media   # ffmpeg 실패 시 원본 그대로 Whisper(mlx 내부 디코딩)
    segs = _whisper(wav, lang, wd, **({"initial_prompt": initial_prompt} if initial_prompt else {}))
    return (segs, src) if segs else None


def _yt_subs(url, langs, wd):
    base = os.path.join(wd, "sub")
    # --ignore-errors: 특정 언어(예: ko 자동번역 트랙)가 429를 내도 yt-dlp가 통째로
    # 중단하지 않고 나머지 언어(en 등)를 계속 받게 한다. 이게 없으면 영어 영상에서
    # ko 자동번역 429 하나가 자막 경로 전체를 죽여 → 무의미한 장시간 ASR로 떨어지고
    # 타임아웃 났다(2026-06-08 6amLO7I9xdg: ko 429→en 못 받음→46분 Whisper→120s타임아웃).
    subprocess.run([YTDLP, *_yt_hardening(), "--ignore-errors",
                    "--skip-download", "--write-auto-subs", "--write-subs",
                    "--sub-langs", ",".join(langs), "--sub-format", "vtt", "-o", base, url],
                   capture_output=True, timeout=120)
    vtts = sorted(glob.glob(base + "*.vtt"))
    for lang in langs:
        for v in vtts:
            if f".{lang}." in v:
                s = _parse_timed(v)
                if s:
                    return s, f"subs:{lang}"
    for v in vtts:
        s = _parse_timed(v)
        if s:
            return s, "subs"
    return None


def _yt_asr(url, lang, wd, *, initial_prompt=""):
    completed = subprocess.run([YTDLP, *_yt_hardening(), "-x", "--audio-format", "m4a",
                    "-o", os.path.join(wd, "audio.%(ext)s"), url],
                   capture_output=True, timeout=600)
    if completed.returncode != 0:
        raise RuntimeError("audio_download_failed")
    af = [p for p in glob.glob(os.path.join(wd, "audio.*"))
          if p.lower().endswith(_AUDIO_EXT) and os.path.getsize(p) > 0]
    if not af:
        return None
    return _asr(af[0], lang, wd, **({"initial_prompt": initial_prompt} if initial_prompt else {}))


def transcript_chars(text):
    return len(re.sub(r"\s+", "", text or ""))


def minimum_transcript_chars():
    return max(1, int(os.environ.get("YOUTUBE_MIN_TRANSCRIPT_CHARS", "1000")))


def transcribe(target, lang="ko", asr_only=False, *, title="", channel=""):
    """Caption -> audio/ASR, with short captions and exceptions falling through.

    Diagnostics contain stage/status only, never cookies or provider stderr.
    """
    stages = []
    prompt = _initial_prompt(title, channel) if title or channel else ""
    context_kwargs = {"initial_prompt": prompt} if prompt else {}
    def attempt(stage, operation):
        started = time.monotonic()
        try:
            result = operation()
            chars = transcript_chars(" ".join(str(x.get("text", "")) for x in result[0])) if result else 0
            status = "ok" if chars >= minimum_transcript_chars() else "insufficient"
            detail = {"stage": stage, "status": status, "chars": chars}
        except Exception as exc:
            result = None
            detail = {"stage": stage, "status": "failed", "error_type": type(exc).__name__,
                      "reason": str(exc) if str(exc) in ("audio_download_failed", "whisper_process_failed") else "stage_exception"}
        detail["seconds"] = round(time.monotonic() - started, 2)
        stages.append(detail)
        sys.stderr.write("[transcript-stage] " + json.dumps(detail) + "\n")
        return result if detail["status"] == "ok" else None

    with tempfile.TemporaryDirectory() as wd:
        if os.path.exists(target) and target.lower().endswith(_AUDIO_EXT):
            r = attempt("local_asr", lambda: _asr(target, lang, wd, **context_kwargs))
        else:
            vid = target
            m = re.search(r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{11})", target)
            if m:
                vid = m.group(1)
            url = target if target.startswith("http") else f"https://youtu.be/{vid}"
            r = None if asr_only else attempt("captions", lambda: _yt_subs(url, [lang, "en"], wd))
            if not r:
                r = attempt("audio_asr", lambda: _yt_asr(url, lang, wd, **context_kwargs))
        if not r:
            return {"target": target, "error": "자막·ASR 모두 실패", "stages": stages}
        segs, src = r
        full = " ".join(s["text"] for s in segs)
        return {"target": target, "source": src, "char_count": len(full),
                "transcript": full, "stages": stages,
                "segments_sample": segs[:: max(1, len(segs) // 20)]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="YouTube URL/ID 또는 로컬 오디오·영상 파일")
    ap.add_argument("--lang", default="ko")
    ap.add_argument("--asr-only", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    r = transcribe(a.target, a.lang, a.asr_only)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    elif "error" in r:
        sys.stderr.write(f"[실패] {r['error']}\n"); sys.exit(1)
    else:
        sys.stderr.write(f"[source={r['source']} chars={r['char_count']}]\n")
        print(r["transcript"])
