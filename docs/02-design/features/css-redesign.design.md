# [Design] css-redesign (v2)

> 참조 플랜: `docs/01-plan/features/css-redesign.plan.md` (v2)
> **핵심**: 라임(`#65a30d`) = 유일한 액센트. 나머지 전부 무채색.

---

## 구현 순서

---

### STEP 1 — `style.css` : CSS 변수 교체

`:root` 블록(lines 9–29)을 아래로 교체.

```css
:root {
    --primary-color:       #65a30d;   /* 라임 — 유지 */
    --primary-color-hover: #4d7c0f;   /* 진라임 — 유지 */
    --background-color:    #f5f5f5;   /* 변경: 흰→연회색 */
    --card-bg:             #ffffff;
    --text-main:           #111111;
    --text-muted:          #555555;
    --border-color:        #e0e0e0;
    --line-gray:           #e0e0e0;
}
```

---

### STEP 2 — `style.css` : body 배경 변수화

```css
/* body 선택자에 추가/수정 */
body {
    background: var(--background-color);
}
```

---

### STEP 3 — `style.css` : 슬로건 하이라이트 통일

```css
/* 현재 */
.slogan-highlight { color: #84cc16; }

/* 변경 */
.slogan-highlight { color: var(--primary-color); }
```

---

### STEP 4 — `style.css` : 로고 흑백 처리

```css
/* 추가 */
.header-logo {
    filter: grayscale(1);
}
```

---

### STEP 5 — `style.css` : 파랑 계열 제거

| 선택자 | 속성 | 현재 | 변경 |
|--------|------|------|------|
| `.run-count` | color | `#2563eb` | `var(--text-muted)` |
| `.pill` | background | `rgba(37,99,235,0.1)` | `rgba(0,0,0,0.07)` |
| `.pill` | color | `var(--primary-color)` | `var(--text-main)` |
| `.tile-member-badge` | background | `rgba(37,99,235,0.1)` | `rgba(0,0,0,0.07)` |
| `.tile-member-badge` | color | `var(--primary-color)` | `var(--text-main)` |
| `.modal-run:hover` | background | `rgba(37,99,235,0.08)` | `rgba(0,0,0,0.05)` |
| `.calendar-cell.active` | box-shadow | `rgba(37,99,235,0.15)` | `rgba(0,0,0,0.15)` |

---

### STEP 6 — `style.css` : 초록·연두 계열 제거

| 선택자 | 속성 | 현재 | 변경 |
|--------|------|------|------|
| `.calendar-cell.has-articles` | background | `#e6f8d7` | `#eeeeee` |
| `.calendar-cell.has-articles` | border-color | `#b9e3a0` | `#cccccc` |
| `.highlight` | background | `#e5f7da` | `#f0f0f0` |

---

### STEP 7 — `style.css` : 이미지 플레이스홀더 단색화

```css
/* 현재 */
.image-placeholder.ai { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
.image-placeholder.xr { background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); }
.tile-placeholder.ai  { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
.tile-placeholder.xr  { background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); }

/* 변경 */
.image-placeholder.ai { background: #333333; }
.image-placeholder.xr { background: #555555; }
.tile-placeholder.ai  { background: #333333; }
.tile-placeholder.xr  { background: #555555; }
```

---

### STEP 8 — `style.css` : 뉴스 제목 색상

뉴스 제목 색상은 primary-color(라임) 대신 텍스트 기본색으로 변경 —
라임을 유일한 액센트로 살리기 위해 제목에서는 제거.

```css
/* 현재 */
.news-title { color: var(--primary-color); }
.news-card-title a { color: var(--primary-color); }

/* 변경 */
.news-title { color: var(--text-main); }
.news-card-title a { color: var(--text-main); }
```

---

### STEP 9 — `style.css` : 기타 하드코딩 통일

| 선택자 | 속성 | 현재 | 변경 |
|--------|------|------|------|
| `th` | background | `#f1f5f9` | `#f5f5f5` |
| `.month-header` | background | `#f1f5f9` | `#f5f5f5` |
| `.weekday-row` | background | `#f8fafc` | `#f5f5f5` |
| `tr:hover` | background | `#f8fafc` | `#f7f7f7` |
| `.ghost-btn.subtle` | background | `#f8fafc` | `#f5f5f5` |
| `.modal-run` | background | `#f8fafc` | `#f5f5f5` |
| `.tile-image` | background | `#f1f5f9` | `#f0f0f0` |
| `.meaning-box` | background | `#f3f6fb` | `#f5f5f5` |
| `.meaning-box` | border-left | `var(--line-gray)` | `#cccccc` |
| `.col-count` | color | `var(--primary-color)` | `var(--text-main)` |
| `.tile-source` | color | `var(--primary-color)` | `var(--text-muted)` |
| `.source-link` | color | `var(--primary-color)` | `var(--text-muted)` |
| `.eyebrow` | color | `var(--primary-color)` | `var(--text-muted)` |
| `.summary-section-title` | color | `var(--primary-color)` | `var(--text-main)` |
| `.section-more` | color | `var(--primary-color)` | `var(--text-muted)` |
| `.wordcloud-legend` | color | `#555` | `var(--text-muted)` |
| `.news-summary` | color | `#1f2937` | `var(--text-main)` |

> **유지**: `.weekday-row .weekend` `#e02424`, `.header-announcement` `#ef4444` (기능적 빨강)

---

### STEP 10 — `style.css` : box-shadow 제거

```
제거 대상:
  .dashboard-section   { box-shadow: 0 1px 3px rgba(0,0,0,0.05) }
  .news-item           { box-shadow: 0 6px 16px rgba(0,0,0,0.06) }
  .card                { box-shadow: 0 10px 30px rgba(15,23,42,0.05) }
  .news-image img      { box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1) }
  .member-news-tile:hover  { box-shadow 제거 + transform 제거 }

경량화 (유지):
  .modal-body          → 0 4px 12px rgba(0,0,0,0.12)
  .run-popover         → 0 2px 8px rgba(0,0,0,0.08)
```

---

### STEP 11 — `style.css` : border-radius 4px 통일

| 선택자 | 현재 | 변경 |
|--------|------|------|
| `.dashboard-section` | `8px` | `4px` |
| `.news-item` | `10px` | `4px` |
| `.news-image img` | `12px` | `4px` |
| `.card` | `12px` | `4px` |
| `.member-news-tile` | `10px` | `4px` |
| `.table-responsive` | `10px` | `4px` |
| `.styled-table` | `10px` | `4px` |
| `.month-block` | `10px` | `4px` |
| `.calendar-cell` | `8px` | `3px` |
| `.pill` | `999px` | `3px` |
| `.search-bar input` | `10px` | `4px` |
| `.search-bar .primary-btn` | `10px` | `4px` |
| `.ghost-btn` | `10px` | `4px` |
| `.modal-body` | `14px` | `6px` |
| `.run-popover` | `14px` | `6px` |
| `.modal-run` | `10px` | `4px` |
| `.meaning-box` | `8px` | `4px` |
| `.news-card` | `10px` | `4px` |
| `.news-card-thumb img` | `8px` | `4px` |
| 모바일 카드 tr (member, gov) | `10px` | `4px` |

---

### STEP 12 — `style.css` : 간격 축소

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
| `.member-directory-section` | padding-top | `2rem` | `1rem` |
| `.meaning-box` | padding | `0.75rem 1rem` | `0.5rem 0.75rem` |
| `.meaning-box` | margin-top | `0.75rem` | `0.4rem` |
| `.table-responsive` | margin-bottom | `2rem` | `1rem` |

---

### STEP 13 — `style.css` : 타이포그래피

| 선택자 | 속성 | 현재 | 변경 |
|--------|------|------|------|
| `body` | line-height | `1.6` | `1.5` |
| `.news-summary` | line-height | `1.75` | `1.6` |
| `.news-summary` | font-size | clamp(1-1.08rem) | `0.9rem` |
| `h1` | font-size | clamp(1.6-2rem) | clamp(1.4-1.75rem) |
| `.news-title` | font-size | clamp(1.15-1.5rem) | clamp(1-1.2rem) |
| `.dashboard-section h2` | font-size | clamp(1.2-1.4rem) | clamp(1.05-1.2rem) |
| `.tile-title` | font-size | `0.95rem` | `0.875rem` |

---

### STEP 14 — `admin.html` : 인라인 스타일 교체

| 위치 | 현재 | 변경 |
|------|------|------|
| YouTube 분석 버튼 background | `#65a30d` | `var(--primary-color)` |
| YouTube h3 color | `#4d7c0f` | `var(--text-main)` |
| 웹쉐어 섹션 배경 | `background: #ecfdf5; border: 1px solid #10b981` | `background: var(--card-bg); border: 1px solid var(--border-color)` |
| 웹쉐어 h3 color | `#047857` | `var(--text-main)` |
| 웹쉐어 버튼 background | `#10b981` | `var(--primary-color)` |
| checkbox accent-color | `#10b981` | `var(--primary-color)` |
| 레이블 color | `#047857` | `var(--text-muted)` |
| 결과박스 border | `1px solid #10b981` | `1px solid var(--border-color)` |
| 결과박스 텍스트 color | `#047857` | `var(--text-muted)` |
| URL 링크 color | `#0369a1` | `var(--primary-color)` |
| `<h1 style="color:#111827">` | `#111827` | `var(--text-main)` |

---

### STEP 15 — `board/index.html` : 내부 `<style>` 블록 교체

board/index.html의 `<style>` 태그 내:

| 현재 | 변경 |
|------|------|
| `color: #667eea` | `color: var(--text-muted)` |
| `color: #2563eb !important` | `color: var(--primary-color) !important` |

---

### STEP 16 — `xr/index.html` 확인

grep으로 비무채색 확인 후 잔존시 교체.

---

## 변경 파일 목록

```
docs/static/css/style.css      ← 주요 변경 (Steps 1–13)
docs/admin.html                ← 인라인 스타일 교체 (Step 14)
docs/board/index.html          ← <style> 블록 교체 (Step 15)
docs/xr/index.html             ← 확인 후 필요시 (Step 16)
docs/index.html                ← 이미 var() 사용 중, 확인만
```

---

## 검증 기준 (Definition of Done)

```
grep 0건 확인:
  style.css     : #2563eb #667eea #764ba2 #84cc16 #10b981 #047857
                  #ecfdf5 #11998e #38ef7d rgba(37,99,235,*)
  admin.html    : #10b981 #047857 #ecfdf5 #0369a1 #4d7c0f
  board/*.html  : #667eea #2563eb

유지 확인:
  style.css     : --primary-color: #65a30d 존재
  .slogan-highlight : color: var(--primary-color) 사용
  .header-logo  : filter: grayscale(1) 추가됨

시각 확인:
  라임그린 외 유채색 전 페이지 미노출
  로고 흑백 처리
  뉴스 목록 밀도 향상 (기존 대비 +30% 아이템 가시)
  모바일 375px 가독성 이상 없음
```
