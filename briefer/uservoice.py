#!/usr/bin/env python3
"""사용자 피드백 — AI 실사용자 커뮤니티 대화를 '피드백' 관점으로 매일 정리.

컨셉: 뉴스/브리핑이 아니라, 실사용자가 현장에서 겪은 이슈·반응·요구를 '사용자 피드백'으로
읽는다. 각 항목은 **이슈 → 내용 → 해설** 3단으로 제시한다. 디자인은 뉴스면과 무관한 독립 폼.

소스(2026-08-13 결정):
- **GPTers 덕후방만** — 맥북에어(fovea)에 SSH로 kakaocli 읽기(경합 없음).
  ※ 미니 직접 읽기는 xbot sync 데몬과 DB 잠금 경합으로 불안정 → 에어 경유.
  (방 ID·SSH 호스트 등 식별자는 gitignore된 briefer/_identifiers.py 에.)
- 홀딩(미니 전용, DB 경합으로 미읽음): 여러 방 — 에어 합류/미니 read 해결 시 활성화.

LLM = hermes(xbot 컨테이너, 로컬·키 불요). 정책 = 검증 게이트(근거 없는 창작/개인정보 방지).
프라이버시: 개인 이름/핸들/연락처/원문 인용 배제 — 주제·흐름·체감만 집약.

실행:
  python3 -m briefer.uservoice --docs-root docs                 # 에어 SSH 덤프+생성+렌더
  python3 -m briefer.uservoice --docs-root docs --dump-dir DIR  # 기존 덤프 사용(프리뷰)
"""
from __future__ import annotations
import argparse
import datetime
import html
import json
import os
import re
import subprocess
import sys

from briefer import feedback_sources

# ---- 소스 식별자(카톡 오픈채팅 ID·SSH 호스트) ----
# 개인정보라 gitignore된 로컬 briefer/_identifiers.py 에서 로드(공개 repo 유출 방지).
# 파일이 없으면 환경변수(USERVOICE_*)로 폴백. 실값은 로컬 파일/환경변수에만 존재.
try:
    from briefer import _identifiers as _ids
    AIR_HOST = _ids.AIR_HOST
    AIR_KAKAOCLI = _ids.AIR_KAKAOCLI
    GPTERS_CID = _ids.GPTERS_CID
    GPTERS_ROOM = _ids.GPTERS_ROOM
except ImportError:
    AIR_HOST = os.environ.get("USERVOICE_AIR_HOST", "")
    AIR_KAKAOCLI = os.environ.get("USERVOICE_AIR_KAKAOCLI", "kakaocli")
    GPTERS_CID = os.environ.get("USERVOICE_GPTERS_CID", "")
    GPTERS_ROOM = os.environ.get("USERVOICE_GPTERS_ROOM", "")

SITE_URL = "https://vaax-maker.github.io/ai-news-daily/"
FEEDBACK_URL = "https://vaax-maker.github.io/ai-news-daily/v2/uservoice.html"

# ---- LLM (OpenRouter, 공통 briefer.llm) ----
MODELS = ["openai/gpt-5.6-luna", "anthropic/claude-sonnet-4-6", "google/gemini-3.1-flash-lite"]


def _llm_complete(system: str, user: str, model: str, timeout: int = 120) -> str:
    """OpenRouter 텍스트 생성(공통 briefer.llm). xbot/Docker 의존 없음(2026-08-18 전환)."""
    from briefer import llm
    return llm.complete(system, user, models=[model], timeout=min(timeout, 120), retries=2)


# ---- 대화 수집(에어 SSH) + 코퍼스 ----
def dump_from_air(dump_dir: str, since: str = "2d") -> None:
    os.makedirs(dump_dir, exist_ok=True)
    out = os.path.join(dump_dir, f"chat_{GPTERS_CID}.json")
    cmd = ["ssh", "-o", "ConnectTimeout=10", "-o", "BatchMode=yes", AIR_HOST,
           f"{AIR_KAKAOCLI} messages --chat-id {GPTERS_CID} --since {since} --limit 4000 --json"]
    with open(out, "w", encoding="utf-8") as f:
        subprocess.run(cmd, stdout=f, stderr=subprocess.DEVNULL, timeout=90, check=False)
    n = os.path.getsize(out)
    print(f"[dump] 에어 GPTers ← {n} bytes (since {since})", file=sys.stderr)


def _msg_text(m: dict) -> str:
    for k in ("message", "text", "content", "plainText", "body"):
        v = m.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


_URLONLY = re.compile(r'^\s*https?://\S+\s*$')
_NOISE = re.compile(r'(사진|동영상|이모티콘|삭제된 메시지|음성메시지|파일:|샵검색|송금)')


def load_corpus(dump_dir: str, max_chars: int = 12000) -> str:
    """GPTers 덤프 → 정제 대화 텍스트(개인식별/노이즈/JSON 시스템메시지 제거).

    빈/깨진 덤프(에어 SSH 0바이트 등)는 크래시 대신 빈 코퍼스로 처리 —
    한 소스 실패가 전체 발행을 막지 않도록(2026-08-18 안정화)."""
    path = os.path.join(dump_dir, f"chat_{GPTERS_CID}.json")
    if not os.path.exists(path):
        return ""
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read().strip()
        if not raw:
            print("[uservoice] GPTers 덤프 0바이트 — 빈 코퍼스로 계속", file=sys.stderr)
            return ""
        data = json.loads(raw)
    except Exception as e:  # noqa
        print(f"[uservoice] GPTers 덤프 로드 실패({type(e).__name__}) — 빈 코퍼스로 계속",
              file=sys.stderr)
        return ""
    msgs = data if isinstance(data, list) else data.get("messages", [])
    lines = []
    for m in msgs:
        t = str(m.get("type") or m.get("messageType") or "").lower()
        if t and t not in ("text", "reply", "0", "1"):
            continue
        txt = _msg_text(m)
        if not txt or txt.startswith("{") or _URLONLY.match(txt) or _NOISE.search(txt):
            continue
        txt = re.sub(r'\s+', ' ', txt).strip()
        if len(txt) >= 2:
            lines.append(txt[:280])
    body = "\n".join(lines)
    return body[-max_chars:] if len(body) > max_chars else body


# ---- 날짜 간 중복 제거(seen-store) ----
def load_seen(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa
        return {}


def save_seen(path: str, seen: dict, today: str, keep_days: int = 7) -> None:
    """오래된 항목 정리 후 저장(rolling window). 파싱 실패 항목은 보존."""
    try:
        cutoff = datetime.date.fromisoformat(today) - datetime.timedelta(days=keep_days)
        pruned = {}
        for url, d in seen.items():
            try:
                if datetime.date.fromisoformat(d) >= cutoff:
                    pruned[url] = d
            except Exception:  # noqa
                pruned[url] = d
        with open(path, "w", encoding="utf-8") as f:
            json.dump(pruned, f, ensure_ascii=False, indent=1)
    except Exception as e:  # noqa
        print(f"[seen] 저장 실패: {e}", file=sys.stderr)


# xbot tap이 적재하는 오픈채팅 JSONL(미니 소스, 경합 없음). ⚠️ 이 머신(mini) 전용.
UV_TAP_JSONL = os.path.join(os.path.expanduser("~"), ".xbot", "uservoice-rooms.jsonl")


def load_jsonl_rooms(hours: int = 24, exclude_ids=(GPTERS_CID,),
                     per_room_chars: int = 6000, seen: dict | None = None):
    """xbot tap JSONL에서 최근 N시간 오픈채팅 메시지를 방별로 읽음(DB 경합 없음).

    GPTers는 에어로 따로 읽으므로 기본 제외. seen(=이미 발행에 쓴 메시지 지문 dict)이 주어지면
    메시지 **내용 해시로 날짜간 중복을 제거**한다(24h 창 겹침·재실행에도 같은 대화 재유입 방지).
    반환: ({방라벨: 정제 텍스트}, [이번에 새로 쓴 메시지 지문 리스트])."""
    import time as _t
    import hashlib
    if not os.path.exists(UV_TAP_JSONL):
        return {}, []
    cutoff = _t.time() - hours * 3600
    exclude = {str(x) for x in exclude_ids}
    seen = seen or {}
    rooms: dict[str, list] = {}
    new_hashes: list = []
    with open(UV_TAP_JSONL, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:  # noqa
                continue
            try:
                if float(r.get("ts", 0)) < cutoff:
                    continue
            except Exception:  # noqa
                continue
            if str(r.get("chat_id", "")) in exclude:
                continue
            txt = (r.get("text") or "").strip()
            if not txt or txt.startswith("{") or _URLONLY.match(txt) or _NOISE.search(txt):
                continue
            norm = re.sub(r"\s+", " ", txt)[:280]
            h = "uv:" + hashlib.md5(norm.encode("utf-8")).hexdigest()[:16]
            if h in seen:              # 지난 날 발행에 이미 쓴 메시지 → 건너뜀(날짜간 중복 방지)
                continue
            new_hashes.append(h)
            label = (r.get("chat_name") or str(r.get("chat_id", "")) or "오픈채팅").strip()[:40]
            rooms.setdefault(label, []).append(norm)
    out = {}
    for label, lines in rooms.items():
        body = "\n".join(lines)
        out[label] = body[-per_room_chars:] if len(body) > per_room_chars else body
    return out, new_hashes


def trim_jsonl(days: int = 5) -> None:
    """tap JSONL을 최근 N일치로 유지(무한 증가·장기 보관 방지)."""
    import time as _t
    if not os.path.exists(UV_TAP_JSONL):
        return
    cutoff = _t.time() - days * 86400
    try:
        kept = []
        with open(UV_TAP_JSONL, encoding="utf-8") as f:
            for line in f:
                try:
                    if float(json.loads(line).get("ts", 0)) >= cutoff:
                        kept.append(line)
                except Exception:  # noqa
                    continue
        with open(UV_TAP_JSONL, "w", encoding="utf-8") as f:
            f.writelines(kept)
    except Exception as e:  # noqa
        print(f"[tap] trim 실패: {e}", file=sys.stderr)


def build_multi_corpus(gpters: str, seen: dict | None = None,
                       extra_rooms: dict | None = None,
                       caps=(("reddit", 18), ("hn", 18), ("geeknews", 12)),
                       item_chars: int = 240, gpters_chars: int = 5500):
    """GPTers(오픈채팅) + Reddit·HN·긱뉴스 → 소스 라벨링 코퍼스.

    seen(=이미 발행한 URL dict)이 주어지면 웹 소스 아이템을 URL 기준으로 **중복 제거**한다.
    반환: (코퍼스텍스트, 활성소스, 이번에 새로 쓴 URL 목록)."""
    seen = seen or {}
    raw = {
        "reddit": feedback_sources.fetch_reddit(),
        "hn": feedback_sources.fetch_hn(since_h=24),          # 최근 24시간
        "geeknews": feedback_sources.fetch_geeknews(),
    }
    label = {"reddit": "Reddit (글로벌 AI 커뮤니티)", "hn": "Hacker News (개발자)",
             "geeknews": "긱뉴스 (국내 개발자)"}
    pfx = {"reddit": "R", "hn": "H", "geeknews": "G"}
    blocks, active, new_urls, refmap = [], [], [], {}
    for key, cap in caps:
        items = [it for it in raw.get(key, [])
                 if it.get("url") and it["url"] not in seen][:cap]   # 날짜간 중복 제거
        if not items:
            continue
        active.append(label[key])
        lines = []
        for i, it in enumerate(items, 1):
            rid = f"{pfx[key]}{i}"                             # 참조표식 → 이슈별 출처 링크
            refmap[rid] = {"url": it["url"], "source": label[key]}
            new_urls.append(it["url"])
            lines.append(f"[{rid}] {it['text'][:item_chars]}")
        blocks.append(f"===== [{label[key]}] =====\n" + "\n".join(lines))
    if gpters.strip():                                         # 오픈채팅은 24h 창으로 중복 최소화
        active.append("오픈채팅 · GPTers")
        blocks.append(f"===== [오픈채팅 · GPTers 덕후방 (비공개 대화)] =====\n{gpters[:gpters_chars]}")
    for label, body in (extra_rooms or {}).items():            # xbot tap 방(미니 소스)
        if body.strip():
            active.append(f"오픈채팅 · {label}")
            blocks.append(f"===== [오픈채팅 · {label} (비공개 대화)] =====\n{body}")
    return "\n\n".join(blocks), active, new_urls, refmap


# ---- LLM 생성 (이슈/내용/해설) ----
SYSTEM = (
    "너는 VAAX의 '사용자 피드백 애널리스트'다. AI 도구를 실제로 쓰는 사람들의 여러 커뮤니티"
    "(Reddit·Hacker News·긱뉴스·오픈채팅)에서 오늘 오간 글·대화를 읽고, 실사용자가 현장에서 겪은 "
    "이슈·반응·요구를 '사용자 피드백'으로 정리한다. 뉴스가 아니라 실사용자의 목소리를 대변한다. "
    "편성은 **주제(이슈) 우선**이다: 여러 소스에 겹치는 이슈는 반드시 하나로 묶어 주제당 항목 1개로만 "
    "낸다(같은 주제가 Reddit·오픈채팅 양쪽에 나와도 항목은 하나). 소스 국적 매핑 — **해외=Reddit·"
    "Hacker News, 국내=긱뉴스·오픈채팅**. 특히 오픈채팅은 국내 실사용자가 도구를 직접 쓰며 겪은 현장 "
    "목소리(질문·꿀팁·불만·비교)라 가장 생생한 사용기이니 비중 있게 반영한다. **한 주제가 국내·해외 "
    "양쪽에서 나오면** content/commentary에서 '해외에선 ~, 국내에선 ~'처럼 두 각도를 구분해 담고, 한쪽에서만 "
    "나온 주제는 굳이 국내/해외를 나누지 않는다.\n"
    "원칙:\n"
    "(1) 대화에 실재하지 않는 것은 절대 쓰지 않는다. 수치·인용·주체·사건을 창작하지 마라. 대화에서 "
    "근거를 취하되 우리 문장으로 재작성한다.\n"
    "(2) 프라이버시 vs 출처: **출처(단톡방/커뮤니티 이름)는 그대로 명시**한다 — 코퍼스 각 구획의 "
    "'오픈채팅 · <방이름>' 또는 'Reddit/Hacker News/긱뉴스' 라벨을 sources에 실제 이름으로 적는다. "
    "단, **방 안의 특정 개인**은 보호: 개인의 이름·아이디·@멘션·연락처·회사 등 신원 정보 금지, 개인 "
    "메시지를 그대로 인용하지 말고 여러 사람의 이야기를 '이슈·흐름·체감'으로 묶어라. 홍보/스팸/링크만 "
    "있는 메시지는 무시.\n"
    "(3) 각 항목은 이슈(issue)·내용(content)·해설(commentary) 3단. issue=실사용자가 부딪힌 문제/질문/"
    "반응을 압축한 제목. content=사용자들이 실제로 무엇을 말했는지(사실). commentary=그 피드백이 뜻하는 "
    "바·왜 중요한지(애널리스트 관점).\n"
    "(4) category(사용성/비용/신뢰/기능요청/성능/만족 중)와 sentiment(불만/궁금/제안/호평/우려 중)를 "
    "대화 근거로 붙인다.\n"
    "(5) 각 항목에 **어떤 서비스·어떤 모델·어떤 사용조건**인지 메타를 붙인다: service(제품/서비스명, "
    "예 ChatGPT·Claude Code·Codex·Cursor·Midjourney·Slack), model(모델명, 예 GPT-5.6·Claude Sonnet·"
    "Gemini), conditions(사용조건: 요금제·플랫폼·환경, 예 유료 요금제·데스크톱 웹·API·무료 티어). "
    "**반드시 대화에 명시된 것만 쓰고, 언급이 없으면 빈 문자열(\"\")로 둔다. 추측·창작 절대 금지.**\n"
    "(6) 한국어. 이모지·해시태그 금지. 반드시 JSON만 출력(설명·코드펜스 금지)."
)


def _build_user(corpus: str, feedback: str = "") -> str:
    fb = ""
    if feedback:
        fb = ("\n\n[직전 시도 반려 사유 — 반드시 교정]\n" + feedback +
              "\n위 지적을 없애라. 대화에 '명확히' 있는 것만. 근거 약한 구체 표현은 빼고 좁혀 다시 작성.")
    schema = ('\n\n위는 오늘 AI 실사용자 커뮤니티 대화다. 아래 JSON만 출력하라:\n'
              '{\n'
              '  "title": "<오늘 사용자 피드백을 관통하는 한 줄, 40자 이내>",\n'
              '  "mood": "<오늘의 전반 정서 한 단어, 예: 기대·불만·혼란·활기>",\n'
              '  "overview": "<오늘 피드백 개관 2~3문장 — 지배적 정서·핵심 이슈>",\n'
              '  "items": [\n'
              '    {"issue":"<이슈 제목 22자 이내>",'
              '"category":"<사용성|비용|신뢰|기능요청|성능|만족>",'
              '"sentiment":"<불만|궁금|제안|호평|우려>",'
              '"service":"<나온 제품/서비스명, 없으면 \\"\\">",'
              '"model":"<나온 모델명, 없으면 \\"\\">",'
              '"conditions":"<사용조건: 요금제·플랫폼·환경, 근거 있을 때만, 없으면 \\"\\">",'
              '"sources":["<이 이슈가 나온 출처를 실제 이름으로. 오픈채팅이면 방 이름 그대로(예: '
              '\\"코난쌤 오픈채팅방\\"·\\"김효율의 AI개발단\\"), 웹이면 Reddit·Hacker News·긱뉴스. '
              '코퍼스 구획 라벨을 그대로 옮긴다>"],'
              '"refs":["<이 이슈 근거가 된 항목 표식, 예: R1·H3·G2 (여러 개 가능), 오픈채팅 근거면 비움>"],'
              '"content":"<사용자들이 실제로 말한 내용 1~2문장>",'
              '"commentary":"<해설: 뜻하는 바·왜 중요한지 1~2문장>"}\n'
              '  ]\n'
              '}\n'
              'items는 서로 다른 이슈로 6~8개. service/model/conditions는 명시된 것만(없으면 ""). '
              'sources는 소스 구획명 기준 1~2개. refs는 각 항목 앞의 대괄호 표식([R1] 등)에서 '
              '이 이슈의 근거가 된 것을 1~3개 정확히 옮겨 적는다(없는 표식 창작 금지).')
    return f"[오늘의 사용자 피드백 소스]\n{corpus}{schema}{fb}"


def _parse_json(raw: str) -> dict:
    s = re.sub(r'^```(?:json)?\s*', '', raw.strip())
    s = re.sub(r'\s*```$', '', s).strip()
    m = re.search(r'\{.*\}', s, re.S)
    return json.loads(m.group(0) if m else s)


def _validate(d: dict) -> None:
    if not d.get("title") or not d.get("overview"):
        raise ValueError("missing title/overview")
    it = d.get("items")
    if not isinstance(it, list) or len(it) < 3:
        raise ValueError(f"items 부족: {it if not isinstance(it, list) else len(it)}")
    for x in it:
        if not x.get("issue") or not x.get("content"):
            raise ValueError("item issue/content 누락")


def generate(corpus: str, models: list[str] | None = None, feedback: str = "") -> dict:
    from briefer import llm
    if not llm.KEY:
        raise RuntimeError("OPENROUTER_API_KEY 없음 (env·~/xbot/.env 확인).")
    user = _build_user(corpus, feedback=feedback)
    last = None
    for model in (models or MODELS):
        try:
            d = _parse_json(_llm_complete(SYSTEM, user, model=model))
            _validate(d)
            d["_model"] = model
            return d
        except Exception as e:  # noqa
            last = f"{model}: {e}"
            continue
    raise RuntimeError(f"모든 모델 실패: {last}")


# ---- 검증 게이트 ----
_NUM = re.compile(r'\d[\d,\.]*\d|\d')


def _nn(s: str) -> str:
    return (s or "").replace(",", "").replace(".", "")


def evidence_issues(gen: dict, corpus: str) -> list[str]:
    src = _nn(corpus)
    issues = []
    fields = [gen.get("title", ""), gen.get("overview", "")]
    for x in gen.get("items", []):
        fields += [x.get("issue", ""), x.get("content", ""), x.get("commentary", "")]
    for f in fields:
        for n in _NUM.findall(f or ""):
            if len(_nn(n)) >= 2 and _nn(n) not in src:
                issues.append(f"수치 '{n}' 대화 미확인")
    return issues[:8]


_JUDGE_SYS = (
    "너는 사용자 피드백 요약 사실검증관이다.\n"
    "- 각 항목(이슈/내용/해설)은 대화의 요약이다. 항목·대화로 뒷받침되면 근거 있음으로 본다(발췌에 그 "
    "대목이 안 보여도 항목에 있으면 통과). 발췌는 표본일 뿐 전체가 아니다.\n"
    "- title/overview/해설은 편집·분석 관점이다. 대화·항목에서 도출되는 강조·프레이밍은 허용한다.\n"
    "- 실패(ok=false)는 오직: (a) 항목에도 대화에도 없는 새 구체 사실(고유명사·수치·인용·사건)을 지어냄"
    "(fabrication), (b) 개인 신원(이름·아이디·연락처) 노출(pii).\n"
    "- 일반화·해석·집약은 실패 사유 아님. 의심스러우면 통과. 반드시 JSON만 출력한다."
)


def judge(gen: dict, corpus: str, model: str = "openai/gpt-5.6-luna") -> dict:
    sample = corpus[:6000]
    it = "\n".join(f'  - {x.get("issue","")}: {x.get("content","")}' for x in gen.get("items", []))
    user = (f'대화 코퍼스(표본, 전체 아님):\n{sample}\n---\n'
            f'피드백 항목 — 근거 목록:\n{it}\n---\n'
            f'제목: {gen.get("title","")}\n개관: {gen.get("overview","")}\n---\n'
            '아래 JSON만: {"ok":true/false,"fabrication":true/false,"pii":true/false,"issues":["..."]}\n'
            '항목으로 뒷받침되면 근거 있는 것이다.')
    try:
        raw = _llm_complete(_JUDGE_SYS, user, model=model, timeout=120)
        s = re.sub(r'^```(?:json)?\s*', '', raw.strip())
        s = re.sub(r'\s*```$', '', s).strip()
        m = re.search(r'\{.*\}', s, re.S)
        return json.loads(m.group(0) if m else s)
    except Exception as e:  # noqa
        return {"ok": None, "issues": [f"judge 실패: {e}"]}


def evaluate(gen: dict, corpus: str, model: str | None = None) -> dict:
    ev = evidence_issues(gen, corpus)
    jd = judge(gen, corpus, model=model or "openai/gpt-5.6-luna")
    passed = (not ev) and (jd.get("ok") is not False) \
        and (jd.get("fabrication") is not True) and (jd.get("pii") is not True)
    return {"passed": passed, "evidence_issues": ev, "judge": jd}


# ---- 렌더 (완전히 새로운 폼 · 사용자 피드백 리포트) ----
def _esc(s) -> str:
    return html.escape(str(s or ""))


_SENT_CLASS = {"불만": "neg", "우려": "neg", "궁금": "ask", "제안": "sug", "호평": "pos", "만족": "pos"}


def _short_src(s: str) -> str:
    s = str(s or "")
    if "Reddit" in s:
        return "Reddit"
    if "Hacker" in s or "HN" in s:
        return "HN"
    if "긱뉴스" in s or "Geek" in s:
        return "긱뉴스"
    if "GPTers" in s or "오픈채팅" in s or "덕후" in s:
        return "오픈채팅"
    return s[:10]

_CSS = """
:root{
  --paper:#F7F5F1; --card:#FFFFFF; --ink:#1C1B19; --dim:#55514B; --muted:#928C83;
  --line:rgba(28,27,25,.12); --line-2:rgba(28,27,25,.06);
  --accent:#E0532E; --accent-ink:#B23D1C; --accent-soft:#FBE;
  --tint:#FBF2ED; --tint-line:rgba(224,83,46,.22);
  --neg:#C6412B; --ask:#2F6FB0; --sug:#B5731A; --pos:#2E8B57;
  --kr:"Pretendard Variable",Pretendard,-apple-system,system-ui,sans-serif;
}
*{box-sizing:border-box;margin:0;padding:0}
html{-webkit-text-size-adjust:100%}
body{background:#EDEAE4;color:var(--ink);font-family:var(--kr);line-height:1.6;
  -webkit-font-smoothing:antialiased;overflow-x:hidden}
.page{max-width:620px;margin:0 auto;min-height:100vh;background:
  radial-gradient(130% 40% at 100% -6%, rgba(224,83,46,.10), transparent 60%), var(--paper);
  box-shadow:0 0 0 1px var(--line-2),0 30px 80px -44px rgba(28,27,25,.42)}
a{color:inherit;text-decoration:none}

/* header */
.top{padding:34px 24px 22px;border-bottom:1px solid var(--line)}
.kick{font-size:11px;font-weight:700;letter-spacing:.22em;text-transform:uppercase;color:var(--accent)}
.kick .mk{display:inline-block;width:16px;height:2px;background:var(--accent);vertical-align:middle;margin-right:8px;border-radius:2px}
.title{margin-top:14px;font-size:clamp(26px,7vw,34px);line-height:1.18;font-weight:800;
  letter-spacing:-.022em;text-wrap:balance;color:#191816}
.meta{margin-top:14px;font-size:12px;letter-spacing:.01em;color:var(--muted)}
.mood{margin-top:16px;display:inline-flex;align-items:center;gap:9px;font-size:12.5px;color:var(--dim);
  background:var(--card);border:1px solid var(--line);border-radius:999px;padding:7px 14px}
.mood b{color:var(--accent-ink);font-weight:750}
.mood .rd{width:7px;height:7px;border-radius:50%;background:var(--accent)}

/* overview */
.overview{padding:22px 24px 6px;font-size:15.5px;line-height:1.74;color:var(--dim)}

/* section label */
.seclabel{padding:20px 24px 4px;display:flex;align-items:baseline;gap:12px}
.seclabel .t{font-size:11px;font-weight:700;letter-spacing:.2em;text-transform:uppercase;color:var(--muted)}
.seclabel .ln{height:1px;flex:1;background:var(--line)}
.seclabel .c{font-size:11px;color:var(--accent);letter-spacing:.06em}

/* feedback items */
.feed{padding:6px 16px 8px}
.fb{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:20px 18px;
  margin:12px 0;box-shadow:0 1px 2px rgba(28,27,25,.04),0 16px 30px -26px rgba(28,27,25,.4)}
.fb__row{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:11px}
.fb__no{font-size:12px;font-weight:800;color:var(--accent);letter-spacing:.04em;
  font-variant-numeric:tabular-nums;margin-right:2px}
.chip{font-size:10.5px;font-weight:700;letter-spacing:.04em;padding:4px 9px;border-radius:999px;
  border:1px solid var(--line)}
.chip--cat{color:var(--dim);background:var(--paper)}
.chip--src{color:var(--accent-ink);background:var(--tint);border-color:var(--tint-line);
  font-weight:750;letter-spacing:.02em}
.chip--sent{color:#fff}
.sent--neg{background:var(--neg)}.sent--ask{background:var(--ask)}
.sent--sug{background:var(--sug)}.sent--pos{background:var(--pos)}
.sent--x{background:var(--muted)}
.fb__issue{font-size:19px;line-height:1.34;font-weight:750;letter-spacing:-.012em;
  text-wrap:balance;color:#181715;margin-bottom:12px}
.fb__meta{display:flex;flex-wrap:wrap;gap:7px;margin-bottom:14px}
.fb__meta .mi{font-size:11.5px;color:var(--dim);background:var(--paper);
  border:1px solid var(--line);border-radius:8px;padding:4px 10px;display:inline-flex;
  align-items:center;gap:6px;font-variant-numeric:tabular-nums}
.fb__meta .mi i{font-style:normal;font-size:9.5px;font-weight:800;letter-spacing:.1em;
  text-transform:uppercase;color:var(--accent-ink)}
.fb__block{position:relative;padding-left:16px;margin-top:12px}
.fb__block::before{content:"";position:absolute;left:0;top:3px;bottom:3px;width:3px;border-radius:3px}
.fb__content::before{background:var(--line)}
.fb__lbl{display:block;font-size:10px;font-weight:800;letter-spacing:.16em;text-transform:uppercase;
  color:var(--muted);margin-bottom:5px}
.fb__block p{font-size:14.5px;line-height:1.66;color:var(--dim)}
.fb__comment{margin-top:13px;padding:13px 15px;background:var(--tint);border:1px solid var(--tint-line);
  border-radius:11px}
.fb__comment::before{display:none}
.fb__comment .fb__lbl{color:var(--accent-ink)}
.fb__comment p{color:#3f3a34}
.fb__src{margin-top:13px;display:flex;flex-wrap:wrap;align-items:center;gap:8px;
  padding-top:12px;border-top:1px solid var(--line-2)}
.fb__srclbl{font-size:9.5px;font-weight:800;letter-spacing:.16em;text-transform:uppercase;
  color:var(--muted)}
.fb__src a{font-size:12px;font-weight:700;color:var(--accent-ink);background:var(--tint);
  border:1px solid var(--tint-line);border-radius:8px;padding:4px 10px;display:inline-flex;
  align-items:center;gap:5px}
.fb__src a .ext{font-size:10px;opacity:.7}
.fb__src .noext{font-size:12px;color:var(--muted)}

/* footer */
.foot{padding:26px 24px 46px;border-top:1px solid var(--line);margin-top:10px;
  font-size:11.5px;letter-spacing:.02em;color:var(--muted);line-height:1.95}
.foot b{color:var(--dim);font-weight:700}
.foot__nav{display:flex;flex-wrap:wrap;gap:16px;margin-top:12px}
.foot a{color:var(--accent-ink);border-bottom:1px solid var(--tint-line)}

@media (prefers-reduced-motion:no-preference){
  .fb{opacity:0;transform:translateY(12px);animation:rise .6s cubic-bezier(.2,.7,.2,1) forwards}
  .fb:nth-child(1){animation-delay:.05s}.fb:nth-child(2){animation-delay:.11s}
  .fb:nth-child(3){animation-delay:.17s}.fb:nth-child(4){animation-delay:.23s}
  .fb:nth-child(5){animation-delay:.29s}.fb:nth-child(6){animation-delay:.35s}
  .fb:nth-child(7){animation-delay:.41s}
  @keyframes rise{to{opacity:1;transform:none}}
}
"""


def _src_label(source: str) -> str:
    return _short_src(source)


def render_feedback(gen: dict, date: str, refmap: dict | None = None,
                    in_subdir: bool = False) -> str:
    refmap = refmap or {}
    # 상대 링크(메인=docs/v2/uservoice.html, 날짜편=docs/v2/uservoice/<date>.html)
    if in_subdir:
        news_href, arch_href, today_href = "../../index.html", "index.html", "../uservoice.html"
    else:
        news_href, arch_href, today_href = "../index.html", "uservoice/index.html", None
    try:
        dobj = datetime.date.fromisoformat(date)
        wk = ["월", "화", "수", "목", "금", "토", "일"][dobj.weekday()]
        dl = f"{dobj.year}.{dobj.month:02d}.{dobj.day:02d} ({wk})"
    except Exception:
        dl = date

    cards = []
    for i, x in enumerate(gen.get("items", []), 1):
        sent = (x.get("sentiment") or "").strip()
        scls = _SENT_CLASS.get(sent, "x")
        cat = _esc(x.get("category", ""))
        metas = []
        for key, val in (("서비스", x.get("service")), ("모델", x.get("model")),
                         ("조건", x.get("conditions"))):
            v = (val or "").strip()
            if v:
                metas.append(f'<span class="mi"><i>{key}</i>{_esc(v)}</span>')
        meta_html = f'<div class="fb__meta">{"".join(metas)}</div>' if metas else ""
        srcs = [s for s in (x.get("sources") or []) if str(s).strip()][:2]
        src_html = "".join(f'<span class="chip chip--src">{_esc(_short_src(s))}</span>' for s in srcs)
        # 이슈별 출처 링크(refs → 원문 URL). 중복 URL 제거.
        links, seen_u = [], set()
        for rid in (x.get("refs") or []):
            ref = refmap.get(str(rid).strip())
            if ref and ref.get("url") and ref["url"] not in seen_u:
                seen_u.add(ref["url"])
                links.append(f'<a href="{_esc(ref["url"])}" target="_blank" rel="noopener">'
                             f'{_esc(_short_src(ref["source"]))} <span class="ext">↗</span></a>')
        if not links and any("오픈채팅" in s or "GPTers" in s for s in srcs):
            links.append('<span class="noext">오픈채팅 · 비공개 대화</span>')
        src_row = f'<div class="fb__src"><span class="fb__srclbl">출처</span>{"".join(links)}</div>' if links else ""
        cards.append(f"""
      <section class="fb">
        <div class="fb__row">
          <span class="fb__no">{i:02d}</span>
          {f'<span class="chip chip--cat">{cat}</span>' if cat else ''}
          {f'<span class="chip chip--sent sent--{scls}">{_esc(sent)}</span>' if sent else ''}
          {src_html}
        </div>
        <h2 class="fb__issue">{_esc(x.get("issue",""))}</h2>
        {meta_html}
        <div class="fb__block fb__content">
          <span class="fb__lbl">내용</span>
          <p>{_esc(x.get("content",""))}</p>
        </div>
        <div class="fb__block fb__comment">
          <span class="fb__lbl">해설</span>
          <p>{_esc(x.get("commentary",""))}</p>
        </div>
        {src_row}
      </section>""")
    cards_html = "\n".join(cards)
    n = len(gen.get("items", []))
    mood = _esc(gen.get("mood", ""))

    body = f"""
  <div class="page">
    <header class="top">
      <div class="kick"><span class="mk"></span>VAAX · 사용자 피드백</div>
      <h1 class="title">{_esc(gen.get("title",""))}</h1>
      <div class="meta">{dl} · 최근 24시간 · Reddit · Hacker News · 긱뉴스 · 오픈채팅 · 개인정보 제외</div>
      {f'<div class="mood"><span class="rd"></span>오늘의 정서 <b>{mood}</b></div>' if mood else ''}
    </header>
    <p class="overview">{_esc(gen.get("overview",""))}</p>
    <div class="seclabel"><span class="t">Voice of Users</span><span class="ln"></span><span class="c">피드백 {n}건</span></div>
    <main class="feed">
{cards_html}
    </main>
    <footer class="foot">
      <b>VAAX · 사용자 피드백</b><br>
      Reddit · Hacker News · 긱뉴스 · 오픈채팅의 하루치 실사용자 목소리를 이슈·내용·해설로 정리 · 개인정보 제외 · AI 자동 요약<br>
      <span class="foot__nav">
        <a href="{arch_href}">지난 피드백 아카이브 →</a>
        {f'<a href="{today_href}">오늘 편 →</a>' if today_href else ''}
        <a href="{news_href}">오늘의 AI 뉴스 →</a>
      </span>
    </footer>
  </div>"""
    return ('<!doctype html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            '<meta name="color-scheme" content="light">\n'
            '<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css">\n'
            f'<title>사용자 피드백 · VAAX — {_esc(date)}</title>\n'
            f'<style>{_CSS}</style>\n</head>\n<body>\n{body}\n</body>\n</html>\n')


# ---- 텔레그램 티저 ----
def build_caption(gen: dict, date: str) -> str:
    """공통 캡션(AI 보이스) — 룩앤필 통일(2026-08-18, briefer.caption)."""
    from briefer import caption
    bullets = [x.get("issue", "") for x in (gen.get("items") or [])[:3] if x.get("issue")]
    return caption.build("AI 보이스", date, bullets, FEEDBACK_URL,
                         headline=(gen.get("title") or "").strip(),
                         note="AI 실사용자 커뮤니티 대화 요약(개인정보 제외)")


# ---- 날짜별 아카이브 ----
def load_manifest(path: str) -> list:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa
        return []


def upsert_manifest(manifest: list, date: str, gen: dict) -> list:
    entry = {"date": date, "title": gen.get("title", ""), "mood": gen.get("mood", ""),
             "n": len(gen.get("items", []))}
    manifest = [m for m in manifest if m.get("date") != date] + [entry]
    manifest.sort(key=lambda m: m.get("date", ""), reverse=True)   # 최신순
    return manifest


_ARCH_CSS = """
:root{--paper:#F7F5F1;--card:#FFF;--ink:#1C1B19;--dim:#55514B;--muted:#928C83;
 --line:rgba(28,27,25,.12);--accent:#E0532E;--accent-ink:#B23D1C;--tint:#FBF2ED;
 --tint-line:rgba(224,83,46,.22);--kr:"Pretendard Variable",Pretendard,-apple-system,system-ui,sans-serif}
*{box-sizing:border-box;margin:0;padding:0}
body{background:#EDEAE4;color:var(--ink);font-family:var(--kr);line-height:1.6;-webkit-font-smoothing:antialiased}
.page{max-width:620px;margin:0 auto;min-height:100vh;background:var(--paper);
 box-shadow:0 0 0 1px rgba(28,27,25,.06),0 30px 80px -44px rgba(28,27,25,.42)}
a{color:inherit;text-decoration:none}
.top{padding:32px 24px 20px;border-bottom:1px solid var(--line)}
.kick{font-size:11px;font-weight:700;letter-spacing:.22em;text-transform:uppercase;color:var(--accent)}
.h{margin-top:12px;font-size:26px;font-weight:800;letter-spacing:-.02em}
.sub{margin-top:8px;font-size:12.5px;color:var(--muted)}
.list{padding:8px 16px 50px}
.row{display:block;background:var(--card);border:1px solid var(--line);border-radius:14px;
 padding:16px 18px;margin:10px 0}
.row .d{font-size:12px;font-weight:800;color:var(--accent-ink);letter-spacing:.04em}
.row .t{font-size:16.5px;font-weight:750;letter-spacing:-.01em;line-height:1.4;margin-top:5px}
.row .m{margin-top:8px;font-size:11.5px;color:var(--muted)}
.row .m b{color:var(--dim)}
.back{display:inline-block;margin-top:12px;font-size:12px;color:var(--accent-ink);
 border-bottom:1px solid var(--tint-line)}
.empty{text-align:center;color:var(--muted);padding:50px 20px}
"""


def render_archive_index(manifest: list) -> str:
    rows = []
    for m in manifest:
        d = m.get("date", "")
        try:
            dobj = datetime.date.fromisoformat(d)
            wk = ["월", "화", "수", "목", "금", "토", "일"][dobj.weekday()]
            dl = f"{dobj.year}.{dobj.month:02d}.{dobj.day:02d} ({wk})"
        except Exception:
            dl = d
        rows.append(
            f'<a class="row" href="{_esc(d)}.html"><span class="d">{_esc(dl)}</span>'
            f'<div class="t">{_esc(m.get("title",""))}</div>'
            f'<div class="m">피드백 {m.get("n","")}건'
            + (f' · 정서 <b>{_esc(m.get("mood"))}</b>' if m.get("mood") else '') + '</div></a>')
    body = (f'<div class="page"><header class="top">'
            f'<div class="kick">VAAX · 사용자 피드백 아카이브</div>'
            f'<h1 class="h">지난 피드백</h1>'
            f'<div class="sub">AI 실사용자 커뮤니티의 하루치 목소리 · 총 {len(manifest)}편</div>'
            f'<a class="back" href="../uservoice.html">← 오늘 편</a></header>'
            f'<div class="list">{"".join(rows) or "<div class=empty>아직 편이 없습니다.</div>"}</div></div>')
    return ('<!doctype html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css">\n'
            '<title>사용자 피드백 · 아카이브</title>\n'
            f'<style>{_ARCH_CSS}</style>\n</head>\n<body>\n{body}\n</body>\n</html>\n')


def main():
    ap = argparse.ArgumentParser(description="사용자 피드백 발행 (독립 폼)")
    ap.add_argument("--docs-root", default="docs")
    ap.add_argument("--dump-dir", default=None, help="기존 덤프 사용(없으면 에어 SSH 수집)")
    ap.add_argument("--since", default="1d", help="오픈채팅 수집 창(기본 24시간)")
    ap.add_argument("--date", default=datetime.date.today().strftime("%Y-%m-%d"))
    args = ap.parse_args()

    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "data", "uservoice")
    os.makedirs(data_dir, exist_ok=True)

    dump_dir = args.dump_dir
    if dump_dir is None:
        dump_dir = os.path.join(data_dir, "dumps")
        try:
            dump_from_air(dump_dir, args.since)
        except Exception as e:  # noqa  (에어 실패해도 웹 소스로 계속)
            print(f"[dump] 에어 실패(계속): {type(e).__name__}", file=sys.stderr)
    gpters = load_corpus(dump_dir)
    seen_path = os.path.join(data_dir, "seen.json")
    seen = load_seen(seen_path)
    tap_rooms, new_msg_hashes = load_jsonl_rooms(seen=seen)   # xbot tap 미니 방 + 메시지 지문 날짜간 중복제거
    corpus, active, new_urls, refmap = build_multi_corpus(gpters, seen=seen, extra_rooms=tap_rooms)
    print(f"[corpus] {len(corpus)}자 · 소스 {active} · 신규 {len(new_urls)}건(중복제거 후)",
          file=sys.stderr)
    if len(corpus) < 800:
        print(f"[error] 신규 소스 부족: {len(corpus)}자 — 발행 스킵", file=sys.stderr)
        sys.exit(2)

    gen = None
    feedback = ""
    for attempt in range(1, 4):
        gen = generate(corpus, feedback=feedback)
        ev = evaluate(gen, corpus)
        gen["_eval"] = ev
        if ev["passed"]:
            print(f"[eval] 통과 (attempt {attempt})", file=sys.stderr)
            break
        issues = (ev["evidence_issues"] or []) + (ev["judge"].get("issues") or [])
        feedback = " / ".join(str(i) for i in issues)[:600]
        print(f"[eval] 실패 (attempt {attempt}): {feedback}", file=sys.stderr)
    if not gen["_eval"]["passed"]:
        gen["_overview_dropped"] = gen.get("overview", "")
        heads = [x.get("issue", "") for x in gen.get("items", [])[:3] if x.get("issue")]
        if heads:
            gen["overview"] = "오늘 실사용자 사이에서는 " + ", ".join(heads) + " 등이 화두였습니다."
        print("[eval] ⚠ 미통과 → 보수 폴백(개관 재구성, 사람 검토)", file=sys.stderr)

    # 각 항목의 대표 원문 URL(refs→refmap) 해석 — 통합 카드가 아카이브 페이지가 아니라
    # 원문(Reddit/HN/긱뉴스)으로 바로 링크되게. refs 없는 항목(오픈채팅 등)은 "" → 폴백.
    for it in gen.get("items", []):
        purl = ""
        for rid in (it.get("refs") or []):
            ref = refmap.get(str(rid).strip())
            if ref and ref.get("url"):
                purl = ref["url"]
                break
        it["primary_url"] = purl

    payload = {"date": args.date, "corpus_len": len(corpus), "sources": active, "gen": gen}
    for path in (os.path.join(data_dir, f"{args.date}.json"), os.path.join(data_dir, "latest.json")):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    out_dir = os.path.join(args.docs_root, "v2")
    arch_dir = os.path.join(out_dir, "uservoice")
    os.makedirs(arch_dir, exist_ok=True)
    # 1) 메인(오늘) 페이지
    doc = render_feedback(gen, args.date, refmap=refmap, in_subdir=False)
    with open(os.path.join(out_dir, "uservoice.html"), "w", encoding="utf-8") as f:
        f.write(doc)
    # 2) 날짜별 아카이브 페이지 + 인덱스 + 매니페스트
    dated = render_feedback(gen, args.date, refmap=refmap, in_subdir=True)
    with open(os.path.join(arch_dir, f"{args.date}.html"), "w", encoding="utf-8") as f:
        f.write(dated)
    man_path = os.path.join(arch_dir, "manifest.json")
    manifest = upsert_manifest(load_manifest(man_path), args.date, gen)
    with open(man_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    with open(os.path.join(arch_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_archive_index(manifest))
    # 3) 발송용 요약 메시지
    with open(os.path.join(out_dir, "uservoice_message.txt"), "w", encoding="utf-8") as f:
        f.write(build_caption(gen, args.date))
    for u in new_urls:                          # 이번에 쓴 소스 URL 기록 → 내일 중복 제외
        seen[u] = args.date
    for h in new_msg_hashes:                    # 카톡 방 메시지 지문 기록 → 날짜간 중복 제외
        seen[h] = args.date
    save_seen(seen_path, seen, args.date)
    trim_jsonl(days=5)                          # tap JSONL 회전(최근 5일 유지)
    verdict = "PASS" if gen["_eval"]["passed"] else "DEGRADED"
    print(f"[feedback] '{gen['title']}' 모델={gen.get('_model')} eval={verdict} "
          f"→ {out_dir}/uservoice.html ({len(doc)} bytes) · 아카이브 {len(manifest)}편", file=sys.stderr)


if __name__ == "__main__":
    main()
