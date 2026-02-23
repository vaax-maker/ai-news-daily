#!/usr/bin/env python3
"""CLI: URL을 분석하여 ParsedContent를 JSON으로 출력.

사용법:
    python scripts/analyze_url.py <url>

예시:
    python scripts/analyze_url.py https://example.com
    python scripts/analyze_url.py https://www.youtube.com/watch?v=dQw4w9WgXcQ

의존성: requirements-extra.txt
"""
import sys
import json

from src.url_analyzer import analyze_url


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/analyze_url.py <url>", file=sys.stderr)
        sys.exit(1)
    url = sys.argv[1]
    result = analyze_url(url)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
