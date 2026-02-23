from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List

@dataclass
class ParsedContent:
    title: str
    source: str
    date: Optional[str]
    content: str
    keywords: List[str]
    related_links: List[str]

class BaseParser(ABC):
    @abstractmethod
    def can_parse(self, url: str) -> bool:
        pass

    @abstractmethod
    def parse(self, url: str) -> ParsedContent:
        pass

    def parse_with_fallback(self, url: str, fallback_content: str = "") -> ParsedContent:
        """예외 발생 시 빈 ParsedContent 반환."""
        try:
            return self.parse(url)
        except Exception as e:
            return ParsedContent(
                title=url,
                source=url,
                date=None,
                content=fallback_content or f"[Parse error: {e}]",
                keywords=[],
                related_links=[],
            )
