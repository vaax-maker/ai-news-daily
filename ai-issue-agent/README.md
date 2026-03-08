# 🤖 AI 이슈 모니터링 에이전트

매일 오전 7:30 (KST) 지정된 YouTube 채널들의 48시간 이내 영상을 수집하고,
NotebookLM으로 주제를 분석하여 한국어 인포그래픽을 Telegram으로 자동 발송하는 에이전트입니다.

## 📋 시스템 구조

```
[YouTube RSS 수집] → [트랜스크립트 추출] → [NotebookLM 분석]
                                                    ↓
[Telegram 자동 발송] ← [PNG 인포그래픽 생성] ← [주제 분류]
```

## 🚀 초기 설정 (최초 1회)

### 1. GitHub Secrets 설정

GitHub 저장소 Settings → Secrets and variables → Actions에서 아래 3개를 등록하세요:

| Secret 이름 | 설명 | 얻는 방법 |
|------------|------|----------|
| `TELEGRAM_BOT_TOKEN` | 텔레그램 봇 토큰 | [@BotFather](https://t.me/BotFather)에서 `/newbot` |
| `TELEGRAM_CHAT_ID` | 채팅방 ID | [@userinfobot](https://t.me/userinfobot)에서 확인 |
| `NOTEBOOKLM_COOKIES` | NotebookLM 인증 쿠키 | 아래 가이드 참고 |

### 2. NotebookLM 쿠키 추출 방법

NotebookLM은 Google 계정 로그인이 필요합니다. 쿠키를 한 번 추출하면 GitHub Actions에서 자동 사용됩니다.

#### 로컬에서 쿠키 추출:
```bash
# 1. notebooklm 스킬 폴더로 이동
cd ~/.agents/skills/notebooklm

# 2. 최초 브라우저 로그인 (브라우저가 열립니다)
python scripts/run.py auth_manager.py setup

# 3. 브라우저에서 Google 로그인 완료 후, 쿠키 파일 확인
cat data/browser_state/cookies.json

# 4. 쿠키를 Base64로 인코딩
cat data/browser_state/cookies.json | base64

# 5. 위 출력값을 GitHub Secret `NOTEBOOKLM_COOKIES` 에 등록
```

> ⚠️ 쿠키는 약 2-4주 후 만료됩니다. 만료 시 재추출 후 Secret을 업데이트하세요.

### 3. 로컬 테스트 (선택)
```bash
cd ai-issue-agent
pip install -r requirements.txt
playwright install chromium

# dry-run 테스트 (실제 발송 없음)
python scripts/run_agent.py --dry-run --no-telegram --hours 48
```

## ⏰ 자동 실행 스케줄

- **매일 오전 7:30 KST** (= UTC 22:30 전날)
- GitHub Actions → Actions 탭 → `AI 이슈 모니터링 에이전트` → `Run workflow`로 수동 실행 가능

## 📺 모니터링 채널 목록 (15개)

| 채널 | 언어 | 카테고리 |
|------|------|---------|
| @nateherk | EN | AI |
| @nicksaraev | EN | AI |
| @itssssss_Jack | EN | AI |
| @Chase-H-AI | EN | AI |
| @dante-labs | EN | AI |
| @innovation-catalyst | EN | AI |
| @jocoding | KO | AI/코딩 |
| @코딩알려주는누나 | KO | AI/코딩 |
| @TTimesTV | KO | 테크 |
| @ai_tusol | KO | AI |
| @mr.5pm | KO | AI |
| @배움의달인 | KO | AI |
| @평범한사업가 | KO | 비즈니스/AI |
| @maker-evan | KO | AI/메이커 |
| @OMG_electronics | KO | 테크 |

## 📊 출력 결과

1. **`01_common_topics.png`** — 🔥 공통 주제 인포그래픽 (여러 채널에서 다룬 AI 이슈)
2. **`02_unique_topics.png`** — 📌 개별 주제 인포그래픽 (채널별 단독 이슈)
3. **`report.md`** — 텍스트 리포트

결과물은 GitHub Actions Artifacts에도 7일간 보관됩니다.

## 🔧 트러블슈팅

| 문제 | 해결 |
|------|------|
| NotebookLM 쿠키 만료 | 로컬에서 `auth_manager.py setup` 재실행 후 Secret 업데이트 |
| 트랜스크립트 없는 영상 | 자동으로 제목+설명으로 대체 분석 |
| Playwright 오류 | `playwright install-deps chromium` 재실행 |
| Telegram 발송 실패 | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` Secret 확인 |
