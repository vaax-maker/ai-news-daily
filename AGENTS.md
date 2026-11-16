# AI Daily 운영 규칙

## 범위와 명칭

프로젝트는 `ai_news`, `customer_stories`, `youtube_summaries` 세 콘텐츠 영역과
`integrations`, `publishing`, `notifications` 공통 모듈로만 구성한다. 과거 프로젝트 이름을
새 코드명으로 재사용하지 않는다. 기존 공개 URL·외부 파일명은 호환 경계에서만 허용한다.

## 정본 실행 경로

- 일간 전체: `deploy/run_pipeline.sh`
- AI News: `python3 -m aidaily.ai_news.pipeline --docs-root docs`
- Customer Stories: `python3 -m aidaily.customer_stories.pipeline --docs-root docs --since 1d`
- YouTube Summaries: `deploy/run_youtube_summaries.sh`
- 기존 launchd 호환: `deploy/run_publish_9am.sh`

생성기는 외부 발행이나 Telegram 전송을 직접 수행하지 않는다. 순서는 항상 생성 →
`publishing` → `notifications`다.

## 구현 원칙

- 외부 API 호출은 `aidaily.integrations`에 둔다. 기능 패키지에서 HTTP 요청을 재구현하지 않는다.
- 모든 텍스트 LLM 호출은 `aidaily.integrations.openrouter`를 사용한다.
- 비밀값은 환경변수 또는 `~/.config/aidaily/.env`에서 읽고 커밋하지 않는다.
- `docs/`는 발행 산출물, `data/`는 런타임 상태다. 이력은 임의 삭제하지 않는다.
- 내부 서비스 주소는 `_abot/services.json` 등록값을 우선한다. 환경변수는 운영 오버라이드다.
- `run_publish_9am.sh`, `run_daily.sh`, `run_uservoice.sh`는 기존 자동화가 끊기지 않게 하는
  얇은 호환 진입점이며 새 로직을 추가하지 않는다.

## 검증

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 python3 -m compileall -q aidaily deploy
bash -n deploy/*.sh
```

라이브 LLM 요청, Telegram 전송, Git push는 별도 승인된 배포 검증에서만 실행한다.

<!-- ABOT-SESSION-GUIDANCE:START -->
## 편대 세션 역할과 AI 연동 — 지침 1.0.0 (2026-10-01)

- 사용자 승인: 공통 모델/추론 서버/GPU 대기열/클라이언트/API/레지스트리/통합 검증은 abot 관리 세션, 프로젝트 호출부/파이프라인/UI/품질/배포는 해당 담당 세션이 주도한다. 다른 프로젝트 작업의 코드 전체를 대신 덮어쓰지 않는다. 구체적인 사용자 지시와 기록된 인계의 범위는 따른다.
- 편대 또는 AI 연동 작업을 시작·재개하기 전에 `~/.abot-guidance/POLICY.txt`, `~/.abot-guidance/CONTRACT.json`과 프로젝트 `AGENTS.md`를 읽는다. 관련 인계는 `~/.abot-guidance/handoffs/`에 있다.
- 정본은 Drive `_abot/docs/SESSION-RESPONSIBILITIES.txt`, 프로젝트별 상태는 `_abot/docs/inference-adoption/<project>.json`이다. 담당 세션은 `docs/fleet-inference-acceptance.json`에 실제 담당·읽은 버전·적용 상태·시험 증거를 기록한다. 안내 배포를 담당 확인/제품 채택 완료로 기록하지 않는다.
- Pro 내부 AI는 `services.json`에서 주소를 찾고 공통 `~/abot-inference/inference_client.py`를 사용한다. GPU busy는 대기하며, 불확실한 제출은 같은 작업을 조회한다. 로컬 사용 불가가 확인된 경우만 프로젝트 정책/동의 범위에서 유료 대체한다. 인증 오류·불확실한 유료 제출을 자동 재시도하지 않는다.
- 기존 tmux·대화·프로세스·원본·수동 편집을 보존한다. 지침 파일 배포만으로 진행 중인 세션이 새 지침을 읽었다고 주장하거나 일괄 재시작하지 않는다. 호스트 운영은 에이전트가 직접 수행한다.

<!-- ABOT-SESSION-GUIDANCE:END -->


## 이 프로젝트의 내부 AI 인계

`docs/FLEET-INFERENCE-HANDOFF.txt`와 `docs/fleet-inference-acceptance.json`을 읽고 실제 적용 단계를 기록한다. 이 문서 배포는 기존 제품 호출 경로의 자동 전환이나 테스트/배포 완료를 의미하지 않는다.

## 정책 PRD 자동 갱신

정책·코드·설정 변경 후 `python3 deploy/sync_policy_prd.py --publish`를 실행한다. 매 60초 변경 감지 예약도 같은 작업을 수행한다. 의미가 달라진 정책은 `operations/policy-prd/POLICY.md`도 함께 갱신한다. 자동 생성물은 type1 인증 세션웹 `/p/aidaily-policy/`에만 등록하며 소식지 공개 산출물에 포함하지 않는다. 불확실한 등록은 기록된 transaction으로 재개한다. 키·원문·DB를 문서에 넣지 않는다.

문서·PRD를 웹으로 제공하는 경우도 기본 웹디자인 B 적용 대상이다. `abot-web-design-b` 원문을 읽고 UX 브리프·실제 6화면 검수·독립 사용자 검증을 수행한다. 문서 출력이라는 이유로 예외 처리하지 않는다.

정책 PRD 본문은 읽기 쉬운 문장별 개조식으로 유지한다. 표·코드·수치·예외 조건·원문 문구를 보존하고 자동 갱신에도 같은 형식을 적용한다.

<!-- ABOT-END-TO-END-COMPLETION-1.0.0 -->
## 실제 사용자 결과 기준 완료 검증 — 2026-10-28 사용자 승인
- 구현·단위시험·파일 생성·push·작업 종료만으로 완료 처리하지 않는다. 실제 사용자 입력부터 최종 사용 화면까지 검증한다.
- 이번 입력의 URL·영상 ID·작업 ID를 최종 출력과 대조한다. 기존 산출물이나 기존 목록의 정상 상태로 이번 작업의 성공을 대신하지 않는다.
- 발행은 의도한 발행일의 실제 공개 목록에 해당 결과가 포함되고, 그 목록의 링크로 결과 페이지와 필수 이미지가 열리는 것까지 필수 완료조건이다. 업로드일과 발행일을 구분한다.
- 자동 완료 검사는 이번 결과의 목록 포함·링크·필수 산출물까지 검사하고 하나라도 빠지면 실패해야 한다. 기존 항목 수 일치만으로 통과시키지 않는다.
- 실제 운영 경로와 별도 시험 환경·mock·재생시험을 구분한다. 부분 시험을 전체 검증으로 보고하지 않는다.
- 허용 범위의 실제 검증을 끝까지 수행한다. 권한·비용·승인이 필요한 검증을 임의 우회하지 않으며, 미검증·실패·대기 항목이 있으면 완료라고 보고하지 않는다.
- 완료 보고에는 변경점·이번 입력의 실제 결과·검증 근거·적용 상태·잔여 제한을 명시하고, 실패 보고 전 인접한 별도 문제와 인과관계를 검증한다.
