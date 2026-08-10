# VAAX AI 뉴스 (ai-news-daily v3)

## 개요
aiofmodu.com(모두의AI) daily-news Firestore 문서를 소스로, 매 평일 오전
"오늘의 AI 뉴스" 모바일 웹페이지 + 텔레그램 발송을 자동 생성하는 파이프라인.
개조식 요약, 세로 인포그래픽 커버, 검색 가능한 아카이브로 구성된다.

## 구조

```
briefer/
  source.py       # Firestore fetch (fetch_today/fetch_all) + 결정적 파싱(parse_stories)
  outline.py      # OpenRouter(anthropic/claude-sonnet-4-6)로 소스 문장 → 개조식 bullet 변환
  infographic.py  # 맥미니 nlm-infographic API 호출 → 세로 인포그래픽 PNG 생성
  render.py       # 오늘의 뉴스 HTML(index.html) + 아카이브/검색 HTML(archive.html) 렌더
  notify.py       # 텔레그램 sendPhoto(인포그래픽+캡션) 발송
  build.py         # 오케스트레이터 (python3 -m briefer.build)
deploy/
  run_daily.sh              # 평일 09:00 KST 발행 러너 (fetch→outline→render→push→telegram)
  com.vaax.brief.plist      # launchd 잡 정의 (아직 미설치 — 설치는 별도 승인 필요)
docs/                        # 빌드 산출물 (GitHub Pages 루트)
  index.html                # 오늘의 뉴스
  archive.html               # 아카이브 · 검색
  archive/index.json         # 아카이브 데이터(전체 뉴스, 최신순)
  infographic.png            # 오늘의 인포그래픽
```

## 실행 방법

### 로컬 빌드 (인포그래픽 API 호출 포함, 느림 ~수 분)
```bash
export OPENROUTER_API_KEY=$(docker exec hermes-xbot printenv OPENROUTER_API_KEY)
/opt/homebrew/bin/python3 -m briefer.build --docs-root docs
```

### 드라이런 (기존 PNG 재사용 — 느린 인포그래픽 API 스킵)
```bash
export OPENROUTER_API_KEY=$(docker exec hermes-xbot printenv OPENROUTER_API_KEY)
/opt/homebrew/bin/python3 -m briefer.build --docs-root docs --skip-infographic /path/to/existing.png
```

### 운영 배포 (평일 자동 발행)
`deploy/run_daily.sh` 가 pull → build → commit/push(main) → 텔레그램 발송까지 수행한다.
`deploy/com.vaax.brief.plist` 를 `~/Library/LaunchAgents/` 에 설치하면 평일 09:00 KST 자동 실행
(현재는 파일만 작성되어 있고 로드되지 않은 상태).

## 의존성
표준 라이브러리(`urllib`, `json`, `re`, `html` 등)만 사용한다. `requirements.txt` 참고 —
bs4/requests 등은 불필요(파싱은 정규식 기반).

## 자격증명
- `OPENROUTER_API_KEY` — 환경변수 (운영은 `docker exec hermes-xbot printenv OPENROUTER_API_KEY`로 획득)
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` — 환경변수 또는 `~/nlm-infographic/deploy/.tg-creds.json`
- nlm-infographic API 토큰 — `~/nlm-infographic/.api_token` (파일에서 직접 로드, 하드코딩 없음)

## 브랜드/디자인
포인트 컬러 = 진한 연두 `--gold:#4C7E00; --gold-br:#7CC01A;`(내부 변수명은 레거시).
라이트 테마, 이모지 미사용, 박스 좌측 액센트바/그림자 없음, 개조식(bullet) 표기.
