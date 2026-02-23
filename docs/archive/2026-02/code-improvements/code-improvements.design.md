# [Design] code-improvements

> 작성일: 2026-02-22
> 단계: Design
> 참조: [Plan](../../../01-plan/features/code-improvements.plan.md)

---

## 1. 설계 개요

Plan v3의 5개 Phase를 구현하기 위한 파일별 변경 명세입니다.
**새로 생성되는 파일**과 **기존 파일 수정** 두 가지로 구분합니다.

---

## 2. Phase 0 — 롤백/복구 시스템

### P0-1. `scripts/checkpoint.sh`

**신규 생성** | 의존성 없음

```bash
#!/usr/bin/env bash
# scripts/checkpoint.sh — Git 태그 기반 코드 체크포인트 관리

set -e
COMMAND=$1
LABEL=$2
TAG_PREFIX="backup"
```

| 명령 | 동작 | git 명령 |
|------|------|---------|
| `create {label}` | 현재 커밋에 태그 생성 | `git tag backup/YYYYMMDD-HHMMSS-{label}` |
| `list` | backup/* 태그 목록 + 날짜 | `git tag -l 'backup/*'` |
| `restore {label}` | 해당 태그로 hard reset | `git reset --hard backup/{label}` (확인 프롬프트 포함) |
| `delete {label}` | 로컬 태그 삭제 | `git tag -d backup/{label}` |

**주의사항**:
- `restore` 실행 전 "현재 uncommitted 변경사항이 사라집니다. 계속하시겠습니까? (y/N)" 확인
- `docs/`와 `data/`는 별도 롤백 전략 사용 (이 스크립트 범위 외)

---

### P0-2. `src/utils/snapshot.py`

**신규 생성** | 의존성: `shutil`, `json`, `datetime` (표준 라이브러리)

```python
class DataSnapshot:
    BASE_DIR = "data/_snapshots"
    MAX_KEEP = 7  # 기본 보관 개수

    def create(self, label: str = "") -> str:
        """data/ 디렉토리 스냅샷 생성. 스냅샷 ID 반환."""

    def restore(self, snapshot_id: str) -> None:
        """스냅샷 ID로 data/ 복원. 현재 data/ 덮어쓰기 전 확인."""

    def list(self) -> list[dict]:
        """스냅샷 목록 반환: [{id, label, created_at, size_mb}]"""

    def cleanup(self, keep: int = MAX_KEEP) -> int:
        """오래된 스냅샷 삭제. 삭제된 개수 반환."""
```

**스냅샷 디렉토리 구조**:
```
data/
└── _snapshots/
    ├── 20260222_143000_pre-work/
    │   ├── members/          ← data/members/ 복사본
    │   ├── gov/              ← data/gov/ 복사본
    │   ├── dashboard_data.json
    │   └── _meta.json        ← {id, label, created_at, original_files_count}
    └── 20260222_160000_auto/
        └── ...
```

**`_meta.json` 스키마**:
```json
{
  "id": "20260222_143000_pre-work",
  "label": "pre-work",
  "created_at": "2026-02-22T14:30:00+09:00",
  "files_count": 42,
  "size_bytes": 128000
}
```

**제외 대상** (스냅샷에 포함하지 않음):
- `data/_snapshots/` 자체 (재귀 방지)
- `data/usage.db` (SQLite, 별도 관리)

---

### P0-3. `scripts/rollback_docs.py`

**신규 생성** | 의존성: `subprocess`, `argparse`

```python
# 사용법
# python scripts/rollback_docs.py status   — 최근 docs/ 변경 커밋 목록
# python scripts/rollback_docs.py last     — 마지막 docs/ 변경 커밋 revert
# python scripts/rollback_docs.py --before YYYY-MM-DD  — 날짜 이전 마지막 정상 커밋으로 복원
```

**내부 로직**:
1. `git log --oneline -- docs/` 로 docs/ 변경 커밋 목록 추출
2. `last` 모드: `git revert --no-commit {commit_hash}` + 확인 후 `git commit`
3. `--before` 모드: 해당 날짜 이전 마지막 커밋 해시를 찾아 `git checkout {hash} -- docs/`

**`daily-news.yml` CI 안전장치 추가**:

```yaml
# .github/workflows/daily-news.yml 에 추가할 step
- name: Validate generated output
  run: |
    # 1. index.html 존재 확인
    test -f docs/index.html || (echo "❌ index.html 생성 실패" && exit 1)
    # 2. 파일 크기 최소 기준 (1KB 이상)
    [ $(wc -c < docs/index.html) -gt 1024 ] || (echo "❌ index.html 비정상 (너무 작음)" && exit 1)
    # 3. HTML 기본 구조 확인
    grep -q "</html>" docs/index.html || (echo "❌ index.html HTML 구조 불완전" && exit 1)
    echo "✅ 출력 검증 통과"
```

---

### P0-4. `scripts/firestore_backup.py` + `scripts/firestore_restore.py`

**신규 생성** | 의존성: `firebase_admin` (이미 requirements.txt에 있음)

**backup 설계**:
```python
# scripts/firestore_backup.py
# 실행: python scripts/firestore_backup.py [--collections all|quickview_pages|members|gov]

BACKUP_DIR = "backups/firestore"

def export_collection(db, collection_name: str, output_path: str) -> int:
    """컬렉션 전체를 JSON으로 내보냄. 저장된 문서 수 반환."""
    # Firestore 초기화: generate_quickview.py의 get_firestore_client() 패턴 재사용
```

**restore 설계**:
```python
# scripts/firestore_restore.py
# 실행: python scripts/firestore_restore.py --from backups/firestore/20260222_143000
#        python scripts/firestore_restore.py --collection quickview_pages
#                                             --from backups/firestore/20260222_143000/quickview_pages.json
```

**백업 디렉토리 구조**:
```
backups/
└── firestore/
    └── 20260222_143000/
        ├── quickview_pages.json   ← [{id, data: {...}}]
        ├── members.json
        ├── gov.json
        └── _manifest.json         ← {created_at, collections: [...], doc_counts: {...}}
```

**.gitignore 추가**:
```
backups/
data/_snapshots/
```

---

## 3. Phase 1 — 보안 수정

### P1-1. `src/fetchers/gov.py` 수정

**변경 위치 및 내용**:

| 위치 | 현재 | 변경 후 |
|------|------|---------|
| L14 | `DEFAULT_GOV_API_KEY = "b333fbc..."` | 삭제 |
| L395 (fetch_gov_announcements) | `service_key = os.getenv("GOV_API_KEY", DEFAULT_GOV_API_KEY)` | `service_key = os.getenv("GOV_API_KEY", "")` |
| L315 (fetch_bizinfo_announcements) | `api_key = "6TJrqD"` | `api_key = os.getenv("BIZINFO_API_KEY", "")` |

**폴백 처리**:
```python
# fetch_bizinfo_announcements() 내부
api_key = os.getenv("BIZINFO_API_KEY", "")
if not api_key:
    logger.warning("[Bizinfo] BIZINFO_API_KEY not set. Skipping.")
    return []
```

**`.env.example` 추가**:
```
BIZINFO_API_KEY=your_bizinfo_api_key_here
```

### P1-2. Dead Code 제거

**변경 위치**: `src/fetchers/gov.py`, `fetch_iitp_announcements()` 내부

두 번째 `return items_list` 라인 1줄 삭제.

---

## 4. Phase 2 — 프로젝트 구조 정리

### P2-1. requirements 파일 분리

**신규 생성할 파일들**:

`requirements-dev.txt`:
```
pytest>=7.0,<9.0
pytest-cov>=4.0,<6.0
```

`requirements-admin.txt`:
```
streamlit>=1.30,<2.0
```

`requirements-extra.txt`:
```
fastapi>=0.100,<1.0
pydantic>=2.0,<3.0
youtube-transcript-api>=0.6,<1.0
uvicorn>=0.20,<1.0
```

**기존 `requirements.txt`**: 변경 없음 (프로덕션 CI 의존성만 유지)

### P2-2. 루트 레벨 파일 정리

**이동 대상** (루트 → `maintenance/`):
```
rebuild_daily_pages.py     → maintenance/rebuild_daily_pages.py
rebuild_member_pages.py    → maintenance/rebuild_member_pages.py
rebuild_all_html.py        → maintenance/rebuild_all_html.py
rebuild_quickview_pages.py → maintenance/rebuild_quickview_pages.py
regenerate_wordcloud.py    → maintenance/regenerate_wordcloud.py
```

**삭제 대상** (이미 완료된 일회성 패치):
```
fix_all_templates.py, fix_daily_pages_final.py, fix_gov_mobile.py
fix_malformed_links.py, fix_quickview_html.py, fix_quickview_shadowdom.py
fix_timestamp_links.py, fix_webshare_responsive.py, fix_webshare_youtube.py
patch_daily_buttons.py, patch_daily_alerts.py
simplify_actions.py, update_templates.py, complete_fix.py
convert_gov_mobile.py, convert_members_to_list.py
remove_inline_actions.py, remove_share_alerts.py
check_pages.py, verify_title_changes.py
send_now.py, admin_server.py
```

> **주의**: 삭제 전 `git rm` 사용 (이력 보존). 삭제 후 되돌리려면 `git checkout HEAD~1 -- {파일명}`

### P2-3. 루트 테스트 파일 정리

**`tests/`로 이동하는 파일** (pytest 형식으로 리팩토링):
```
test_koneps_check.py    → tests/test_koneps.py (통합)
test_gov_status.py      → tests/test_gov_fetcher.py
test_bizinfo_only.py    → tests/test_bizinfo_fetcher.py
test_notifier.py        → tests/test_notifier.py
```

**삭제 대상** (디버그 전용):
```
test_koneps_debug.py, test_koneps_debug_v2.py
test_koneps_extended.py, test_gemini.py, test_prompt.py
```

---

## 5. Phase 3 — Firebase 확장 + 아키텍처

### P3-1. `src/utils/storage.py` — Firestore 백엔드 추가

**기존 `MemberStorage` 클래스 확장** (기존 JSON 로직은 그대로 유지):

```python
class MemberStorage:
    def __init__(self, data_dir="data/members"):
        self.use_firestore = os.getenv("FIRESTORE_ENABLED", "false").lower() == "true"
        self.data_dir = data_dir
        self._db = None
        if not self.use_firestore:
            os.makedirs(self.data_dir, exist_ok=True)

    @property
    def db(self):
        """지연 초기화 — 첫 Firestore 호출 시에만 연결."""
        if self._db is None:
            from generate_quickview import get_firestore_client  # 기존 패턴 재사용
            self._db = get_firestore_client()
        return self._db

    def load_news(self, member_id: str) -> list[dict]:
        if self.use_firestore:
            return self._load_from_firestore(member_id)
        return self._load_from_json(member_id)   # 기존 메서드 그대로

    def save_news(self, member_id: str, new_items: list[dict]) -> list[dict]:
        if self.use_firestore:
            return self._save_to_firestore(member_id, new_items)
        return self._save_to_json(member_id, new_items)  # 기존 메서드 그대로

    # --- Firestore 전용 메서드 (신규) ---

    def _load_from_firestore(self, member_id: str) -> list[dict]:
        """Firestore members/{member_id}/news 컬렉션에서 로드."""

    def _save_to_firestore(self, member_id: str, new_items: list[dict]) -> list[dict]:
        """기존 dedup 로직 유지, Firestore에 저장."""
```

**Firestore 문서 ID 생성 규칙**:
```python
import hashlib
doc_id = hashlib.md5(item["link"].encode()).hexdigest()[:16]
```

**`src/storage/gov_storage.py` — 동일 패턴 적용**:
`GovStorage` 클래스에 동일한 `use_firestore` 폴백 패턴 추가.

**GitHub Actions `daily-news.yml` 환경변수 추가**:
```yaml
env:
  FIRESTORE_ENABLED: "true"
```

### P3-2. `generate_quickview.py` → `src/generators/quickview.py`

**파일 이동**:
```
generate_quickview.py → src/generators/quickview.py
```

**`main.py` 임포트 수정**:
```python
# Before
try:
    from generate_quickview import get_latest_quickviews, process_quickview_pages
except Exception as e:
    print(f"[Quickview] Error: {e}")

# After
if os.getenv("ENABLE_QUICKVIEW", "true").lower() == "true":
    from src.generators.quickview import get_latest_quickviews, process_quickview_pages
```

### P3-3. `main.py` 분리

**신규 파일 `src/utils/dedup.py`**:
```python
"""Article deduplication utilities."""
from difflib import SequenceMatcher
import re

def normalize_title(title: str) -> str:
    """Normalize title for similarity comparison."""

def is_similar_title(new_title: str, existing_titles: list[str],
                     threshold: float = 0.80) -> bool:
    """Check if new_title is similar to any existing title."""
```

**신규 파일 `src/utils/archive.py`**:
```python
"""Daily archive file resolution and merge utilities."""
import os

def resolve_daily_file(archive_dir: str, date_str: str, run_id: str) -> tuple[str, list[str]]:
    """Return (primary_filename, duplicate_filenames) for the given date."""
```

**`main.py` 변경**:
- `normalize_title`, `is_similar_title` → `from src.utils.dedup import ...`로 교체
- `resolve_daily_file` 중첩 함수 → `from src.utils.archive import ...`로 교체
- `process_category()` 내부 중첩 함수 정의 3개 제거

### P3-4. 미통합 모듈 정리

| 파일 | 조치 |
|------|------|
| `src/parser/base.py`, `src/parser/youtube.py`, `src/parser/article.py` | `src/url_analyzer.py`의 지원 모듈로 확정 → git add |
| `src/llm/summarizer.py` | 중복 판정 → 삭제 또는 `# EXPERIMENTAL:` 주석 추가 후 git add |
| `src/url_analyzer.py` | `src/parser/` 사용 방식으로 리팩토링 후 git add |

---

## 6. Phase 4 — 코드 품질

### P4-1. `src/fetchers/gov.py` bare except 수정

**위치**: `fetch_koneps_announcements()` 내 `response.json()` 파싱 부분

```python
# Before
try:
    data = response.json()
except:
    continue

# After
try:
    data = response.json()
except (json.JSONDecodeError, ValueError):
    logger.debug(f"[KONEPS] JSON parse error for {keyword}")
    continue
```

**import 추가**: 파일 상단에 `import json` 추가

### P4-2. IITP SSL 검증

`verify=False` 제거하고 `verify=True`로 변경. 실패 시 IITP 소스를 조용히 비활성화.

### P4-3. 타입 힌트 보강 (`main.py`)

```python
# 추가할 타입 힌트 예시
def merge_articles(primary_items: list[dict], secondary_items: list[dict]) -> list[dict]:
def rebuild_indexes(categories: dict, consolidate_archives: bool = False) -> None:
def process_category(config, now_utc: datetime.datetime) -> dict:
```

---

## 7. 구현 순서 및 의존성

```
P0-1 (checkpoint.sh)          ← 독립, 가장 먼저
P0-2 (snapshot.py)            ← 독립
P0-3 (rollback_docs.py)       ← 독립
P0-4 (firestore_backup.py)    ← firebase_admin 필요, Phase 3 전 완료
    ↓
P1-1, P1-2 (gov.py 수정)      ← P0-1 체크포인트 생성 후
    ↓
P2-1 (requirements 분리)      ← 독립
P2-2, P2-3 (파일 정리)        ← git rm 사용
    ↓
P3-2 (quickview 이동)         ← P3-1 전에 해야 경로 정리됨
P3-3 (dedup.py, archive.py)   ← P3-1과 독립적
P3-1 (storage.py Firestore)   ← P0-4 완료 후, P3-2/3와 병행 가능
P3-4 (미통합 모듈)            ← 독립
    ↓
P4-1, P4-2, P4-3              ← 언제든 가능
```

---

## 8. 검증 방법

각 Phase 완료 후 실행할 검증 명령:

```bash
# Phase 0 검증
./scripts/checkpoint.sh list                    # 태그 생성 확인
python -c "from src.utils.snapshot import DataSnapshot; print(DataSnapshot().list())"

# Phase 1 검증
python -c "from src.fetchers.gov import fetch_gov_announcements; print('OK')"
python -m pytest tests/test_style_constants.py  # 기존 테스트 통과 확인

# Phase 2 검증
pip install -r requirements.txt                 # 핵심 의존성 설치 확인
pip install -r requirements-dev.txt             # 개발 의존성 확인
python -m pytest tests/                         # 전체 테스트

# Phase 3 검증
FIRESTORE_ENABLED=false python main.py --limit 2  # JSON 폴백 모드 검증
FIRESTORE_ENABLED=true python main.py --limit 2   # Firestore 모드 검증 (로컬)

# 전체 파이프라인 검증 (Phase 0~3 완료 후)
python main.py --limit 3
test -f docs/index.html && echo "✅ 파이프라인 정상"
```
