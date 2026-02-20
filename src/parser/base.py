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
