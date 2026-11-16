"""Select compact, exact-match highlight phrases from published summaries."""

from __future__ import annotations

import re

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[가-힣A-Z0-9\"“‘])")
_TOKEN = re.compile(r"\S+")
_WORD = re.compile(r"[가-힣A-Za-z0-9][가-힣A-Za-z0-9.+-]*")
_SIGNAL = re.compile(
    r"\b(?:AI|AGI|LLM|GPT(?:-[\w.]+)?|ChatGPT|Claude|Gemini|Astra|Codex|"
    r"OpenAI|Anthropic|DeepSeek|NVIDIA|GPU|RAG)\b|"
    r"오픈AI|챗GPT|클로드|제미나이|아스트라|코덱스|앤스로픽|딥시크|엔비디아|"
    r"인공지능|생성형\s*AI|AI\s*에이전트|에이전트|로봇|반도체|"
    r"발표|공개|출시|지원|투자|경고|핵심|목표|"
    r"\d[\d,.]*(?:%|배|억|조|만|명|건|개|년|개월|월|일|시간|분|달러|원|GB|TB|B|M)",
    re.I,
)
_EDGE = " \t\r\n,.;:!?·—–-()[]{}\"'“”‘’"
_STOP = {"그리고", "하지만", "또한", "이는", "이번", "해당", "관련", "통해", "대한"}
_BAD_START = re.compile(r"^(?:그리고|하지만|또한|이는|이들은|그는|기사는|해당|관련)(?:은|는|이|가)?\b")
_BAD_END = re.compile(
    r"(?:은|는|이|가|을|를|의|와|과|도|만|에|서|로|으로|에게|하며|하고|했고|"
    r"이며|이고|이나|지만|때문에|따라|통해|대한|위한|등|및)$"
)
_GOOD_END = re.compile(
    r"(?:합니다|했습니다|됩니다|됐습니다|있습니다|없습니다|"
    r"했다|한다|된다|됐다|였다|이다|있다|없다|같다|"
    r"밝혔다|전망했다|촉구했다|평가했다|공개했다|발표했다|출시했다|"
    r"가동됐다|달성했다|공유했다|말했다|물었다|나왔다|이어졌다|"
    r"지적했다|전했다|요청했다|넘었다|좌우한다|해석한다)$"
)


def _norm(text: str) -> str:
    return re.sub(r"[^가-힣a-z0-9]+", "", text.casefold())


def _title_words(title: str) -> set[str]:
    return {
        word.casefold() for word in _WORD.findall(title or "")
        if len(word) >= 2 and word not in _STOP
    }


def _best_phrase(sentence: str, title_words: set[str], title_norm: str) -> tuple[int, str] | None:
    sentence = sentence.strip()
    tokens = list(_TOKEN.finditer(sentence))
    if not tokens:
        return None

    candidates: list[tuple[int, int, int, str]] = []
    for start in range(len(tokens)):
        for size in range(2, 10):
            end_index = start + size - 1
            if end_index >= len(tokens):
                break
            phrase = sentence[tokens[start].start():tokens[end_index].end()].strip(_EDGE)
            if not 10 <= len(phrase) <= 36:
                continue
            if len(re.findall(r"[가-힣A-Za-z]", phrase)) < 5:
                continue
            if _norm(phrase) == title_norm:
                continue
            words = {word.casefold() for word in _WORD.findall(phrase)}
            overlap = len(words & title_words)
            signals = len(_SIGNAL.findall(phrase))
            last_token = tokens[end_index].group().strip(_EDGE)
            complete_end = bool(_GOOD_END.search(last_token))
            if _BAD_END.search(last_token) or not complete_end:
                continue
            # 제목과 이어지는 핵심 사실을 우선하되, 조사·접속어에서 잘린 구문은 강하게
            # 감점한다. 완결된 서술어/핵심 명사로 끝나는 구문을 가장 높게 친다.
            score = overlap * 7 + signals * 5 + (3 if 3 <= size <= 5 else 0)
            score += 9
            score -= 5 if _BAD_START.search(phrase) else 0
            # 쉼표 바로 뒤나 문장 첫머리에서 시작하면 자연스러운 절일 가능성이 높다.
            if start == 0 or tokens[start - 1].group().rstrip().endswith((",", ";", ":")):
                score += 2
            candidates.append((score, -abs(size - 5), -start, phrase))

    if not candidates:
        short = sentence.strip(_EDGE)
        if 10 <= len(short) <= 36 and _norm(short) != title_norm:
            return 0, short
        return None
    score, _, _, phrase = max(candidates)
    return score, phrase


def select_highlights(summary: str, title: str = "") -> list[str]:
    """Return 1–2 exact substrings, each 10–36 chars, for restrained highlighting.

    Two phrases are allowed only when the summary has at least three sentences.
    Aggregate title lists joined by middle dots are intentionally excluded.
    """
    summary = str(summary or "").strip()
    if not summary or summary.count(" · ") >= 2:
        return []
    sentences = [part.strip() for part in _SENTENCE_SPLIT.split(summary) if part.strip()]
    title_words = _title_words(title)
    title_norm = _norm(title)
    ranked: list[tuple[int, int, str]] = []
    for index, sentence in enumerate(sentences):
        best = _best_phrase(sentence, title_words, title_norm)
        if best:
            score, phrase = best
            ranked.append((score + (2 if index == 0 else 0), index, phrase))
    if not ranked:
        return []

    limit = 1 if len(sentences) <= 2 else 2
    budget = max(24, int(len(summary) * 0.25))
    selected: list[tuple[int, str]] = []
    for _, index, phrase in sorted(ranked, key=lambda row: (-row[0], row[1])):
        if sum(len(item[1]) for item in selected) + len(phrase) > budget:
            continue
        selected.append((index, phrase))
        if len(selected) == limit:
            break
    return [phrase for _, phrase in sorted(selected)]
