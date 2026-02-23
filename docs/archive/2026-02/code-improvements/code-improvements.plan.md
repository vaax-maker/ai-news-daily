# [Plan] code-improvements

> 작성일: 2026-02-22 (v3 — 롤백/복구 시스템 추가)
> 단계: Plan
> 우선순위: High (보안 이슈 포함)

---

## 1. 개요 (Overview)

코드베이스 전반 분석 결과를 바탕으로, **현재 구조 개선**과 **Firebase 확장**을 하나의 로드맵으로 통합한 계획입니다.

### 핵심 전제

- **GitHub Pages + Actions 유지**: 정적 사이트 생성에 최적화된 현재 구조를 유지
- **Firebase는 전면 이전이 아닌 확장**: Firestore를 `data/` 디렉토리 영속성 계층으로 활용
- **현재 이미 Firebase 부분 통합 중**: `quickview_pages` 컬렉션, 수동 기사 처리가 Firestore 사용
- **목표**: CI 실행마다 초기화되는 `data/` 문제를 해결하면서, 코드 품질/보안 동시 개선

### 최종 목표 아키텍처

```
현재                                   목표
─────────────────────────────          ──────────────────────────────────────
GitHub Actions (스케줄러)              GitHub Actions (유지)
    ↓                                      ↓
Python 파이프라인                      Python 파이프라인 (리팩토링)
    ↓                                      ↓ ↑
data/ (git-ignored, CI마다 소실)  →    Firestore (영구 데이터 계층)
    ↓                                      ↓
docs/ → GitHub Pages (유지)           docs/ → GitHub Pages (유지)
```

---

## 2. 개선 항목 (5단계 로드맵)

### ⚫ Phase 0 — 롤백/복구 시스템 (모든 작업 전 선행 구축)

> **왜 Phase 0인가**: 코드 변경, Firebase 마이그레이션, 파일 정리 등 모든 작업에는 롤백 리스크가 존재합니다.
> 다른 Phase 착수 전에 복구 수단을 먼저 확보해야 안전하게 진행할 수 있습니다.

이 프로젝트의 데이터는 3개 계층으로 구성되며, 각각 다른 롤백 전략이 필요합니다:

```
계층 1: 소스 코드 (.py, templates/, config/)   → git tag 체크포인트
계층 2: data/ JSON 파일                        → 로컬 스냅샷 (git-ignored)
계층 3: docs/ 생성 HTML                        → git revert (이미 git 추적)
계층 4: Firestore 데이터 (Phase 3 이후)        → JSON 덤프 백업
```

#### P0-1. Git 체크포인트 스크립트

**목적**: 작업 시작 전 소스코드 상태를 git tag로 저장.

**구현**: `scripts/checkpoint.sh` (또는 `scripts/checkpoint.py`)

```bash
# 사용법
./scripts/checkpoint.sh create "before-phase1-security-fix"
# → git tag backup/before-phase1-security-fix 생성

./scripts/checkpoint.sh list
# → 모든 backup/* 태그 목록 출력

./scripts/checkpoint.sh restore "before-phase1-security-fix"
# → git reset --hard backup/before-phase1-security-fix
```

**롤백 대상**: `src/`, `templates/`, `config/`, `scripts/`, `requirements*.txt`, `main.py`
**롤백 불포함**: `data/` (git-ignored), `docs/` (별도 전략)

**구현 규칙**:
- 작업 시작 시 자동으로 체크포인트 생성 안내 (선택 강제는 하지 않음)
- 태그 이름 형식: `backup/YYYYMMDD-HHMMSS-{설명}` (예: `backup/20260222-143000-before-firebase`)
- 오래된 backup 태그는 30일 후 자동 목록 표시 (삭제는 수동)

#### P0-2. `data/` 로컬 스냅샷 시스템

**목적**: `python main.py` 실행 전후 `data/` 디렉토리 상태 보존.
`data/`는 `*.json` 패턴으로 git-ignored이므로 별도 백업 필요.

**구현**: `src/utils/snapshot.py`

```python
# 사용 시나리오
from src.utils.snapshot import DataSnapshot

# 실행 전 스냅샷 생성
snap = DataSnapshot()
snap_id = snap.create("before-firebase-migration")
# → data/_snapshots/20260222_143000_before-firebase-migration/ 에 복사본 저장

# 문제 발생 시 복원
snap.restore(snap_id)
# → 스냅샷에서 data/ 복원

# 오래된 스냅샷 정리 (최근 7개만 유지)
snap.cleanup(keep=7)
```

**스냅샷 대상**:
```
data/
├── members/*.json        → 스냅샷 포함
├── gov/*.json            → 스냅샷 포함
├── dashboard_data.json   → 스냅샷 포함
└── _snapshots/           → 스냅샷 제외 (메타 디렉토리)
```

**`main.py` 통합 (선택적)**:
```python
# main.py 최상단 (선택 옵션)
if os.getenv("AUTO_SNAPSHOT", "false") == "true":
    from src.utils.snapshot import DataSnapshot
    DataSnapshot().create(f"auto-{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}")
```

#### P0-3. `docs/` 롤백 가이드 문서화

**목적**: 잘못된 CI 실행이 깨진 HTML을 `docs/`에 커밋/푸시했을 때 복구 절차.

**현황 분석**:
- `docs/`는 git 추적 중 → `git revert` 또는 `git reset`으로 복구 가능
- `docs/index.html`은 이미 `tempfile.mkstemp` 패턴으로 원자적 쓰기 구현 (부분적 안전)
- CI 실패 시 `docs/` 커밋이 롤백되지 않는 문제 존재

**구현**: `scripts/rollback_docs.py` + `docs/ROLLBACK.md`

```bash
# 마지막 docs/ 변경 전으로 되돌리기
python scripts/rollback_docs.py last
# → docs/ 폴더 변경이 포함된 마지막 커밋을 revert

# 특정 날짜 이전으로
python scripts/rollback_docs.py --before 2026-02-20
# → 해당 날짜 이전의 마지막 정상 커밋 체크아웃

# 현재 docs/ 상태 확인
python scripts/rollback_docs.py status
```

**CI 안전장치 강화** (`daily-news.yml`):
```yaml
# 현재: 항상 커밋
git add docs data
git commit -m "Update Daily News"

# 개선: 핵심 파일 존재 여부 확인 후 커밋
- name: Validate output before commit
  run: |
    test -f docs/index.html || (echo "index.html missing!" && exit 1)
    python -c "from html.parser import HTMLParser; ..."  # HTML 유효성 검사
```

#### P0-4. Firestore 마이그레이션 전 백업 (Phase 3 전 실행)

**목적**: P3-1 Firestore 영속성 계층 구축 전, 기존 Firestore 데이터를 JSON으로 덤프.

**구현**: `scripts/firestore_backup.py` + `scripts/firestore_restore.py`

```bash
# Firestore 전체 백업
python scripts/firestore_backup.py
# → backups/firestore/20260222_143000/
#     ├── quickview_pages.json
#     ├── members.json
#     └── gov.json

# 특정 컬렉션 복원
python scripts/firestore_restore.py --collection quickview_pages \
  --from backups/firestore/20260222_143000/quickview_pages.json
```

**주의**: `backups/` 디렉토리는 `.gitignore`에 추가 (대용량 가능)

---

#### Phase 0 체크리스트 (작업 착수 전 확인)

```
작업 시작 전:
  □ scripts/checkpoint.sh create "{작업명}" 실행
  □ data/ 스냅샷 생성 (python -c "from src.utils.snapshot import DataSnapshot; DataSnapshot().create('pre-work')")
  □ Firestore 백업 (Phase 3 이상인 경우)

작업 완료 후:
  □ python main.py --limit 3 으로 파이프라인 검증
  □ docs/index.html 정상 생성 확인
  □ 이상 없으면 체크포인트 유지, 1주 후 삭제

롤백이 필요한 경우:
  □ 코드 문제: ./scripts/checkpoint.sh restore {체크포인트명}
  □ data/ 문제: python -c "from src.utils.snapshot import DataSnapshot; DataSnapshot().restore('{id}')"
  □ docs/ 문제: python scripts/rollback_docs.py last
  □ Firestore 문제: python scripts/firestore_restore.py --from backups/firestore/{날짜}/
```

---

### 🔴 Phase 1 — 즉시 수정 (보안/버그)

#### P1-1. 하드코딩된 API 키 제거
**파일**: [src/fetchers/gov.py](src/fetchers/gov.py)
- L14: `DEFAULT_GOV_API_KEY = "b333fbc..."` — 공공데이터포털 키 소스 노출
- L315: `api_key = "6TJrqD"` — Bizinfo API 키 하드코딩

**변경 내용**:
```python
# Before
DEFAULT_GOV_API_KEY = "b333fbc99c..."
api_key = "6TJrqD"

# After
service_key = os.getenv("GOV_API_KEY")       # 기존 변수명 재사용
bizinfo_key = os.getenv("BIZINFO_API_KEY", "6TJrqD")  # 하위 호환 폴백
```
- `.env.example`에 `BIZINFO_API_KEY=` 항목 추가
- GitHub Actions Secrets에 `BIZINFO_API_KEY` 등록

#### P1-2. Dead Code 제거
**파일**: [src/fetchers/gov.py:307-308](src/fetchers/gov.py#L307)
- `fetch_iitp_announcements()` 내부에 `return items_list` 중복 존재 (두 번째는 절대 실행 안 됨)
- 두 번째 `return` 라인 삭제

---

### 🟠 Phase 2 — 프로젝트 구조 정리

#### P2-1. `requirements.txt` 누락 항목 보완

| 라이브러리 | 사용 위치 | 분류 |
|-----------|----------|------|
| `streamlit` | `admin/app.py` | `requirements-admin.txt` |
| `fastapi` | `src/url_analyzer.py` | `requirements-extra.txt` |
| `pydantic` | `src/url_analyzer.py` | `requirements-extra.txt` |
| `youtube_transcript_api` | `src/url_analyzer.py` | `requirements-extra.txt` |
| `pytest` | `tests/` | `requirements-dev.txt` |

**파일 분리 방향**:
```
requirements.txt          ← 프로덕션 CI 핵심 의존성 (현재)
requirements-admin.txt    ← streamlit 등 관리자 도구
requirements-dev.txt      ← pytest 등 개발 도구
requirements-extra.txt    ← url_analyzer 등 실험적 모듈
```

#### P2-2. 루트 레벨 임시 스크립트 정리
루트에 산재한 ~20개 일회성 패치/수정 스크립트:
`fix_*.py`, `patch_*.py`, `rebuild_*.py`, `simplify_*.py`, `update_*.py`, `convert_*.py`

**처리 기준**:
- 반복 사용 가능성 있음 → `maintenance/`로 이동
- 완전히 완료된 일회성 → 삭제
- 기준 불명확 → 목록 작성 후 사용자 확인

#### P2-3. 루트 레벨 테스트 파일 정리
루트에 위치한 임시 테스트/디버그 파일 9개:
`test_koneps_check.py`, `test_koneps_debug.py`, `test_koneps_debug_v2.py`,
`test_gov_status.py`, `test_koneps_extended.py`, `test_bizinfo_only.py`,
`test_gemini.py`, `test_notifier.py`, `test_prompt.py`

**처리 기준**:
- 재사용 가치 있는 검증 로직 → `tests/`로 이동 + pytest 형식 변환
- 일회성 디버그 → 삭제

---

### 🟡 Phase 3 — Firebase 확장 + 아키텍처 개선 (핵심)

#### P3-1. Firestore 데이터 영속성 계층 구축 ⭐

**현황**: `data/` 디렉토리가 `.gitignore`에 포함되어 CI 실행 시 매번 초기화.
회원사 뉴스 이력, 정부과제 데이터가 CI 간 공유되지 않음.

**목표 Firestore 스키마**:
```
Firestore
├── members/
│   └── {member_id}/          (예: "삼성전자")
│       └── news/
│           └── {article_id}  (link의 hash)
│               ├── title: str
│               ├── link: str
│               ├── summary_html: str
│               ├── published_display: str
│               ├── timestamp: number
│               └── source_name: str
│
├── gov/
│   └── announcements/
│       └── {item_id}         (link의 hash)
│           ├── title: str
│           ├── link: str
│           ├── dept: str
│           ├── date: str
│           └── source_name: str
│
└── quickview_pages/           ← 이미 존재, 유지
    └── {page_id}
```

**구현 범위**:
1. `src/utils/storage.py` — `MemberStorage` 클래스에 Firestore 백엔드 추가
   - 기존 JSON 파일 방식은 로컬 개발용 폴백으로 유지
   - `FIRESTORE_ENABLED=true` 환경변수로 전환 제어
2. `src/storage/gov_storage.py` — `GovStorage` 동일 방식 확장
3. GitHub Actions `daily-news.yml` — `FIRESTORE_ENABLED=true` 설정

**비용 분석** (Firebase Spark 무료 플랜):
| 작업 | 일일 추정 | 월간 | 무료 한도 | 상태 |
|------|---------|------|---------|------|
| 기사 write | ~80건 | ~2,400 | 20,000/일 | ✅ 무료 |
| Gov write | ~50건 | ~1,500 | 20,000/일 | ✅ 무료 |
| 데이터 read (CI) | ~200건 | ~6,000 | 50,000/일 | ✅ 무료 |
| 저장 용량 | ~300KB/일 | ~9MB | 1,000MB | ✅ 무료 |

**결론: 현재 사용 규모에서 Firebase Spark 무료 플랜으로 완전 운용 가능**

#### P3-2. `generate_quickview.py` 정식 모듈화

**현황**: 루트에 위치, `main.py`에서 `try/except ImportError`로 선택적 임포트.

```python
# 현재 main.py
try:
    from generate_quickview import get_latest_quickviews, process_quickview_pages
except Exception as e:
    print(f"[Quickview] Error loading quickview data: {e}")
```

**변경 방향**:
- `generate_quickview.py` → `src/generators/quickview.py`로 이동
- `main.py` 임포트를 정식 경로로 변경
- 선택적 동작은 `ENABLE_QUICKVIEW=true` 환경변수로 제어

#### P3-3. `main.py` 분리 — `process_category()` 추출

**현황**: `main.py` 1000줄, `process_category()` 280줄, 내부 중첩 함수 포함.

**분리 대상**:
```
main.py (현재 1000줄)
  └── process_category()
        ├── normalize_title()      → src/utils/dedup.py
        ├── is_similar_title()     → src/utils/dedup.py
        └── resolve_daily_file()   → src/utils/archive.py

main.py (목표 ~400줄)
  └── process_category()가 dedup.py, archive.py를 호출하는 흐름만 담당
```

#### P3-4. 미통합 신규 모듈 방향 결정

**현황**: `src/llm/summarizer.py`, `src/parser/` (base, youtube, article) — git untracked
기존 `src/generators/llm.py`와 기능 중복.

**결정 필요 사항**:
- 현재 `src/llm/summarizer.py`는 `gpt-4o` 단일 모델, 다른 프롬프트 사용
- 기존 `src/generators/llm.py`는 OpenAI→Grok→Gemini 폴백 체인
- **권장**: `src/parser/`는 `url_analyzer.py`의 지원 모듈로 역할 명확화
  → git add 후 `src/url_analyzer.py`와 함께 정식 모듈로 등록
- **권장**: `src/llm/summarizer.py`는 중복이므로 삭제 또는 실험용 표시

---

### 🟢 Phase 4 — 코드 품질

#### P4-1. Bare `except:` 클로즈 개선
**위치**: [src/fetchers/gov.py:175](src/fetchers/gov.py#L175)
```python
# Before
except:
    continue

# After
except (json.JSONDecodeError, ValueError, KeyError):
    continue
```

#### P4-2. IITP SSL 검증 문제
**위치**: [src/fetchers/gov.py:255](src/fetchers/gov.py#L255)
`verify=False`로 SSL 인증 비활성화 중. IITP 공식 API 유무 확인 후 스크래핑 유지 또는 제거 결정.

#### P4-3. 타입 힌트 보강
`main.py` 주요 함수(`process_category`, `merge_articles`, `rebuild_indexes`)에 반환 타입 힌트 추가.

---

## 3. 전체 로드맵 요약

| Phase | 항목 | 우선순위 | 난이도 | 임팩트 |
|-------|------|---------|--------|--------|
| **Phase 0** ⚫ | P0-1 Git 체크포인트 스크립트 | ⚫ 선행 | 낮음 | 코드 롤백 기반 |
| | P0-2 `data/` 로컬 스냅샷 시스템 | ⚫ 선행 | 중간 | 데이터 롤백 |
| | P0-3 `docs/` 롤백 가이드 + CI 안전장치 | ⚫ 선행 | 낮음 | HTML 롤백 |
| | P0-4 Firestore 백업 스크립트 | ⚫ 선행 | 낮음 | Firestore 롤백 |
| **Phase 1** 🔴 | P1-1 하드코딩 API 키 제거 | 🔴 즉시 | 낮음 | 보안 리스크 제거 |
| | P1-2 Dead code 제거 | 🔴 즉시 | 낮음 | 코드 명확성 |
| **Phase 2** 🟠 | P2-1 requirements.txt 보완 | 🟠 높음 | 낮음 | 재현성/협업 |
| | P2-2 루트 임시 스크립트 정리 | 🟠 높음 | 중간 | 유지보수성 |
| | P2-3 루트 테스트 파일 정리 | 🟠 높음 | 낮음 | 구조 명확성 |
| **Phase 3** 🟡 | P3-1 Firestore 영속성 계층 ⭐ | 🟡 중간 | 중간 | 데이터 영속성 |
| | P3-2 quickview 모듈화 | 🟡 중간 | 낮음 | 구조 일관성 |
| | P3-3 main.py 분리 | 🟡 중간 | 높음 | 가독성/테스트성 |
| | P3-4 미통합 모듈 정리 | 🟡 중간 | 중간 | 기술 부채 해소 |
| **Phase 4** 🟢 | P4-1 Bare except 개선 | 🟢 낮음 | 낮음 | 안정성 |
| | P4-2 IITP SSL 문제 | 🟢 낮음 | 중간 | 안정성 |
| | P4-3 타입 힌트 보강 | 🟢 낮음 | 중간 | 코드 품질 |

---

## 4. 실행 전략

### 권장 실행 순서

```
Day 1 (선행): Phase 0 — 롤백 인프라 구축
  → P0-1: scripts/checkpoint.sh 작성 (30분)
  → P0-2: src/utils/snapshot.py 구현 (2시간)
  → P0-3: scripts/rollback_docs.py + CI 안전장치 (1시간)
  → P0-4: scripts/firestore_backup.py (1시간, 나중에 해도 되나 Phase 3 전 필수)

  ★ 이후 모든 작업은 체크포인트 생성 후 시작

Week 1: Phase 1 (보안 즉시 수정)
  → [체크포인트 생성]
  → P1-1: gov.py API 키 환경변수화 (30분)
  → P1-2: Dead code 삭제 (10분)
  → [python main.py --limit 3 검증]

Week 1-2: Phase 2 (구조 정리)
  → [체크포인트 생성]
  → P2-1: requirements.txt 분리 (1시간)
  → P2-2/3: 루트 파일 정리 (2-3시간, 목록 확인 필요)

Week 2-3: Phase 3 (Firebase + 아키텍처)
  → [체크포인트 생성 + Firestore 백업 (P0-4)]
  → P3-1: Firestore storage 백엔드 구현 (핵심, 4-6시간)
  → P3-2: quickview 모듈 이동 (1시간)
  → P3-3: main.py dedup/archive 분리 (3-4시간)
  → P3-4: 미통합 모듈 결정 및 정리 (1시간)

Week 3+: Phase 4 (품질 개선, 여유 시간에 진행)
```

### P3-1 Firestore 구현 전략 (중요)

폴백 패턴으로 안전하게 전환:
```python
class MemberStorage:
    def __init__(self, data_dir="data/members"):
        self.use_firestore = os.getenv("FIRESTORE_ENABLED", "false").lower() == "true"
        self.data_dir = data_dir
        if self.use_firestore:
            self.db = get_firestore_client()  # 기존 generate_quickview.py 패턴 재사용
        else:
            os.makedirs(self.data_dir, exist_ok=True)

    def load_news(self, member_id):
        if self.use_firestore:
            return self._load_from_firestore(member_id)
        return self._load_from_json(member_id)      # 기존 코드 유지

    def save_news(self, member_id, new_items):
        if self.use_firestore:
            return self._save_to_firestore(member_id, new_items)
        return self._save_to_json(member_id, new_items)  # 기존 코드 유지
```

**환경별 설정**:
- 로컬 개발: `FIRESTORE_ENABLED=false` (기존 JSON 파일 방식)
- GitHub Actions CI: `FIRESTORE_ENABLED=true` + `FIREBASE_SERVICE_ACCOUNT` 시크릿

---

## 5. 범위 외 (Out of Scope)

- GitHub Pages → Firebase Hosting 전면 이전 (불필요, 비용 발생 가능)
- GitHub Actions → Firebase Functions 이전 (Blaze 플랜 필요, 현재 무료 구조 포기)
- 템플릿 HTML/CSS 디자인 변경
- 새로운 뉴스 소스 추가
- LLM 프롬프트 최적화
