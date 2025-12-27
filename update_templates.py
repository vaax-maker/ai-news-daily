#!/usr/bin/env python3
"""
템플릿 파일들을 한 번에 업데이트: 토론/공유만 유지, 이모지 제거, 제목 옆으로 이동
"""

# daily_list.html 업데이트
daily_list_new = '''{% extends "layout.html" %}

{% block title %}{{ date_str }} {{ category_display_name }} News{% endblock %}

{% block extra_css %}{% endblock %}

{% block content %}
<h1>{{ date_str }} {{ category_display_name }} News</h1>
<p class="subtitle">Updated at {{ time_str }} (KST)</p>

<section class="item-list">
    {% for article in articles %}
    <article class="news-item">
        <div class="news-header">
            <h2 class="news-title">
                <a href="{{ article.link }}" target="_blank">{{ article.title }}</a>
                <span class="inline-actions">
                    <a href="../board/index.html?mode=discuss&title={{ article.title|urlencode }}&link={{ article.link|urlencode }}&source={{ article.source_name|urlencode }}" 
                       class="action-link">토론</a>
                    <span class="action-separator">|</span>
                    <button onclick="navigator.clipboard.writeText('{{ article.link }}').then(() => alert('링크가 클립보드에 복사되었습니다!')).catch(() => alert('복사 실패'))" 
                            class="action-link action-button">공유</button>
                </span>
            </h2>
            <div class="news-meta">
                <a href="{{ article.link }}" target="_blank" class="source-link">{{ article.source_name }}</a>
                <span class="published-date">{{ article.published_display }}</span>
            </div>
        </div>

        <div class="news-body">
            {% if article.image_url %}
            <div class="news-image">
                <img src="{{ article.image_url }}" alt="Thumbnail" loading="lazy">
            </div>
            {% elif article.placeholder_type %}
            <div class="news-image">
                <div class="image-placeholder {{ article.placeholder_type }}">
                    {{ article.placeholder_type|upper }}
                </div>
            </div>
            {% endif %}

            <div class="news-summary">
                {{ article.summary_html | safe }}
            </div>
        </div>
    </article>
    {% endfor %}
</section>
{% endblock %}
'''

# CSS 업데이트 (inline-actions 스타일)
css_inline_actions = '''
/* 인라인 액션 링크 (제목 옆) */
.inline-actions {
    margin-left: 1rem;
    font-size: 0.85rem;
    font-weight: 500;
    white-space: nowrap;
}

.action-link {
    color: var(--primary-color);
    text-decoration: none;
    cursor: pointer;
    transition: opacity 0.2s;
    background: none;
    border: none;
    padding: 0;
    font-family: inherit;
    font-size: inherit;
    font-weight: inherit;
}

.action-link:hover {
    opacity: 0.7;
    text-decoration: underline;
}

.action-separator {
    margin: 0 0.5rem;
    color: var(--text-muted);
}

/* 모바일 반응형 */
@media (max-width: 768px) {
    .inline-actions {
        display: block;
        margin-left: 0;
        margin-top: 0.5rem;
        font-size: 0.8rem;
    }
}
'''

print("템플릿 파일 업데이트 중...")

# 1. daily_list.html 업데이트
with open('templates/daily_list.html', 'w', encoding='utf-8') as f:
    f.write(daily_list_new)
print("✓ daily_list.html 업데이트 완료")

# 2. CSS 파일에 inline-actions 스타일 추가 (기존 discussion feature styles 교체)
with open('static/css/style.css', 'r', encoding='utf-8') as f:
    css_content = f.read()

# Discussion Feature Styles 섹션 찾아서 교체
import re
pattern = r'/\* ===================================\s+Discussion Feature Styles\s+===================================.+?(?=/\*|$)'
replacement = f'''/* ===================================
   Discussion Feature Styles
   ==================================== */
{css_inline_actions}
/* 정부과제용 토론/공유 링크 (테이블 내) */
.col-discuss {{
    width: 60px;
    text-align: center;
}}

.discuss-btn-sm {{
    color: var(--primary-color);
    text-decoration: none;
    font-size: 0.85rem;
    font-weight: 500;
    background: none;
    border: none;
    padding: 0;
    cursor: pointer;
    transition: opacity 0.2s;
}}

.discuss-btn-sm:hover {{
    opacity: 0.7;
    text-decoration: underline;
}}

/* 토론 게시글 배지 */
.discuss-badge {{
    background: var(--primary-color);
    color: white;
    padding: 0.2rem 0.5rem;
    border-radius: 4px;
    font-size: 0.75rem;
    margin-right: 0.5rem;
    display: inline-block;
}}

/* 토론 게시글 배경색  */
.discussion-post {{
    background: linear-gradient(90deg, #f0fdf4 0%, white 100%);
}}

'''

css_content = re.sub(pattern, replacement, css_content, flags=re.DOTALL)

with open('static/css/style.css', 'w', encoding='utf-8') as f:
    f.write(css_content)
print("✓ style.css 업데이트 완료")

print("\n✨ 모든 템플릿 업데이트 완료!")
