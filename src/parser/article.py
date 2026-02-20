import requests
from bs4 import BeautifulSoup
from datetime import datetime
from src.parser.base import BaseParser, ParsedContent
from typing import List

class ArticleParser(BaseParser):
    def can_parse(self, url: str) -> bool:
        return True
    
    def parse(self, url: str) -> ParsedContent:
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; VAAXBot/1.0)'}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        title = self._extract_title(soup)
        source = self._extract_source(soup, url)
        date = self._extract_date(soup)
        content = self._extract_content(soup)
        related_links = self._extract_links(soup, url)
        
        return ParsedContent(
            title=title,
            source=source,
            date=date,
            content=content,
            keywords=self._extract_keywords(title, content),
            related_links=related_links
        )
    
    def _extract_title(self, soup: BeautifulSoup) -> str:
        for selector in ['meta[property="og:title"]', 'meta[name="twitter:title"]', 'h1', 'title']:
            tag = soup.select_one(selector)
            if tag:
                if tag.has_attr('content'):
                    return str(tag['content']).strip()
                else:
                    return (tag.get_text() if hasattr(tag, 'get_text') else str(tag)).strip()
        return 'Untitled'
    
    def _extract_source(self, soup: BeautifulSoup, url: str) -> str:
        og_site = soup.find('meta', property='og:site_name')
        if og_site and og_site.get('content'):
            return str(og_site.get('content'))
        from urllib.parse import urlparse
        return urlparse(url).netloc
    
    def _extract_date(self, soup: BeautifulSoup) -> str:
        for selector in ['meta[property="article:published_time"]', 'meta[name="date"]', 'time']:
            tag = soup.select_one(selector)
            if tag:
                date_str = str(tag.get('content', tag.get('datetime', '')))
                try:
                    dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    return dt.strftime('%Y-%m-%d')
                except Exception:
                    return date_str[:10] if isinstance(date_str, str) else ''
        return ""
    
    def _extract_content(self, soup: BeautifulSoup) -> str:
        for tag in soup(['script', 'style', 'nav', 'header', 'footer']):
            tag.decompose()
        article = soup.find('article') or soup.find('main')
        if article:
            text = article.get_text(separator=' ', strip=True)
        else:
            text = soup.body.get_text(separator=' ', strip=True) if soup.body else ''
        return ' '.join(text.split())
    
    def _extract_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        from urllib.parse import urljoin
        links: List[str] = []
        for a in soup.select('a[href]')[:5]:
            href = str(a['href'])
            full_url = urljoin(base_url, href)
            if full_url not in links:
                links.append(full_url)
        return links
    
    def _extract_keywords(self, title: str, content: str) -> List[str]:
        words = (title + ' ' + content).lower().split()
        stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'what', 'which', 'who', 'whom', 'where', 'when', 'why', 'how', 'all', 'each', 'every', 'both', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very', 'just'}
        keywords = [w for w in set(words) if len(w) > 2 and w not in stopwords]
        return sorted(keywords)[:10]
