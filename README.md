# ai-news-daily

## 개요
- 애플 AI 관련 뉴스 5줄 요약 및 업로드 자동화 GitHub Actions 및 순수 파이썬 코드로 작동
- 중앙일보 애플 뉴스, 맥루머스를 통한 정기적인 애플 뉴스 확인
- LangChain을 사용한 뉴스 요약 및 내용 요약 생성

## 최근 조치 요약
- Gemini 요약 호출이 무료 할당량을 초과했을 때 오류로 종료되지 않고, 안내된 대기 시간을 기다린 뒤 다시 시도하도록 재시도 로직을 추가했습니다.
- Gemini 호출이 반복적으로 실패하면 Grok API로 자동 전환해 요약을 이어가도록 백업 경로를 추가했습니다.

## 환경 변수 설정 (요약 실패 시 Grok 백업용)
- `GEMINI_API_KEY`: 기존 Gemini 호출에 사용되는 키.
- `GROK_API_KEY`: Grok 백업 호출에 필요한 API 키. **필수**이며, 아래처럼 환경 변수로 설정해야 합니다.
- `GROK_MODEL`(선택): Grok 호출에 사용할 모델 ID. 기본값은 `llama-3.3-70b-versatile`.

### 키 저장 위치
- **로컬 실행**: 셸에서 `export GROK_API_KEY="발급받은_키"` 로 지정하거나, `.env` 파일에 `GROK_API_KEY=발급받은_키` 형식으로 저장한 뒤 `source .env` 로 불러옵니다.
- **GitHub Actions**: 저장소 **Settings → Secrets and variables → Actions → New repository secret** 에 `GROK_API_KEY` 이름으로 등록합니다. 워크플로가 자동으로 읽어 사용합니다.
