# AI Daily

AI Daily는 세 가지 콘텐츠 제품을 수집·요약하고, 하나의 사이트로 발행한 뒤 Telegram으로
알리는 자동화 프로젝트다. 실행 작업본은 mini1의 `~/aidaily` (`main`)이며,
프로젝트 문서 정본은 `abot-projects path _aidaily`로 조회하는 중앙 저장소다.

## 프로젝트 구조

```text
aidaily/
  ai_news/             AI News 수집·요약·렌더링
  customer_stories/    Customer Stories 수집·검증·렌더링
  youtube_summaries/   YouTube Summaries 수집·분석·리포트 생성
  integrations/        OpenRouter·Firestore·YouTube·이미지·HTTP API 클라이언트
  publishing/          검색 인덱스·Git·통합 사이트 발행
  notifications/       캡션 작성·Telegram 전송
deploy/
  run_pipeline.sh              일간 생성 → 발행 → 알림 정본
  run_youtube_summaries.sh     YouTube Summaries 정본
  run_publish_9am.sh           기존 launchd용 호환 진입점
docs/                   웹 발행 산출물
data/                   런타임 상태와 로그
```

영어 코드명은 `ai_news`, `customer_stories`, `youtube_summaries`, `integrations`,
`publishing`, `notifications`만 사용한다.

## 운영 흐름

매일 06:00의 `com.aidaily.prepare`는 `deploy/run_pipeline.sh --prepare-only`로 뉴스·사용기를 사전 생성한다.
매일 07:30의 `com.aidaily.publish`는 `deploy/run_pipeline.sh`를 실행해 완료된 생성을 재사용하고 게시·검증 후 독자 알림을 보낸다.
평일 09:00에는 `com.aidaily.aiofmodu-refresh`가 AI of Modu 변경을 확인해 웹을 갱신한다. 기존 10분 간격·10:30 종료 정책과 추가 독자 알림 생략을 유지한다.

1. `ai_news`와 `customer_stories`가 콘텐츠를 생성한다.
2. `publishing`이 검색 인덱스를 재생성하고 두 GitHub Pages 저장소를 발행한다.
3. 발행 성공 후에만 `notifications`가 Telegram 알림을 보낸다.

매일 05:30의 YouTube 스케줄은 `com.aidaily.youtube-summaries`가
`deploy/run_youtube_summaries.sh`를 실행한다. LLM 분석은 공통 OpenRouter 클라이언트를
사용하며 Claude CLI나 유료 구독에 의존하지 않는다.

## API와 자격증명

외부 호출은 `aidaily.integrations` 아래에서 관리한다. 텍스트 LLM은
`aidaily.integrations.openrouter`, YouTube는 `aidaily.integrations.youtube`, 이미지 생성은
`aidaily.integrations.infographic`, Firestore는 `aidaily.integrations.firestore`를 사용한다.

`OPENROUTER_API_KEY`는 환경변수, `AIDAILY_ENV_FILE`, `~/.config/aidaily/.env` 순서로 읽는다.
실제 키와 개인 식별자는 커밋하지 않는다. 서비스 주소는 환경변수로 재정의할 수 있다.

## 텍스트 추론과 재개

기존 `aidaily.integrations.openrouter.complete` / `complete_json` 호출은 설치된
`~/abot-inference/inference_client.py`와 공통 서비스 레지스트리를 통해 Qwen을 먼저
사용한다. 로컬 성공에는 OpenRouter 키가 필요하지 않다. 입력을 자르지 않으며,
16,000자 또는 로컬 출력 한도를 넘는 요청은 기존 OpenRouter 모델 경로를 사용한다.
기존 키 조회 순서와 `AI-Daily` 프로젝트 헤더는 유지한다.

동일한 입력·모델 설정은 안정적인 요청 ID로 재개하고 성공 결과를 재사용한다.
필요하면 호환 가능한 선택 인자 `request_id=`로 업무 ID를 지정할 수 있다.
기록은 `data/llm`에 저장하며 `AIDAILY_LLM_STATE_DIR`로 격리할 수 있다. 기록에는
비공개 응답이 포함될 수 있으므로 공개 docs나 발행 저장소에 넣지 않는다.
`last_usage()`는 실제 provider/model, 토큰 사용량, 비용과 지연 정보를 제공한다.

busy·제출/조회 불확실 상태는 `CompletionPending`으로 남고 생성/발행을 중단한다.
동일 요청을 다시 실행하면 공통 클라이언트가 이어서 처리한다. 인증·TLS 오류는
유료 대체 조건이 아니다. 로컬의 확정된 미접속/미준비/지원 한도 초과 또는 확정된
엔진 실패만 기존 외부 경로를 사용할 수 있다. 외부 전송 전에 영속 기록을 저장하고,
타임아웃이나 결과 불명은 자동 재전송하지 않는다. `retries` 인자는 호환을 위해
유지하되 불확실한 유료 POST 재시도는 하지 않는다. 명시적인 404 모델 거절만 다음
설정 모델을 시도한다. 불확실한 외부 기록은 운영자가 제공자 결과를 확인해 조정해야
하며, 삭제해서 다시 보내지 않는다.

로컬 JSON의 최종 배열 닫힘 오류만 최대 두 괄호를 보정한다. 문자열·사실·키·값이나
잘린 응답은 복원하지 않는다. 기존 콘텐츠 품질 검증은 그대로 적용한다.

## 호환 경계

공개 링크와 외부 저장소 데이터는 기존 이용자를 깨뜨리지 않도록 일부 이름을 유지한다.
`/v2/uservoice`, `daybreak-config.json`, `daybreak-telegram-queue.json`, 외부 검증기가 읽는
`morning-digest` 커밋 접두사는 호환 계약일 뿐 내부 프로젝트 명칭이 아니다.

## 검증

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 python3 -m compileall -q aidaily deploy
bash -n deploy/*.sh
```

네트워크·LLM·Telegram·Git push가 발생하는 라이브 발행은 위 로컬 검증과 별개다.
# 발행 중단 복구 (2026-10-20)

정기 실행은 `deploy/run_pipeline.sh`를 사용한다. 실행 저장소를 자동 pull하거나
생성 파일을 실행 저장소에서 커밋하지 않는다. 공개 산출물만 임시 클론에 복사해
게시하므로 기존 미추적 파일·staged 수정·작업 중 코드를 보존한다.

- 단계 상태: `data/publishing/daily_runs/YYYY-MM-DD.json`
- 복구: 같은 명령을 다시 실행하면 파일 해시가 일치하는 완료 단계를 재사용한다.
- 수동으로 오늘 생성까지 끝났다면 `deploy/run_pipeline.sh --adopt-generated`로 재개한다.
- 게시 후 오늘 날짜·기사의 실제 HTTPS 반영을 확인한 뒤 안내를 발송한다.
- 안내 영수증이 `sending`/`uncertain`이면 자동 재전송하지 않고 실제 발송 결과를 확인한다.
- 실패는 단계 상태와 로그에 기록한다. 관리자 Telegram은 전용 환경변수
  `AIDAILY_ADMIN_TELEGRAM_TOKEN`/`AIDAILY_ADMIN_TELEGRAM_CHAT_ID` 또는 검증된 개인
  수신처 설정 `~/.config/aidaily/admin-notifications.json`으로만 보낸다.
  독자용 일간 안내로 실패 메시지를 대신 보내지 않는다.


## 관리자·방문 통계·스크랩 (2026-10-20)

기존 공용 웹의 `/aidaily/` 관리자에서 방문 통계·스크랩·소식지 읽기를 제공한다.
통계는 KST 일간/월요일 시작 주간/월간, 전체·페이지별 PV다. 공개 수집 서버는
2026-10-20 10:16:35 KST에 활성화했고 공개 HTML 배포도 완료했다. 이전 방문은
소급하지 않는다. 관리자 읽기 화면에서 기사 우측 체크로 저장한 항목은 누적
스크랩 목록에서 동일 UID 기사로 이동한다. 데이터는 비공개 SQLite에 보관한다.

수집 주소는 `services.aidaily-engagement`에서 조회한다. 공개 픽셀은 쓰기 전용이며
관리자 API는 기존 인증을 유지한다. Tailscale 내부 IP로 해석되는 접속과 브라우저
차단은 집계에서 빠질 수 있다. Chrome 로컬 네트워크 권한창을 요청하지 않도록
수집 iframe의 로컬 접근 권한을 제한했다.

현재 배포·증거·복구 주의사항과 후속 확인은
[세션 인계](operations/SESSION-HANDOFF-20261020.md)를 먼저 읽는다.
이 내부 인계 문서를 공개 발행 산출물에 추가하지 않는다.

## 정부과제 일일 업데이트

`python3 -m aidaily.ai_news.gov --date YYYY-MM-DD`가 기업마당·과기정통부·나라장터를
mini1에서 직접 HTTPS로 수집한다. 기존 일일 준비/발행의 선택 단계로 실행하며,
진행 중인 요청·출처별 성공/실패·날짜별 결과는 `data/ai_news/gov/`에 보존한다.
API 키는 환경변수 또는 mini1 비공개 `~/.config/aidaily/gov-api.json`에서 읽으며
로그·Git·공개 페이지에 넣지 않는다. GitHub 수집 작업은 정기 경로에서 사용하지 않는다.

기술 메인 하단에는 `일시 | 출처 | 기관명 | 제목` 표로 표시하고, 제목은 공식 원문으로
연결한다. 시간은 출처가 실제 제공한 정밀도로 표시하며 날짜만 있는 자료에 임의의
시각을 붙이지 않는다. 좁은 화면에서는 표 영역만 좌우로 이동할 수 있다.

정부과제 표는 2026-11-04 사용자 지시에 따라 종료일 없이 매일 정기 발행에 포함한다.
06:00 준비·07:30 발행의 기존 예약을 사용하며, 최근 7일 검색 범위는 운영 기간 제한이 아니다.
