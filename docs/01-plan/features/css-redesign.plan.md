# [Plan] css-redesign  (v2 — 요구사항 업데이트)

## 변경 이력
- v1: 라임그린 제거 + 모노톤 전환 (초안)
- v2: **라임그린 유지** (유일한 하이라이트), 나머지 전부 무채색. 전 페이지 통일. 로고/슬로건 모노톤.

---

## 핵심 원칙

| 원칙 | 내용 |
|------|------|
| **유일한 액센트** | 라임그린(`#65a30d`) 1색만 허용. 파란·청록·보라 등 모든 비무채색 제거 |
| **모노톤 기반** | 나머지는 흰색·회색·검정 계열만 사용 |
| **전 페이지 통일** | style.css뿐 아니라 각 HTML의 인라인/내부 스타일도 교체 |
| **촘촘한 구성** | 패딩·간격을 약 40% 축소 |
| **미니멀** | 그림자 제거, border-radius 축소 |
| **로고·슬로건** | 로고 이미지 → CSS filter grayscale. 슬로건 하이라이트 → 라임 통일 |

---

## 현재 상태 분석 (As-Is)

### 제거 대상 색상 (비무채색)

| 파일 | 위치 | 색상 | 설명 |
|------|------|------|------|
| `style.css` | `:root` | `#65a30d` / `#4d7c0f` | primary/hover — **유지** |
| `style.css` | `.slogan-highlight` | `#84cc16` | 연라임 — `#65a30d`로 통일 |
| `style.css` | `.calendar-cell.has-articles` | `#e6f8d7` / `#b9e3a0` | 연두 배경 → 연회색 |
| `style.css` | `.run-count` | `#2563eb` | 파랑 → `var(--text-muted)` |
| `style.css` | `.pill`, `.tile-member-badge` | `rgba(37,99,235,0.1)` | 파랑 tint → `rgba(0,0,0,0.07)` |
| `style.css` | `.highlight` | `#e5f7da` | 연두 배경 → `#f0f0f0` |
| `style.css` | `.image-placeholder.ai/xr` | 보라·초록 그라디언트 | → `#333` / `#555` 단색 |
| `style.css` | `.modal-run:hover` | `rgba(37,99,235,0.08)` | 파랑 tint → `rgba(0,0,0,0.05)` |
| `style.css` | `.calendar-cell.active` | `rgba(37,99,235,0.15)` | 파랑 링 → `rgba(0,0,0,0.15)` |
| `admin.html` | 버튼 | `#65a30d` (라임) | → 유지 (단, `var(--primary-color)` 변수화) |
| `admin.html` | 웹쉐어 섹션 배경 | `#ecfdf5` / `#10b981` | 초록 → 무채색 |
| `admin.html` | 웹쉐어 텍스트 | `#047857` | 초록 → `var(--text-muted)` |
| `admin.html` | 웹쉐어 버튼 | `#10b981` | 초록 → `var(--primary-color)` |
| `admin.html` | accent-color | `#10b981` | 초록 → `var(--primary-color)` |
| `admin.html` | URL 링크 | `#0369a1` | 파랑 → `var(--primary-color)` |
| `admin.html` | YouTube h3 | `#4d7c0f` | 진라임 → `var(--text-main)` |
| `board/index.html` | `<style>` 블록 | `#667eea` (보라) | → `var(--text-muted)` |
| `board/index.html` | `<style>` 블록 | `#2563eb` (파랑) | → `var(--primary-color)` |

### 로고 / 슬로건 현황

| 요소 | 현재 | 목표 |
|------|------|------|
| `logo_new.png` | 컬러 이미지 | CSS `filter: grayscale(1)` 적용 |
| `.slogan-highlight` | `#84cc16` (연라임) | `var(--primary-color)` = `#65a30d`로 통일 |
| `.slogan-since` | `#9ca3af` (회색) | 유지 |
| `.header-slogan-text` | `var(--text-muted)` | 유지 |

---

## 목표 색상 시스템 (To-Be)

```
허용 색상
  #65a30d / #4d7c0f   ← 라임 (유일한 액센트)
  #ffffff              ← 카드·패널 표면
  #f5f5f5              ← 페이지 배경
  #f9f9f9 / #f0f0f0   ← 연회색 (th, alt 배경)
  #e0e0e0              ← 테두리
  #cccccc              ← 강조 테두리
  #111111              ← 주 텍스트
  #555555              ← 보조 텍스트
  #909090              ← 날짜·메타 텍스트
  #333333 / #555555   ← 이미지 플레이스홀더
  #e02424              ← 주말·공휴일 (기능적 빨강, 예외 유지)
  #ef4444              ← 긴급 공지 (기능적 빨강, 예외 유지)

제거 대상
  파란 계열 (#2563eb, #0369a1, #667eea, rgba(37,99,235,x))
  초록·청록 (#10b981, #047857, #11998e, #38ef7d, #ecfdf5, #e6f8d7, #b9e3a0)
  보라 계열 (#764ba2, #84cc16 외 라임계열)
  임의 연두 계열 (라임 아닌 #84cc16 → #65a30d 흡수)
```

### CSS 변수 갱신 내용

```css
:root {
    /* 유지 (라임 액센트) */
    --primary-color:       #65a30d;
    --primary-color-hover: #4d7c0f;

    /* 변경 */
    --background-color: #f5f5f5;  /* 흰 → 연회색 배경 */
    --card-bg:          #ffffff;  /* 유지 */
    --text-main:        #111111;
    --text-muted:       #555555;
    --border-color:     #e0e0e0;
    --line-gray:        #e0e0e0;
}
```

---

## 간격 축소 계획 (공통)

| 선택자 | 속성 | 현재 | 변경 |
|--------|------|------|------|
| `.dashboard-grid` | gap | `2rem` | `1.25rem` |
| `.dashboard-section` | padding | `1.5rem` | `1rem` |
| `.item-list` | gap | `1.5rem` | `0.75rem` |
| `.news-item` | padding | clamp(1.1-1.5rem) | `0.75rem 1rem` |
| `.news-item` | margin-bottom | clamp(1-1.25rem) | `0.5rem` |
| `.news-body` | gap | `1.5rem` | `0.75rem` |
| `.news-image img` | width | `240px` | `180px` |
| `.card` | padding | `1.5rem` | `1rem` |
| `.card` | margin-bottom | `1.5rem` | `0.75rem` |
| `.member-news-grid` | gap | `1.25rem` | `0.75rem` |
| `.tile-content` | padding | `0.9rem 1rem` | `0.6rem 0.75rem` |
| `.tile-image` | height | `140px` | `110px` |
| `.preview-list li` | padding | `0.75rem 0.25rem` | `0.45rem 0.15rem` |
| `.member-directory-section` | margin-top | `3rem` | `1.5rem` |

---

## 미니멀 시각 요소

| 항목 | 현재 | 변경 |
|------|------|------|
| 카드 box-shadow | 다수 | 제거 |
| 뉴스 아이템 box-shadow | `0 6px 16px` | 제거 |
| 타일 hover transform | translateY(-2px) | 제거 |
| modal box-shadow | `0 20px 40px` | `0 4px 12px rgba(0,0,0,0.12)` |
| 전체 border-radius | 8–14px | 4px 통일 |
| pill border-radius | 999px | 3px |

---

## 구현 대상 파일

| 파일 | 변경 내용 |
|------|-----------|
| `docs/static/css/style.css` | CSS 변수 + 컴포넌트 전체 |
| `docs/index.html` | 인라인 스타일 교체 (var() 사용) |
| `docs/admin.html` | 섹션 배경·버튼·텍스트 색상 (초록 → 무채색/라임) |
| `docs/board/index.html` | `<style>` 블록 내 파란·보라 색상 교체 |
| `docs/xr/index.html` | 확인 후 필요시 교체 |

---

## 타이포그래피 조정

| 항목 | 현재 | 변경 |
|------|------|------|
| line-height | `1.6` | `1.5` |
| news-summary line-height | `1.75` | `1.6` |
| news-summary font-size | clamp(1-1.08rem) | `0.9rem` |
| h1 clamp | 1.6-2rem | 1.4-1.75rem |
| news-title clamp | 1.15-1.5rem | 1-1.2rem |
| tile-title | `0.95rem` | `0.875rem` |

---

## 완료 기준

- [ ] style.css: `#2563eb`, `#667eea`, `#10b981`, `#047857`, `#ecfdf5`, `#11998e`, `#764ba2` 0건
- [ ] style.css: `#84cc16` 0건 (→ `#65a30d`로 통일)
- [ ] style.css: `box-shadow` 잔존 modal/popover 2곳만 (경량화)
- [ ] admin.html: `#10b981`, `#047857`, `#ecfdf5`, `#0369a1` 0건
- [ ] board/index.html: `#667eea`, `#2563eb` 0건
- [ ] 로고: `filter: grayscale(1)` 적용 확인
- [ ] 슬로건 `.slogan-highlight`: `var(--primary-color)` (#65a30d) 사용 확인
- [ ] 전 페이지 라임그린 외 유채색 미사용 시각 확인
- [ ] 모바일(375px) 가독성 이상 없음
