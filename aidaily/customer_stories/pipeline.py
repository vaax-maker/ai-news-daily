#!/usr/bin/env python3
"""Customer Stories — AI 실사용자 커뮤니티 대화를 매일 정리.

컨셉: 뉴스/브리핑이 아니라, 실사용자가 현장에서 겪은 이슈·반응·요구를 '고객 사용기'으로
읽는다. 각 항목은 **이슈 → 내용 → 해설** 3단으로 제시한다. 디자인은 뉴스면과 무관한 독립 폼.

소스(2026-08-13 결정):
- **GPTers 덕후방만** — 맥북에어(fovea)에 SSH로 kakaocli 읽기(경합 없음).
  ※ 미니 직접 읽기는 xbot sync 데몬과 DB 잠금 경합으로 불안정 → 에어 경유.
  (방 ID·SSH 호스트 등 식별자는 gitignore된 customer_stories/_identifiers.py 에.)
- 홀딩(미니 전용, DB 경합으로 미읽음): 여러 방 — 에어 합류/미니 read 해결 시 활성화.

LLM = 공통 OpenRouter 클라이언트(OpenAI 기본). 정책 = 검증 게이트(근거 없는 창작/개인정보 방지).
프라이버시: 개인 이름/핸들/연락처/원문 인용 배제 — 주제·흐름·체감만 집약.

실행:
  python3 -m aidaily.customer_stories.pipeline --docs-root docs
  python3 -m aidaily.customer_stories.pipeline --docs-root docs --dump-dir DIR
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
from pathlib import Path

from aidaily import config
from aidaily.customer_stories import sources, checkpoint, knowledge_filter
from aidaily.integrations import openrouter

# ---- 소스 식별자(카톡 오픈채팅 ID·SSH 호스트) ----
# 개인정보라 gitignore된 로컬 customer_stories/_identifiers.py 에서 로드한다.
# 새 환경변수를 우선하며, 기존 이름은 배포 전환 기간에만 호환한다.
try:
    from aidaily.customer_stories import _identifiers as _ids
    AIR_HOST = _ids.AIR_HOST
    AIR_KAKAOCLI = _ids.AIR_KAKAOCLI
    GPTERS_CID = _ids.GPTERS_CID
except ImportError:
    AIR_HOST = os.environ.get("CUSTOMER_STORIES_AIR_HOST", "")
    AIR_KAKAOCLI = os.environ.get("CUSTOMER_STORIES_KAKAOCLI", "kakaocli")
    GPTERS_CID = os.environ.get("CUSTOMER_STORIES_GPTERS_CID", "")

# ---- LLM (shared OpenRouter integration) ----
MODELS = ["openai/gpt-6-luna", "google/gemini-3.1-flash-lite"]


def _ai_judge_enabled() -> bool:
    """Optional model-based review; deterministic information filtering always runs."""
    value = os.environ.get("CUSTOMER_STORIES_AI_JUDGE_ENABLED", "0").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _llm_complete(system: str, user: str, model: str, timeout: int = 120) -> str:
    return openrouter.complete(system, user, models=[model], timeout=min(timeout, 120), retries=2)


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
            print("[customer_stories] GPTers 덤프 0바이트 — 빈 코퍼스로 계속", file=sys.stderr)
            return ""
        data = json.loads(raw)
    except Exception as e:  # noqa
        print(f"[customer_stories] GPTers 덤프 로드 실패({type(e).__name__}) — 빈 코퍼스로 계속",
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


# Existing collector storage is an external compatibility boundary.
COMMUNITY_TAP_FILE = os.path.expanduser(os.environ.get(
    "CUSTOMER_STORIES_TAP_FILE", str(config.LEGACY_CUSTOMER_STORIES_TAP)
))


def load_jsonl_rooms(hours: int = 24, exclude_ids=(GPTERS_CID,),
                     per_room_chars: int = 6000, seen: dict | None = None):
    """Read legacy tap plus explicitly approved private community taps.

    Timestamp windows and publication content fingerprints apply across all paths.
    The approved extra source keeps its stable anonymous label; legacy labels remain.
    """
    import time as _t
    import hashlib
    import math
    from aidaily.customer_stories.community_tap import approved_tap_paths
    paths = [(COMMUNITY_TAP_FILE, None)]
    try:
        paths += approved_tap_paths()
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        print("[community] Optional source configuration invalid; legacy sources preserved", file=sys.stderr)
    cutoff = _t.time() - hours * 3600
    exclude = {str(x) for x in exclude_ids}
    seen = seen or {}
    rooms: dict[str, list] = {}
    new_hashes: list = []
    collected = set()
    for path, source in paths:
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                    ts = float(r.get("ts", 0))
                    if not math.isfinite(ts) or ts < cutoff:
                        continue
                    if source and str(r.get("chat_id", "")) != str(source["chat_id"]):
                        continue
                    if str(r.get("chat_id", "")) in exclude:
                        continue
                    txt = (r.get("text") or "").strip()
                    if not txt or txt.startswith("{") or _URLONLY.match(txt) or _NOISE.search(txt):
                        continue
                except (ValueError, TypeError, AttributeError):
                    continue
                norm = re.sub(r"\s+", " ", txt)[:280]
                h = "customer_story:" + hashlib.md5(norm.encode("utf-8")).hexdigest()[:16]
                if h in seen or h in collected:
                    continue
                collected.add(h)
                new_hashes.append(h)
                label = source["anonymous_label"] if source else _open_chat_name(
                    (r.get("chat_name") or str(r.get("chat_id", "")) or "오픈채팅").strip()[:40]
                )
                rooms.setdefault(label, []).append(norm)
    out = {}
    for label, lines in rooms.items():
        body = "\n".join(lines)
        out[label] = body[-per_room_chars:] if len(body) > per_room_chars else body
    return out, new_hashes


def trim_jsonl(days: int = 5) -> None:
    """tap JSONL을 최근 N일치로 유지(무한 증가·장기 보관 방지)."""
    import time as _t
    if not os.path.exists(COMMUNITY_TAP_FILE):
        return
    cutoff = _t.time() - days * 86400
    try:
        kept = []
        with open(COMMUNITY_TAP_FILE, encoding="utf-8") as f:
            for line in f:
                try:
                    if float(json.loads(line).get("ts", 0)) >= cutoff:
                        kept.append(line)
                except Exception:  # noqa
                    continue
        with open(COMMUNITY_TAP_FILE, "w", encoding="utf-8") as f:
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
    raw = sources.fetch_all()
    label = {"reddit": "Reddit (글로벌 AI 커뮤니티)", "hn": "Hacker News (개발자)",
             "geeknews": "긱뉴스 (국내 개발자)"}
    pfx = {"reddit": "R", "hn": "H", "geeknews": "G"}
    configured = {row["id"]: row for row in
                  sources.content_settings.sources("customer_stories", enabled_only=True)}
    ordered_caps = list(caps)
    known = {key for key, _ in ordered_caps}
    for key in raw:
        if key in known:
            continue
        row = configured.get(key, {})
        cap = int(row.get("limit") or 12) if row.get("limit_mode") == "fixed" else 12
        ordered_caps.append((key, max(1, cap)))
        label[key] = row.get("name") or (raw[key][0].get("source") if raw[key] else key)
        pfx[key] = f"S{len(pfx) - 2}-"
    blocks, active, new_urls, refmap = [], [], [], {}
    for key, cap in ordered_caps:
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
        gpters_label = _open_chat_name("GPTers 덕후방")
        active.append(gpters_label)
        blocks.append(f"===== [{gpters_label} (비공개 대화)] =====\n{gpters[:gpters_chars]}")
    for label, body in (extra_rooms or {}).items():            # xbot tap 방(미니 소스)
        if body.strip():
            public_label = _open_chat_name(label)
            active.append(public_label)
            blocks.append(f"===== [{public_label} (비공개 대화)] =====\n{body}")
    return "\n\n".join(blocks), active, new_urls, refmap


# ---- LLM 생성 (이슈/내용/해설) ----
SYSTEM = (
    "너는 VAAX의 신문 기자다. 독자에게 중요한 현장 이야깃거리를 찾고, 확인된 사실과 참여자의 주장, "
    "기자의 해석을 구분한다. 충분한 근거가 없는 사실·인과·발언은 만들지 않는다. "
    "AI 도구를 실제로 쓰는 사람들의 여러 커뮤니티"
    "(Reddit·Hacker News·긱뉴스·오픈채팅)에서 오늘 오간 글·대화를 읽고, 실사용자가 현장에서 겪은 "
    "이슈·반응·요구를 '고객 사용기'으로 정리한다. 뉴스가 아니라 실사용자의 목소리를 대변한다. "
    "편성은 **출처 우선**이다: 코퍼스의 각 출처를 독립된 섹션으로 보고, 출처마다 근거가 강한 실사용 "
    "주제를 최대 4개씩 선정한다. 같은 이슈가 여러 출처에 있어도 출처별 맥락과 반응이 다르면 각 출처의 "
    "항목으로 각각 설명한다. 한 항목에는 출처를 정확히 하나만 넣고, 다른 출처와 합쳐 쓰지 마라. "
    "근거가 4개 미만이면 억지로 채우지 말고 있는 만큼만 낸다. 소스 국적 매핑 — **해외=Reddit·"
    "Hacker News, 국내=긱뉴스·오픈채팅**. 특히 오픈채팅은 국내 실사용자가 도구를 직접 쓰며 겪은 현장 "
    "목소리(질문·꿀팁·불만·비교)라 가장 생생한 사용기이니 비중 있게 반영한다.\n"
    "단순 질문·막연한 우려·미래 희망·사용량 걱정·재미 반응만 있는 항목은 제외한다. "
    "질문은 원문에 실제 답변이 함께 있을 때만 채택한다. 기능·설정 방법·구체적 제약·관찰 결과처럼 "
    "읽고 새로운 지식이나 활용 정보를 얻을 수 있어야 한다. 답변이 없으면 만들지 않는다.\n"
    "원칙:\n"
    "(1) 대화에 실재하지 않는 것은 절대 쓰지 않는다. 수치·인용·주체·사건을 창작하지 마라. 대화에서 "
    "근거를 취하되 우리 문장으로 재작성한다.\n"
    "(2) 프라이버시 vs 출처: 코퍼스 구획의 출처 라벨을 sources에 그대로 적는다 — "
    "오픈채팅은 '오픈채팅 · 모임 N' 익명 라벨, 공개 웹은 Reddit/Hacker News/긱뉴스다. "
    "단, **방 안의 특정 개인**은 보호: 개인의 이름·아이디·@멘션·연락처·회사 등 신원 정보 금지, 개인 "
    "메시지를 그대로 인용하지 말고 여러 사람의 이야기를 '이슈·흐름·체감'으로 묶어라. 홍보/스팸/링크만 "
    "있는 메시지는 무시.\n"
    "(3) 각 항목은 이슈(issue)·내용(content)·해설(commentary) 3단. issue=실사용자가 부딪힌 문제/질문/"
    "반응을 압축한 제목. content=사용자들이 실제로 무엇을 말했는지(사실). commentary=그 피드백이 뜻하는 "
    "바·왜 중요한지(애널리스트 관점).\n"
    "각 항목은 정보 조각을 나열하지 말고, 원문에 있는 범위에서 사용 상황이나 목적 → 실제 행동·경험 → "
    "관찰된 결과 또는 제약이 어떻게 이어지는지 자연스러운 문장으로 설명한다. 원문에 없는 단계는 생략하고 "
    "추측해서 채우지 않는다. 비교가 있으면 비교 대상과 조건을 밝혀라. content는 관찰된 사실과 사용자 반응을 "
    "구별하고, commentary는 본문을 반복하지 말고 그 사례가 해당 조건에서 시사하는 바와 알려진 한계를 설명한다. "
    "근거 없는 원인·효과·기대·해결책이나 전체 사용자에 대한 일반화는 금지한다. 해석할 근거가 부족하면 "
    "그 사실을 짧게 밝히고 의미를 억지로 만들지 않는다.\n"
    "(4) category(사용성/비용/신뢰/기능요청/성능/만족 중)와 sentiment(불만/궁금/제안/호평/우려 중)를 "
    "대화 근거로 붙인다.\n"
    "(5) 각 항목에 **어떤 서비스·어떤 모델·어떤 사용조건**인지 메타를 붙인다: service(제품/서비스명, "
    "예 ChatGPT·Claude Code·Codex·Cursor·Midjourney·Slack), model(모델명, 예 GPT-5.6·Claude Sonnet·"
    "Gemini), conditions(사용조건: 요금제·플랫폼·환경, 예 유료 요금제·데스크톱 웹·API·무료 티어). "
    "**반드시 대화에 명시된 것만 쓰고, 언급이 없으면 빈 문자열(\"\")로 둔다. 추측·창작 절대 금지.**\n"
    "각 항목에는 비공개 검증용 _knowledge를 넣는다: kind는 answer/method/feature/constraint/observed_result/new_information, "
    "source_excerpt는 해당 refs 또는 해당 방 원문에 실제 있는 정보성 문구 그대로(질문 문장 제외, 개인 신원 제외). "
    "웹 항목은 근거 문구가 없으면 내지 않는다. 단톡방(오픈채팅)은 원문 연결 예외이므로 source_excerpt를 필수로 요구하지 않는다. "
    "단톡방도 kind는 반드시 지정하고, 질문만·단순 감상·기능 희망만 있는 항목은 제외한다. 이 검증 인용은 공개 본문에 표시하지 않는다.\n"
    "(6) 한국어. 이모지·해시태그 금지. 반드시 JSON만 출력(설명·코드펜스 금지)."
)


def _build_user(corpus: str, feedback: str = "") -> str:
    fb = ""
    if feedback:
        fb = ("\n\n[직전 시도 반려 사유 — 반드시 교정]\n" + feedback +
              "\n위 지적을 없애라. 대화에 '명확히' 있는 것만. 근거 약한 구체 표현은 빼고 좁혀 다시 작성.")
    schema = ('\n\n위는 오늘 AI 실사용자 커뮤니티 대화다. 아래 JSON만 출력하라:\n'
              '{\n'
              '  "title": "<오늘 고객 사용기을 관통하는 한 줄, 40자 이내>",\n'
              '  "mood": "<오늘의 전반 정서 한 단어, 예: 기대·불만·혼란·활기>",\n'
              '  "overview": "<2~3문장: 근거가 있는 공통점이나 차이와 그 맥락. 없으면 대표 사례와 관찰 범위; 제목 나열 금지>",\n'
              '  "items": [\n'
              '    {"issue":"<이슈 제목 22자 이내>",'
              '"category":"<사용성|비용|신뢰|기능요청|성능|만족>",'
              '"sentiment":"<불만|궁금|제안|호평|우려>",'
              '"service":"<나온 제품/서비스명, 없으면 \\"\\">",'
              '"model":"<나온 모델명, 없으면 \\"\\">",'
              '"conditions":"<사용조건: 요금제·플랫폼·환경, 근거 있을 때만, 없으면 \\"\\">",'
              '"sources":["<이 이슈가 나온 코퍼스 출처 라벨 그대로. 오픈채팅이면 '
              '\\"오픈채팅 · 모임 N\\", 웹이면 Reddit·Hacker News·긱뉴스. '
              '코퍼스 구획 라벨을 그대로 옮긴다>"],'
              '"refs":["<이 이슈 근거가 된 항목 표식, 예: R1·H3·G2 (여러 개 가능), 오픈채팅 근거면 비움>"],'
              '"_knowledge":{"kind":"<answer|method|feature|constraint|observed_result|new_information>","source_excerpt":"<해당 원문에 실제 있는 답변/기능/방법/제약/결과 문구 그대로>"},'
              '"content":"<원문에 있는 사용 상황·행동·관찰 결과나 제약을 연결한 사실 설명; 없는 단계는 생략>",'
              '"commentary":"<사실과 구분되는 해당 사례의 의미와 근거상 한계; 반복·추측·일반화 금지>"}\n'
              '  ]\n'
              '}\n'
              '각 코퍼스 출처마다 서로 다른 이슈를 최대 4개 선정한다. 각 항목의 sources는 해당 코퍼스 '
              '구획명 하나만 정확히 넣는다(여러 출처 결합 금지). service/model/conditions는 명시된 것만(없으면 ""). '
              'refs는 각 항목 앞의 대괄호 표식([R1] 등)에서 '
              '이 이슈의 근거가 된 것을 1~3개 정확히 옮겨 적는다(없는 표식 창작 금지).')
    return f"[오늘의 고객 사용기 소스]\n{corpus}{schema}{fb}"


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
        item_sources = [str(s).strip() for s in (x.get("sources") or []) if str(s).strip()]
        if len(item_sources) != 1:
            raise ValueError("item 출처는 정확히 하나여야 함")
    per_source: dict[str, int] = {}
    for x in it:
        source_name = str((x.get("sources") or [""])[0]).strip()
        per_source[source_name] = per_source.get(source_name, 0) + 1
    over_limit = [name for name, count in per_source.items() if count > 4]
    if over_limit:
        raise ValueError(f"출처별 주제 4개 초과: {', '.join(over_limit)}")


def generate(corpus: str, models: list[str] | None = None, feedback: str = "") -> dict:
    user = _build_user(corpus, feedback=feedback)
    # Route once through the common entry point. A quality failure is not
    # permission to try a different paid model or replace uncertain work.
    raw = openrouter.complete(SYSTEM, user, models=models or MODELS,
                              timeout=120, retries=2)
    d = _parse_json(raw)
    _validate(d)
    usage = openrouter.last_usage() or {}
    d["_knowledge_policy"] = 1
    d["_model"] = usage.get("model")
    d["_llm_usage"] = usage
    return d


# ---- 검증 게이트 ----
_NUM = re.compile(r'\d[\d,\.]*\d|\d')


def _nn(s: str) -> str:
    return (s or "").replace(",", "").replace(".", "")


def evidence_issues(gen: dict, corpus: str) -> list[str]:
    src = _nn(corpus)
    issues = []
    fields = [gen.get("title", ""), gen.get("overview", "")]
    for x in gen.get("items", []):
        if knowledge_filter.private_chat_exception(x):
            continue  # Private-chat literal source comparison is explicitly exempted.
        fields += [x.get("issue", ""), x.get("content", ""), x.get("commentary", "")]
    for f in fields:
        for n in _NUM.findall(f or ""):
            if len(_nn(n)) >= 2 and _nn(n) not in src:
                issues.append(f"수치 '{n}' 대화 미확인")
    return issues[:8]


_JUDGE_SYS = (
    "너는 고객 사용기 요약 사실검증관이다. 각 항목의 실제 원문 근거와 본문을 대조한다. "
    "생성된 항목 그 자체는 근거가 아니다. 원문에 답변이 없는 단순 질문, 막연한 우려·미래 희망·반응만 있는 "
    "항목은 실패(knowledge=false)다. 질문+실제 답변, 기능·방법·확인된 제약·구체적 관찰 결과·새 정보를 "
    "원문에서 얻을 수 있어야 한다. 답변·정보를 만들어 넣었으면 fabrication=true다. "
    "실제 제약을 겪은 경험이나 관찰한 결과는 허용하지만 감상만으로 지식을 만들지 마라. "
    "title/overview/해설의 편집 관점은 허용하되, 새 구체 사실·고유명사·수치·인용·사건을 만들거나 "
    "개인 신원을 노출하면 실패다. JSON {ok:bool,fabrication:bool,pii:bool,knowledge:bool,issues:[문자열]}만 출력한다."
    " evidence_mode=private_chat_exception은 사용자가 승인한 단톡방 원문 연결 예외다. "
    "이 항목은 source_evidence가 없거나 공개 원문을 연결할 수 없다는 이유로 실패시키지 않는다. "
    "원문 대조 불가를 fabrication으로 추정하지 말고, 질문만인지 단순 감상인지 또는 정보·답변·구체적인 경험인지 평가한다."
)


def judge(gen: dict, corpus: str, model: str = "openai/gpt-6-luna") -> dict:
    sample = corpus[:6000]
    it = json.dumps([{'issue':x.get('issue',''),'content':x.get('content',''),
        'evidence_mode':'private_chat_exception' if knowledge_filter.private_chat_exception(x) else 'source_bound',
        'source_evidence':knowledge_filter.classify_item(x,corpus).get('source_excerpt','')}
        for x in gen.get('items',[])],ensure_ascii=False)
    user = (f'대화 코퍼스(표본, 전체 아님):\n{sample}\n---\n'
            f'피드백 항목 — 근거 목록:\n{it}\n---\n'
            f'제목: {gen.get("title","")}\n개관: {gen.get("overview","")}\n---\n'
            '아래 JSON만: {"ok":true/false,"fabrication":true/false,"pii":true/false,"knowledge":true/false,"issues":["..."]}\n'
            'source_bound 항목은 source_evidence로 대조하라. private_chat_exception은 원문 대조를 요구하지 않는다. 생성된 항목을 원문 근거라고 주장하지 마라.')
    try:
        raw = _llm_complete(_JUDGE_SYS, user, model=model, timeout=120)
        s = re.sub(r'^```(?:json)?\s*', '', raw.strip())
        s = re.sub(r'\s*```$', '', s).strip()
        m = re.search(r'\{.*\}', s, re.S)
        return json.loads(m.group(0) if m else s)
    except openrouter.RoutingBlocked:
        raise
    except Exception as e:  # noqa
        return {"ok": None, "issues": [f"judge 실패: {e}"]}


def evaluate(gen: dict, corpus: str, model: str | None = None) -> dict:
    knowledge_decisions=[knowledge_filter.classify_item(x,corpus,require_explicit=gen.get("_knowledge_policy")==1) for x in gen.get("items",[])]
    knowledge_errors=[f"항목 {i}: {decision['reason']}" for i,decision in enumerate(knowledge_decisions) if not decision["keep"]]
    ev = evidence_issues(gen, corpus) + knowledge_errors
    source_bound=[x for x in gen.get('items',[]) if not knowledge_filter.private_chat_exception(x)]
    if not source_bound:
        return {'passed':bool(gen.get('items')) and not ev,'evidence_issues':ev,
                'judge':{'status':'not_required_private_chat_source_exception'},
                'source_verification':'exempt_private_chat','information_check':'rule_based'}
    # Exempt chat items must never be rejected again by a source-checking model.
    source_gen={**gen,'items':source_bound}
    if len(source_bound)!=len(gen.get('items',[])):
        source_gen['title']='웹 출처 활용 정보';source_gen['overview']=''
    jd = judge(source_gen, corpus, model=model or "openai/gpt-6-luna")
    if not isinstance(jd, dict) or any(type(jd.get(k)) is not bool for k in ("ok", "fabrication", "pii")):
        raise openrouter.RoutingBlocked("Quality evaluation incomplete; publication blocked")
    if gen.get("_knowledge_policy")==1 and type(jd.get("knowledge")) is not bool:
        raise openrouter.RoutingBlocked("Knowledge evaluation incomplete; publication blocked")
    passed = bool(gen.get("items")) and (not ev) and (jd.get("ok") is not False) \
        and (jd.get("fabrication") is not True) and (jd.get("pii") is not True) and (jd.get("knowledge") is not False)
    return {"passed": passed, "evidence_issues": ev, "judge": jd}


# ---- 렌더 (완전히 새로운 폼 · 고객 사용기 리포트) ----
def _esc(s) -> str:
    return html.escape(str(s or ""))


_SENT_CLASS = {"불만": "neg", "우려": "neg", "궁금": "ask", "제안": "sug", "호평": "pos", "만족": "pos"}

# 수집기의 chat_name이 비어 있던 기간에 저장된 요약을 위한 친화명이다. 방 ID는
# 내부 수집 식별자일 뿐 공개 화면에는 절대 표시하지 않는다.
_OPEN_CHAT_ROOM_NAMES = {
    "18478937851255981": "AI무료 강의 & 정보 공유",
    "18472466542857243": "김효율의 AI개발단",
    "18446637407407327": "코난쌤 오픈채팅방",
    "18310729609691586": "AI+스마트글래스",
    "18475047644735325": "ai the astra",
}
_OPEN_CHAT_ROOM_NUMBERS = {
    name.casefold(): index for index, name in enumerate(_OPEN_CHAT_ROOM_NAMES.values(), 1)
}
_OPEN_CHAT_GPT_COUNT = len(_OPEN_CHAT_ROOM_NUMBERS) + 1
_LONG_NUMERIC_ID = re.compile(r"(?<!\d)\d{6,}(?!\d)")


def _open_chat_name(s: str) -> str:
    """수집용 ID·비공개 방 이름을 안정적인 공개 익명 라벨로 바꾼다."""
    room = re.sub(r"^오픈채팅\s*[·•-]?\s*", "", str(s or "")).strip()
    room = re.sub(r"\s*\(비공개 대화\)\s*$", "", room).strip()
    known_number = re.fullmatch(r"모임\s+(\d+)", room)
    if known_number:
        return f"오픈채팅 · 모임 {known_number.group(1)}"
    if re.fullmatch(r"\d{6,}", room):
        room = _OPEN_CHAT_ROOM_NAMES.get(room, "")
    if "gpters" in room.casefold() or "덕후" in room:
        number = _OPEN_CHAT_GPT_COUNT
    else:
        number = _OPEN_CHAT_ROOM_NUMBERS.get(room.casefold(), 99)
    return f"오픈채팅 · 모임 {number}"


def public_source_label(source: str) -> str:
    """Normalize a source label for any public surface, including search results."""
    value = str(source or "").strip()
    known_room_names = {name.casefold() for name in _OPEN_CHAT_ROOM_NAMES.values()}
    if "Reddit" in value:
        return "Reddit"
    if "Hacker" in value or value == "HN":
        return "HN"
    if "긱뉴스" in value or "Geek" in value:
        return "긱뉴스"
    # Customer-story sources are limited to the three public web sources above
    # and private chats; treat every other label as private and anonymize it.
    return _open_chat_name(value)


def public_story_text(value) -> str:
    """Mask long numeric identifiers in public customer-story text."""
    return _LONG_NUMERIC_ID.sub("[비공개 ID]", str(value or ""))


def _short_src(s: str) -> str:
    return public_source_label(s)

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
.source-group{margin:22px 0 30px}
.source-group__head{display:flex;align-items:baseline;gap:9px;padding:0 4px 9px;border-bottom:1px solid var(--line)}
.source-group__name{font-size:13px;font-weight:800;color:var(--accent-ink);letter-spacing:-.01em}
.source-group__note{font-size:10.5px;color:var(--muted);font-weight:650}

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


def group_items_by_source(items: list[dict], limit_per_source: int = 4) -> list[tuple[str, list[dict]]]:
    """고객사용기 항목을 대표 출처별로 묶고, 각 묶음의 주요 주제를 제한한다.

    한 항목에 여러 출처가 있어도 첫 번째 유효 출처에만 넣어 같은 주제가 여러 묶음에
    반복되지 않게 한다. 오픈채팅은 개인 정보 없이 수집된 방 이름을 출처로 표시한다.
    """
    grouped: dict[str, list[dict]] = {}
    order: list[str] = []
    for item in items:
        raw_sources = [str(value).strip() for value in (item.get("sources") or []) if str(value).strip()]
        label = _src_label(raw_sources[0]) if raw_sources else "기타 커뮤니티"
        label = label or "기타 커뮤니티"
        if label not in grouped:
            grouped[label] = []
            order.append(label)
        if len(grouped[label]) < limit_per_source:
            grouped[label].append(item)
    return [(label, grouped[label]) for label in order if grouped[label]]


def render_customer_stories(gen: dict, date: str, refmap: dict | None = None,
                            in_subdir: bool = False) -> str:
    if gen.get('schema_version') == 2:
        from aidaily.customer_stories.story_render import render_story_report
        return render_story_report(gen, date, archive_href='index.html' if in_subdir else '../uservoice/index.html')
    refmap = refmap or {}
    public_slug = config.LEGACY_CUSTOMER_STORIES_PUBLIC_DIR
    if in_subdir:
        news_href, arch_href, today_href = "../../index.html", "index.html", f"../{public_slug}.html"
        community_href = "community.html"
    else:
        news_href, arch_href, today_href = "../index.html", f"{public_slug}/index.html", None
        community_href = f"{public_slug}/community.html"
    try:
        dobj = datetime.date.fromisoformat(date)
        wk = ["월", "화", "수", "목", "금", "토", "일"][dobj.weekday()]
        dl = f"{dobj.year}.{dobj.month:02d}.{dobj.day:02d} ({wk})"
    except Exception:
        dl = date

    cards = []
    for i, x in enumerate(gen.get("items", []), 1):
        sent = public_story_text(x.get("sentiment") or "").strip()
        scls = _SENT_CLASS.get(sent, "x")
        cat = _esc(public_story_text(x.get("category", "")))
        metas = []
        for key, val in (("서비스", x.get("service")), ("모델", x.get("model")),
                         ("조건", x.get("conditions"))):
            v = public_story_text(val).strip()
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
        if not links and str(x.get("primary_url") or "").strip():
            links.append(f'<a href="{_esc(x["primary_url"])}" target="_blank" rel="noopener">'
                         '관련 출처 <span class="ext">↗</span></a>')
        if not links and any("오픈채팅" in s or "GPTers" in s for s in srcs):
            room_names = list(dict.fromkeys(_short_src(s) for s in srcs
                                             if "오픈채팅" in s or "GPTers" in s))
            links.append(f'<span class="noext">{_esc(" · ".join(room_names))} · 비공개 대화</span>')
        src_row = f'<div class="fb__src"><span class="fb__srclbl">출처</span>{"".join(links)}</div>' if links else ""
        cards.append((x, f"""
      <section class="fb">
        <div class="fb__row">
          <span class="fb__no">{i:02d}</span>
          {f'<span class="chip chip--cat">{cat}</span>' if cat else ''}
          {f'<span class="chip chip--sent sent--{scls}">{_esc(sent)}</span>' if sent else ''}
          {src_html}
        </div>
        <h2 class="fb__issue">{_esc(public_story_text(x.get("issue","")))}</h2>
        {meta_html}
        <div class="fb__block fb__content">
          <span class="fb__lbl">내용</span>
          <p>{_esc(public_story_text(x.get("content","")))}</p>
        </div>
        <div class="fb__block fb__comment">
          <span class="fb__lbl">해설</span>
          <p>{_esc(public_story_text(x.get("commentary","")))}</p>
        </div>
        {src_row}
      </section>"""))
    grouped_cards = []
    html_by_item = {id(item): markup for item, markup in cards}
    for source_name, source_items in group_items_by_source(gen.get("items", []), limit_per_source=4):
        source_cards = []
        for source_index, item in enumerate(source_items, 1):
            markup = html_by_item.get(id(item), "")
            # 출처 안에서 주제 순번을 다시 매겨, 각 출처의 상위 4개라는 구조를 명확히 한다.
            markup = re.sub(r'(<span class="fb__no">)\d+(</span>)',
                            rf'\g<1>{source_index:02d}\g<2>', markup, count=1)
            source_cards.append(markup)
        grouped_cards.append(f"""
      <section class="source-group">
        <div class="source-group__head"><span class="source-group__name">{_esc(source_name)}</span><span class="source-group__note">주요 주제 {len(source_items)}개</span></div>
        {''.join(source_cards)}
      </section>""")
    cards_html = "\n".join(grouped_cards)
    n = len(gen.get("items", []))
    mood = _esc(public_story_text(gen.get("mood", "")))

    body = f"""
  <div class="page">
    <header class="top">
      <div class="kick"><span class="mk"></span>VAAX · 고객 사용기</div>
      <h1 class="title">{_esc(public_story_text(gen.get("title","")))}</h1>
      <div class="meta">{dl} · 최근 24시간 · Reddit · Hacker News · 긱뉴스 · 오픈채팅 · 개인정보 제외</div>
      {f'<div class="mood"><span class="rd"></span>오늘의 정서 <b>{mood}</b></div>' if mood else ''}
    </header>
    <p class="overview">{_esc(public_story_text(gen.get("overview","")))}</p>
    <div class="seclabel"><span class="t">Voice by Source</span><span class="ln"></span><span class="c">출처별 주요 주제 · 최대 4개</span></div>
    <main class="feed">
{cards_html}
    </main>
    <footer class="foot">
      <b>VAAX · 고객 사용기</b><br>
      Reddit · Hacker News · 긱뉴스 · 오픈채팅의 하루치 실사용자 목소리를 출처별 주요 주제로 정리 · 출처별 최대 4개 · 개인정보 제외 · AI 자동 요약<br>
      <span class="foot__nav">
        <a href="{arch_href}">지난 피드백 아카이브 →</a>
        <a href="{community_href}">공개 오픈채팅 주제 보기 →</a>
        {f'<a href="{today_href}">오늘 편 →</a>' if today_href else ''}
        <a href="{news_href}">오늘의 AI 뉴스 →</a>
      </span>
    </footer>
  </div>"""
    return ('<!doctype html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            '<meta name="color-scheme" content="light">\n'
            '<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css">\n'
            f'<title>고객 사용기 · VAAX — {_esc(date)}</title>\n'
            f'<style>{_CSS}</style>\n</head>\n<body>\n{body}\n</body>\n</html>\n')


# ---- 공개 오픈채팅 커뮤니티별 주제 페이지 -----------------------------------
def _open_chat_room(source: str) -> str:
    """공개 오픈채팅 출처만 판별해 사람이 읽을 방 이름을 돌려준다.

    고객사용기 원문 대화·참여자·메시지 ID는 이 단계에 들어오지 않는다. 이미 발행된
    주제 요약의 출처 라벨만 이용한다.
    """
    label = public_source_label(source)
    return label if label.startswith("오픈채팅 · 모임 ") else ""


def build_open_chat_community_topics(payloads: list[dict], limit_rooms: int = 8,
                                     limit_topics: int = 5) -> list[dict]:
    """발행된 고객사용기 요약에서 공개 오픈채팅별 반복 주제를 재구성한다.

    ``activity``는 원문 메시지 수가 아니라 최근 발행 요약에서 해당 방이 근거로
    포착된 횟수다. 원문 보관·노출 없이도 활발히 관찰되는 방을 우선할 수 있다.
    """
    rooms: dict[str, dict] = {}
    for payload in payloads:
        date = str(payload.get("date") or "")
        for item in (payload.get("gen") or {}).get("items") or []:
            seen_rooms = set()
            for source in item.get("sources") or []:
                room = _open_chat_room(source)
                if room:
                    seen_rooms.add(room)
            for room in seen_rooms:
                bucket = rooms.setdefault(room, {"name": room, "activity": 0,
                                                 "last_date": date, "topics": {}})
                bucket["activity"] += 1
                bucket["last_date"] = max(bucket["last_date"], date)
                issue = str(item.get("issue") or "").strip()
                if not issue:
                    continue
                key = re.sub(r"\s+", " ", issue).casefold()
                topic = bucket["topics"].setdefault(key, {
                    "title": issue,
                    "count": 0,
                    "date": date,
                    "summary": str(item.get("content") or "").strip(),
                    "takeaway": str(item.get("commentary") or "").strip(),
                    "category": str(item.get("category") or "").strip(),
                })
                topic["count"] += 1
                if date >= topic["date"]:
                    topic.update({
                        "date": date,
                        "summary": str(item.get("content") or "").strip(),
                        "takeaway": str(item.get("commentary") or "").strip(),
                        "category": str(item.get("category") or "").strip(),
                    })

    result = []
    for room in rooms.values():
        topics = sorted(room["topics"].values(),
                        key=lambda item: (item["count"], item["date"]), reverse=True)[:limit_topics]
        if topics:
            result.append({"name": room["name"], "activity": room["activity"],
                           "last_date": room["last_date"], "topics": topics})
    return sorted(result, key=lambda item: (item["activity"], item["last_date"]), reverse=True)[:limit_rooms]


_COMMUNITY_CSS = """
:root{--paper:#F7F5F1;--ink:#1C1B19;--dim:#55514B;--muted:#928C83;--line:rgba(28,27,25,.12);
 --accent:#E0532E;--accent-ink:#B23D1C;--tint:#FBF2ED;--card:#FFF;
 --kr:\"Pretendard Variable\",Pretendard,-apple-system,system-ui,sans-serif}
*{box-sizing:border-box}body{margin:0;background:#EDEAE4;color:var(--ink);font-family:var(--kr);line-height:1.6}
.page{max-width:760px;margin:0 auto;min-height:100vh;background:var(--paper);padding:32px 24px 54px}
.kick{font-size:11px;font-weight:800;letter-spacing:.16em;color:var(--accent);text-transform:uppercase}.title{font-size:30px;line-height:1.22;letter-spacing:-.035em;margin:10px 0 7px}.lead{font-size:14px;color:var(--dim);margin:0}.note{margin:16px 0 20px;padding:11px 13px;border:1px solid var(--line);border-radius:10px;background:var(--tint);font-size:12px;color:var(--dim)}
.tabs{display:flex;gap:7px;overflow-x:auto;padding:3px 0 13px;border-bottom:1px solid var(--line);scrollbar-width:none}.tab{flex:0 0 auto;border:1px solid var(--line);border-radius:999px;padding:7px 11px;background:#fff;color:var(--dim);font:700 12px var(--kr);cursor:pointer}.tab[aria-selected=\"true\"]{background:var(--ink);border-color:var(--ink);color:#fff}.panel{display:none;padding-top:18px}.panel.active{display:block}.panel-head{display:flex;align-items:baseline;gap:8px;margin-bottom:13px}.panel-head h2{font-size:19px;letter-spacing:-.02em;margin:0}.panel-head span{font-size:11px;color:var(--muted)}
.topic{background:var(--card);border:1px solid var(--line);border-radius:13px;padding:16px;margin:10px 0}.topic-top{display:flex;gap:7px;align-items:center}.badge{font-size:10.5px;font-weight:800;color:var(--accent-ink);background:var(--tint);border-radius:999px;padding:3px 7px}.date{margin-left:auto;font-size:11px;color:var(--muted)}.topic h3{font-size:17px;line-height:1.35;letter-spacing:-.02em;margin:8px 0}.summary{font-size:13px;color:var(--dim);margin:0}.takeaway{margin:11px 0 0;padding-top:10px;border-top:1px solid var(--line);font-size:12.5px;color:var(--ink)}.takeaway b{color:var(--accent-ink)}.empty{padding:48px 0;text-align:center;color:var(--muted)}.back{display:inline-block;margin-top:22px;color:var(--accent-ink);font-size:12px;font-weight:700;text-decoration:none;border-bottom:1px solid rgba(224,83,46,.28)}
"""


def render_open_chat_community_page(rooms: list[dict], latest_date: str) -> str:
    """공개 오픈채팅 주제 페이지. 탭 전환은 정적 HTML 안에서만 수행한다."""
    tabs, panels = [], []
    for index, room in enumerate(rooms):
        tab_id, panel_id = f"room-tab-{index}", f"room-panel-{index}"
        selected = "true" if index == 0 else "false"
        tabs.append(f'<button class="tab" id="{tab_id}" role="tab" aria-selected="{selected}" '
                    f'aria-controls="{panel_id}" data-target="{panel_id}">{_esc(public_story_text(room["name"]))}</button>')
        cards = []
        for topic in room["topics"]:
            category = f'<span class="badge">{_esc(public_story_text(topic["category"]))}</span>' if topic["category"] else ""
            cards.append(f'''<article class="topic"><div class="topic-top">{category}
              <span class="badge">발행 요약 {topic["count"]}회</span><span class="date">최근 { _esc(topic["date"]) }</span></div>
              <h3>{_esc(public_story_text(topic["title"]))}</h3><p class="summary">{_esc(public_story_text(topic["summary"]))}</p>
              <p class="takeaway"><b>읽을 포인트</b> · {_esc(public_story_text(topic["takeaway"]))}</p></article>''')
        panels.append(f'<section class="panel{" active" if index == 0 else ""}" id="{panel_id}" '
                      f'role="tabpanel" aria-labelledby="{tab_id}"><div class="panel-head"><h2>{_esc(public_story_text(room["name"]))}</h2>'
                      f'<span>최근 발행 요약 {room["activity"]}건 · 마지막 { _esc(room["last_date"]) }</span></div>{"".join(cards)}</section>')
    inner = (f'<div class="tabs" role="tablist">{"".join(tabs)}</div>{"".join(panels)}' if rooms
             else '<div class="empty">최근 발행 데이터에서 표시할 공개 오픈채팅 주제가 아직 없습니다.</div>')
    script = """<script>document.querySelectorAll('.tab').forEach(function(tab){tab.addEventListener('click',function(){document.querySelectorAll('.tab').forEach(function(x){x.setAttribute('aria-selected','false')});document.querySelectorAll('.panel').forEach(function(x){x.classList.remove('active')});tab.setAttribute('aria-selected','true');document.getElementById(tab.dataset.target).classList.add('active')})})</script>"""
    return f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css"><title>공개 오픈채팅 주제 · VAAX</title><style>{_COMMUNITY_CSS}</style></head><body><main class="page"><div class="kick">VAAX · 고객 사용기</div><h1 class="title">공개 오픈채팅의 오늘 주제</h1><p class="lead">대화가 활발히 포착된 공개 오픈채팅을 방별로 나누어, 반복된 질문과 사용 경험을 읽습니다.</p><p class="note">{_esc(latest_date)} 기준 최근 발행 요약을 집계했습니다. 원문 메시지·참여자·개인정보는 표시하지 않으며, 대화량은 원문 수가 아닌 발행 요약에 포착된 횟수입니다.</p>{inner}<a class="back" href="../uservoice.html">← 고객 사용기으로</a></main>{script}</body></html>'''


def write_open_chat_community_page(data_dir: str, docs_root: str) -> tuple[str, int]:
    """최근 고객사용기 데이터에서 공개 오픈채팅 탭 페이지를 결정론적으로 재생성한다."""
    payloads = []
    for name in sorted(os.listdir(data_dir)):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}\.json", name):
            continue
        try:
            with open(os.path.join(data_dir, name), encoding="utf-8") as f:
                payloads.append(json.load(f))
        except (OSError, ValueError):
            continue
    payloads = sorted(payloads, key=lambda item: str(item.get("date") or ""), reverse=True)[:14]
    rooms = build_open_chat_community_topics(payloads)
    latest_date = str(payloads[0].get("date") or "") if payloads else ""
    out_dir = os.path.join(docs_root, "v2", config.LEGACY_CUSTOMER_STORIES_PUBLIC_DIR)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "community.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_open_chat_community_page(rooms, latest_date))
    return path, len(rooms)


def rerender_latest_customer_story_page(data_dir: str, docs_root: str) -> str:
    """LLM·수집 없이 가장 최근 발행 payload를 다시 렌더한다.

    새 탐색 페이지 링크처럼 표현 계층만 바뀐 경우, 기존 원문 수집이나 요약을 다시
    돌리지 않고 당일 페이지와 날짜별 페이지를 함께 갱신한다.
    """
    latest_path = os.path.join(data_dir, "latest.json")
    with open(latest_path, encoding="utf-8") as f:
        payload = json.load(f)
    gen, date = payload.get("gen") or {}, str(payload.get("date") or "")
    if not gen or not date:
        raise ValueError("최근 고객사용기 payload가 비어 있습니다")
    out_dir = os.path.join(docs_root, "v2")
    arch_dir = os.path.join(out_dir, config.LEGACY_CUSTOMER_STORIES_PUBLIC_DIR)
    os.makedirs(arch_dir, exist_ok=True)
    public_slug = config.LEGACY_CUSTOMER_STORIES_PUBLIC_DIR
    with open(os.path.join(out_dir, f"{public_slug}.html"), "w", encoding="utf-8") as f:
        f.write(render_customer_stories(gen, date, in_subdir=False))
    with open(os.path.join(arch_dir, f"{date}.html"), "w", encoding="utf-8") as f:
        f.write(render_customer_stories(gen, date, in_subdir=True))
    return date


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
            f'<div class="kick">VAAX · 고객 사용기 아카이브</div>'
            f'<h1 class="h">지난 피드백</h1>'
            f'<div class="sub">AI 실사용자 커뮤니티의 하루치 목소리 · 총 {len(manifest)}편</div>'
            f'<a class="back" href="../{config.LEGACY_CUSTOMER_STORIES_PUBLIC_DIR}.html">← 오늘 편</a></header>'
            f'<div class="list">{"".join(rows) or "<div class=empty>아직 편이 없습니다.</div>"}</div></div>')
    return ('<!doctype html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css">\n'
            '<title>고객 사용기 · 아카이브</title>\n'
            f'<style>{_ARCH_CSS}</style>\n</head>\n<body>\n{body}\n</body>\n</html>\n')


def main():
    ap = argparse.ArgumentParser(description="고객 사용기 발행 (독립 폼)")
    ap.add_argument("--docs-root", default="docs")
    ap.add_argument("--dump-dir", default=None, help="기존 덤프 사용(없으면 에어 SSH 수집)")
    ap.add_argument("--since", default="1d", help="오픈채팅 수집 창(기본 24시간)")
    ap.add_argument("--date", default=datetime.date.today().strftime("%Y-%m-%d"))
    ap.add_argument("--render-community-only", action="store_true",
                    help="기존 고객사용기 발행 데이터만으로 공개 오픈채팅 탭 페이지를 재생성")
    ap.add_argument("--new-run", action="store_true", help="완료된 당일 실행만 새 수집으로 시작; 대기 실행은 재개")
    ap.add_argument("--editorial", action="store_true", help="누적 취재 기사 경로 실행")
    ap.add_argument("--reviewed-report", help="같은 동결 근거에서 데스크가 수정한 비공개 기사 JSON")
    ap.add_argument("--review-note", help="데스크 수정 이유(공개 본문에 포함하지 않음)")
    args = ap.parse_args()

    data_dir = str(config.DATA_ROOT / "customer_stories")
    os.makedirs(data_dir, exist_ok=True)
    if args.render_community_only:
        path, count = write_open_chat_community_page(data_dir, args.docs_root)
        latest_date = rerender_latest_customer_story_page(data_dir, args.docs_root)
        print(f"[customer_stories] 공개 오픈채팅 페이지 → {path} ({count}개 방) · "
              f"고객사용기 {latest_date} 링크 갱신", file=sys.stderr)
        return

    from aidaily.customer_stories import newsroom
    old_pending = checkpoint.unfinished_date(data_dir, args.date)
    legacy_path = Path(data_dir) / 'checkpoints' / (old_pending + '.json')
    legacy_state = json.loads(legacy_path.read_text()) if legacy_path.exists() else {}
    legacy_in_progress = legacy_state and legacy_state.get('stage') not in ('complete', 'review')
    if args.editorial or (newsroom.settings()['enabled'] and not legacy_in_progress):
        raise SystemExit(newsroom.run_until_settled(args))
    args.date = old_pending
    with checkpoint.locked(data_dir, args.date) as saved:
        if args.new_run:
            saved.restart()
        return _run(args, data_dir, saved)


class NoKnowledgeInformation(openrouter.RoutingBlocked):
    """A normal empty-content skip, distinct from unavailable AI evaluation."""


def _knowledge_gate_for_run(gen, corpus, saved=None):
    try:
        return apply_knowledge_gate(gen,corpus)
    except NoKnowledgeInformation:
        if saved is not None:
            saved.save(stage='complete',status='no_information',gen=gen)
        print('[customer_stories] 정보성 원문 근거 없음 — 발행 스킵; 원본 체크포인트 유지',file=sys.stderr)
        raise SystemExit(2)


def apply_knowledge_gate(gen, corpus):
    filtered=knowledge_filter.filter_report(gen,corpus,require_explicit=gen.get('_knowledge_policy')==1)
    if not filtered['items']:
        raise NoKnowledgeInformation('Customer knowledge gate: no source-supported information; publication blocked')
    if len(filtered['items'])!=len(gen.get('items',[])):
        heads=[item.get('issue','') for item in filtered['items'][:3] if item.get('issue')]
        filtered['title']='활용 정보 · '+(heads[0] if heads else '원문 확인 정보')
        # Removed items may have informed the generated overview. Do not infer
        # a shared theme or reconstruct one from a list of surviving titles.
        filtered['overview']='아래에서 출처별 사용 사례와 확인된 정보, 해설을 살펴봅니다.'
    return filtered


def _run(args, data_dir, saved):
    if saved.state.get("stage") == "complete":
        print("[customer_stories] completed daily run reused; --new-run starts fresh collection", file=sys.stderr)
        return
    seen_path = os.path.join(data_dir, "seen.json")
    seen = load_seen(seen_path)
    if not saved.state.get("inputs"):
        dump_dir = args.dump_dir
        if dump_dir is None:
            dump_dir = os.path.join(data_dir, "dumps")
            try:
                dump_from_air(dump_dir, args.since)
            except Exception as e:  # noqa  (에어 실패해도 웹 소스로 계속)
                print(f"[dump] 에어 실패(계속): {type(e).__name__}", file=sys.stderr)
        gpters = load_corpus(dump_dir)
        tap_rooms, new_msg_hashes = load_jsonl_rooms(seen=seen)   # xbot tap 미니 방 + 메시지 지문 날짜간 중복제거
        corpus, active, new_urls, refmap = build_multi_corpus(gpters, seen=seen, extra_rooms=tap_rooms)
        print(f"[corpus] {len(corpus)}자 · 소스 {active} · 신규 {len(new_urls)}건(중복제거 후)",
              file=sys.stderr)
        if len(corpus) < 800:
            skip_path = os.path.join(data_dir, f"skip-{args.date}.json")
            with open(skip_path, "w", encoding="utf-8") as skip_file:
                json.dump({"date": args.date, "reason": "신규 소스 부족"}, skip_file,
                          ensure_ascii=False, indent=2)
            print(f"[error] 신규 소스 부족: {len(corpus)}자 — 발행 스킵", file=sys.stderr)
            sys.exit(2)
        saved.save(stage="collected", date=args.date, attempt=1, feedback="",
                   inputs={"corpus":corpus,"active":active,"new_urls":new_urls,
                           "refmap":refmap,"new_msg_hashes":new_msg_hashes})
    frozen = saved.state["inputs"]
    corpus, active, new_urls, refmap, new_msg_hashes = (
        frozen[k] for k in ("corpus","active","new_urls","refmap","new_msg_hashes"))
    gen = saved.state.get("gen")
    if saved.state.get("stage") != "ready":
        feedback = saved.state.get("feedback", "")
        for attempt in range(saved.state.get("attempt", 1), 4):
            if gen is None:
                gen = generate(corpus, feedback=feedback)
                gen = _knowledge_gate_for_run(gen, corpus, saved=saved)
                saved.save(stage="evaluating", attempt=attempt, feedback=feedback, gen=gen)
            # Deterministic knowledge filtering above remains mandatory. The
            # separate model judge is opt-in while its false-rejection behavior
            # is under review; skipped review is recorded explicitly, never PASS.
            if not _ai_judge_enabled():
                gen["_eval"] = {
                    "passed": False,
                    "status": "not_run",
                    "reason": "ai_judge_disabled_by_default",
                    "judge": {"status": "disabled_by_config"},
                    "evidence_issues": [],
                }
                saved.save(stage="ready", gen=gen)
                print("[eval] AI 검수 미실행(설정으로 비활성화); 결정적 정보성 필터 통과", file=sys.stderr)
                break
            # Same frozen candidate/input recreates the same content-derived LLM ID.
            ev = evaluate(gen, corpus)
            ev["status"] = "passed" if ev.get("passed") else "failed"
            gen["_eval"] = ev
            if ev["passed"]:
                saved.save(stage="ready", gen=gen)
                print(f"[eval] 통과 (attempt {attempt})", file=sys.stderr)
                break
            if gen.get('_knowledge_policy')==1:
                saved.save(stage='review',gen=gen,review_reason='knowledge_evaluation_failed')
                break  # Preserve the failed candidate; never regenerate to bypass review.
            issues = (ev["evidence_issues"] or []) + (ev["judge"].get("issues") or [])
            feedback = " / ".join(str(i) for i in issues)[:600]
            print(f"[eval] 실패 (attempt {attempt}): {feedback}", file=sys.stderr)
            if attempt < 3:
                gen = None
                saved.save(stage="collected", attempt=attempt+1, feedback=feedback, gen=None)
            else:
                saved.save(stage="review" if gen.get("_knowledge_policy")==1 else "ready", gen=gen)
    gen = _knowledge_gate_for_run(gen, corpus, saved=saved)
    ai_judge_skipped = gen.get("_eval", {}).get("status") == "not_run"
    if gen.get('_knowledge_policy')==1 and not gen['_eval']['passed'] and not ai_judge_skipped:
        saved.save(stage='review',gen=gen,review_reason='knowledge_evaluation_failed')
        print('[customer_stories] 정보성·사실 검수 미통과 — 원본 후보 보존, 발행 스킵',file=sys.stderr)
        raise SystemExit(2)
    if not gen["_eval"]["passed"] and not ai_judge_skipped:
        gen["_overview_dropped"] = gen.get("overview", "")
        gen["overview"] = "아래에서 출처별 사용 사례와 확인된 정보, 해설을 살펴봅니다."
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
    # Public URLs stay stable while internal code and data use canonical terminology.
    arch_dir = os.path.join(out_dir, config.LEGACY_CUSTOMER_STORIES_PUBLIC_DIR)
    os.makedirs(arch_dir, exist_ok=True)
    # 1) 메인(오늘) 페이지
    doc = render_customer_stories(gen, args.date, refmap=refmap, in_subdir=False)
    public_slug = config.LEGACY_CUSTOMER_STORIES_PUBLIC_DIR
    with open(os.path.join(out_dir, f"{public_slug}.html"), "w", encoding="utf-8") as f:
        f.write(doc)
    # 2) 날짜별 아카이브 페이지 + 인덱스 + 매니페스트
    dated = render_customer_stories(gen, args.date, refmap=refmap, in_subdir=True)
    with open(os.path.join(arch_dir, f"{args.date}.html"), "w", encoding="utf-8") as f:
        f.write(dated)
    man_path = os.path.join(arch_dir, "manifest.json")
    manifest = upsert_manifest(load_manifest(man_path), args.date, gen)
    with open(man_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    with open(os.path.join(arch_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_archive_index(manifest))
    community_path, community_count = write_open_chat_community_page(data_dir, args.docs_root)
    for u in new_urls:                          # 이번에 쓴 소스 URL 기록 → 내일 중복 제외
        seen[u] = args.date
    for h in new_msg_hashes:                    # 카톡 방 메시지 지문 기록 → 날짜간 중복 제외
        seen[h] = args.date
    save_seen(seen_path, seen, args.date)
    trim_jsonl(days=5)                          # tap JSONL 회전(최근 5일 유지)
    saved.save(stage="complete", gen=gen)
    verdict = "AI_JUDGE_NOT_RUN" if ai_judge_skipped else (
        "PASS" if gen["_eval"]["passed"] else "DEGRADED")
    print(f"[customer_stories] '{gen['title']}' 모델={gen.get('_model')} eval={verdict} "
          f"→ {out_dir}/{public_slug}.html ({len(doc)} bytes) · 아카이브 {len(manifest)}편 "
          f"· 공개 오픈채팅 {community_count}개 방({community_path})", file=sys.stderr)


if __name__ == "__main__":
    main()
