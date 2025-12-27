#!/usr/bin/env python3
"""
모든 템플릿 파일을 직접 수정하여 간소화된 액션 링크 적용
"""
import re

# 1. archive_index.html 수정
print("1. archive_index.html 수정 중...")
with open('templates/archive_index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# createNewsCard 함수를 완전히 교체
old_function = r'function createNewsCard\(article, extraMetaParts = \[\]\) \{.*?return card;\s+\}'
new_function = '''function createNewsCard(article, extraMetaParts = []) {
        const card = document.createElement('article');
        card.className = 'news-item';

        // 1. Header Section
        const header = document.createElement('div');
        header.className = 'news-header';

        const title = document.createElement('h3');
        title.className = 'news-title';
        const link = document.createElement('a');
        link.href = article.link;
        link.target = '_blank';
        link.textContent = article.title;
        title.appendChild(link);
        
        // Inline actions
        const inlineActions = document.createElement('span');
        inlineActions.className = 'inline-actions';
        
        const discussLink = document.createElement('a');
        discussLink.href = `../board/index.html?mode=discuss&title=${encodeURIComponent(article.title)}&link=${encodeURIComponent(article.link)}&source=${encodeURIComponent(article.source || '출처')}`;
        discussLink.className = 'action-link';
        discussLink.textContent = '토론';
        inlineActions.appendChild(discussLink);
        
        const separator = document.createElement('span');
        separator.className = 'action-separator';
        separator.textContent = '|';
        inlineActions.appendChild(separator);
        
        const shareBtn = document.createElement('button');
        shareBtn.className = 'action-link action-button';
        shareBtn.textContent = '공유';
        shareBtn.onclick = () => {
            navigator.clipboard.writeText(article.link)
                .then(() => alert('링크가 클립보드에 복사되었습니다!'))
                .catch(() => alert('복사 실패'));
        };
        inlineActions.appendChild(shareBtn);
        
        title.appendChild(inlineActions);

        const meta = document.createElement('div');
        meta.className = 'news-meta';
        const metaParts = [...extraMetaParts];
        if (article.source) metaParts.push(`<span class='source-link'>${article.source}</span>`);
        if (article.published) metaParts.push(article.published);
        meta.innerHTML = metaParts.join(' · ');

        header.appendChild(title);
        header.appendChild(meta);
        card.appendChild(header);

        // 2. Body Section
        const body = document.createElement('div');
        body.className = 'news-body';

        if (article.image) {
            const thumb = document.createElement('div');
            thumb.className = 'news-image';
            const img = document.createElement('img');
            img.src = article.image;
            img.alt = 'thumbnail';
            img.loading = 'lazy';
            thumb.appendChild(img);
            body.appendChild(thumb);
        }

        const summary = document.createElement('div');
        summary.className = 'news-summary';
        summary.innerHTML = article.summary;
        body.appendChild(summary);

        card.appendChild(body);

        return card;
    }'''

content = re.sub(old_function, new_function, content, flags=re.DOTALL)

with open('templates/archive_index.html', 'w', encoding='utf-8') as f:
    f.write(content)
print("✓ archive_index.html 완료")

# 2. gov_archive.html 수정 - 테이블 버튼
print("\n2. gov_archive.html 수정 중...")
with open('templates/gov_archive.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 이모지 제거
content = content.replace('💬', '토론')
content = content.replace('🔗', '공유')  
content = content.replace('📑', '')

# 원문 버튼 td 제거 (정확한 패턴 매칭)
content = re.sub(r'<td class="col-discuss">\s*<a[^>]*class="discuss-btn-sm source-btn"[^>]*>.*?</a>\s*</td>\s*', '', content, flags=re.DOTALL)

with open('templates/gov_archive.html', 'w', encoding='utf-8') as f:
    f.write(content)
print("✓ gov_archive.html 완료")

# 3. member_page.html 수정
print("\n3. member_page.html 수정 중...")
with open('templates/member_page.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 이모지 제거 및 간소화
content = content.replace('💬', '')
content = content.replace('🔗', '')
content = content.replace('📑', '')
content = re.sub(r'class="action-btn discuss-btn"[^>]*>\s*💬?\s*</a>', 'class="action-link">토론</a>', content)
content = re.sub(r'class="action-btn share-btn"[^>]*>\s*🔗?\s*</button>', 'class="action-link action-button">공유</button>', content)
content = re.sub(r'<a href=".*?" target="_blank".*?class="action-btn source-btn".*?📑.*?</a>\s*', '', content, flags=re.DOTALL)

# news-actions를 간단한 div로 교체
content = re.sub(
    r'<div class="news-actions"[^>]*>',
    '<div style="margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid #e2e8f0; font-size: 0.8rem;">',
    content
)

with open('templates/member_page.html', 'w', encoding='utf-8') as f:
    f.write(content)
print("✓ member_page.html 완료")

# 4. member_index.html 수정
print("\n4. member_index.html 수정 중...")
with open('templates/member_index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 이모지 제거 및 간소화
content = content.replace('💬', '')
content = content.replace('🔗', '')
content = content.replace('📑', '')
content = re.sub(r'class="action-btn discuss-btn"[^>]*>\s*💬?\s*</a>', 'class="action-link">토론</a>', content)
content = re.sub(r'class="action-btn share-btn"[^>]*>\s*🔗?\s*</button>', 'class="action-link action-button">공유</button>', content)
content = re.sub(r'<a href=".*?" target="_blank".*?class="action-btn source-btn".*?</a>\s*', '', content, flags=re.DOTALL)

# news-actions를 간단한 div로 교체
content = re.sub(
    r'<div class="news-actions"[^>]*>',
    '<div style="margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid #e2e8f0; font-size: 0.8rem;">',
    content
)

# action-separator 추가가 누락된 경우를 위해
content = re.sub(r'(</a>)\s*(<button)', r'\1\n                        <span class="action-separator">|</span>\n                        \2', content)

with open('templates/member_index.html', 'w', encoding='utf-8') as f:
    f.write(content)
print("✓ member_index.html 완료")

print("\n✨ 모든 템플릿 파일 업데이트 완료!")
