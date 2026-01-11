# VAAX AI-News-Daily

## 개요
VR-AR-AI-XR 기술 뉴스를 자동 수집, 요약하여 매일 웹페이지로 제공하는 서비스입니다.

## 주요 기능
- **AI/XR 뉴스 수집**: RSS 피드를 통해 AI 및 XR 관련 최신 뉴스 자동 수집
- **LLM 기반 요약**: Grok/Gemini를 활용한 3줄 뉴스 요약
- **정부과제 공고**: 과학기술정보통신부, 나라장터(입찰), 기업마당(지원사업) 통합 공고 제공
- **회원사 뉴스**: VAAX 회원사 관련 뉴스 자동 모니터링
- **워드클라우드**: 주간 키워드 트렌드 시각화
- **자동화된 업데이트**: 매일 2회 (08:00, 16:00) 데이터 수집 및 사이트 갱신
- **서비스 가이드**: 사이트 이용 방법 및 데이터 소스 안내 페이지 제공

## 프로젝트 구조

```
VAAXfinal/
├── main.py                 # 메인 진입점 (뉴스 수집 및 생성)
├── requirements.txt        # Python 의존성
├── .env.example           # 환경변수 예시
│
├── config/                 # 설정 파일
│   ├── categories.yaml    # AI/XR/Gov 카테고리 RSS 피드 설정
│   └── members.yaml       # 회원사 목록 및 키워드
│
├── src/                    # 핵심 소스코드
│   ├── config.py          # 설정 로더
│   ├── fetchers/          # 데이터 수집 모듈
│   │   ├── rss.py        # RSS 피드 수집
│   │   ├── gov.py        # 정부과제 API
│   │   └── search.py     # Google 뉴스 검색
│   ├── generators/        # 콘텐츠 생성 모듈
│   │   ├── html.py       # HTML 렌더링 (Jinja2)
│   │   └── llm.py        # LLM 요약 (Grok/Gemini)
│   └── utils/             # 유틸리티 모듈
│       ├── common.py     # 공통 헬퍼 함수
│       ├── storage.py    # 데이터 영속화
│       ├── wordcloud_generator.py  # 워드클라우드 생성
│       ├── usage_logger.py  # API 사용량 로깅
│       └── env_manager.py   # 환경변수 관리
│
├── templates/              # Jinja2 HTML 템플릿
│   ├── layout.html        # 공통 레이아웃
│   ├── dashboard.html     # 메인 대시보드
│   ├── daily_list.html    # 일일 뉴스 목록
│   ├── daily_table.html   # 테이블 형식 목록
│   ├── archive_index.html # 아카이브 인덱스
│   ├── gov_archive.html   # 정부과제 아카이브
│   ├── member_index.html  # 회원사 인덱스
│   └── member_page.html   # 회원사 개별 페이지
│
├── static/                 # 정적 자산
│   ├── css/style.css      # 스타일시트
│   └── images/            # 이미지 (로고, 워드클라우드)
│
├── admin/                  # 관리자 앱 (Streamlit)
│   └── app.py             # 관리자 대시보드
│
├── scripts/                # 유틸리티 스크립트 (수동 실행)
│   ├── cleanup_members.py # 미사용 회원 데이터 정리
│   ├── import_members.py  # 회원 목록 CSV 가져오기
│   └── migrate_members.py # 회원 데이터 마이그레이션
│
├── maintenance/            # 유지보수 스크립트 (수동 실행)
│   ├── audit_and_clean.py     # HTML 감사 및 정리
│   ├── check_missing_dates.py # 누락 날짜 확인
│   └── fix_mashed_articles.py # 깨진 기사 복구
│
├── docs/                   # 생성된 정적 웹페이지 (GitHub Pages)
│   ├── index.html         # 메인 대시보드
│   ├── ai/daily/          # AI 뉴스 아카이브
│   ├── xr/daily/          # XR 뉴스 아카이브
│   ├── gov/               # 정부과제 페이지
│   └── members/           # 회원사 뉴스 페이지
│
└── data/                   # 데이터 저장소 (git-ignored)
    ├── members/           # 회원사별 뉴스 JSON
    ├── gov/               # 정부과제 데이터
    └── usage.db           # API 사용량 SQLite DB
```

## 환경 변수 설정

`.env.example`을 `.env`로 복사하고 아래 키들을 설정하세요:

| 변수명 | 설명 | 필수 |
|--------|------|------|
| `GROK_API_KEY` | Groq API 키 (기본 요약 엔진) | ✅ |
| `GEMINI_API_KEY` | Google Gemini API 키 (백업) | ✅ |
| `GOV_API_KEY` | 공공데이터포털 API 키 | 선택 |
| `GOOGLE_ANALYTICS_ID` | GA 추적 ID | 선택 |

### 실행 플래그 (환경변수)

| 변수명 | 설명 | 기본값 |
|--------|------|--------|
| `RUN_AI` | AI 뉴스 수집 | true |
| `RUN_XR` | XR 뉴스 수집 | true |
| `RUN_GOV` | 정부과제 수집 | true |
| `RUN_MEMBERS` | 회원사 뉴스 수집 | true |
| `MAX_ARTICLES` | 카테고리당 최대 기사 수 | 10 |

## 실행 방법

### 로컬 실행
```bash
# 의존성 설치
pip install -r requirements.txt

# 환경변수 설정
cp .env.example .env
# .env 파일 편집하여 API 키 입력

# 전체 실행
python main.py

# 제한된 기사 수로 테스트
python main.py --limit 3
```

### GitHub Actions
저장소 **Settings → Secrets and variables → Actions**에 API 키들을 등록하면, 
`.github/workflows`에 정의된 스케줄에 따라 자동 실행됩니다.

### 관리자 대시보드
```bash
streamlit run admin/app.py
```

## 기술 스택
- **Python 3.10+**
- **Jinja2**: HTML 템플릿 렌더링
- **feedparser**: RSS 피드 파싱
- **requests**: HTTP 요청
- **BeautifulSoup4**: HTML 파싱
- **wordcloud**: 워드클라우드 생성
- **Streamlit**: 관리자 대시보드
- **SQLite**: API 사용량 로깅

## 유지보수 가이드
- **기능 추가 시**: 새로운 기능이나 데이터 소스가 추가되면 반드시 `templates/guide.html` 내용을 최신화하여 방문자에게 정확한 정보를 제공해야 합니다.
- **서비스 가이드 재빌드**: `python rebuild_all_html.py` 실행 시 자동으로 가이드 페이지도 재생성됩니다.

## 라이선스
MIT License © 2024 VAAX
