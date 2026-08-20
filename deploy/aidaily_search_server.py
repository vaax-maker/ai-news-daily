#!/usr/bin/env python3
"""aidaily 통합검색 정적 서버 (포트 8096, funnel /aidaily-search 뒤).

기존 `python -m http.server`는 Cache-Control을 안 보내 브라우저가 search.html·search-index.json을
휴리스틱 캐싱 → 갱신 후에도 하드새로고침으로 안 지워지는 문제(2026-08-21). 매 응답에 no-store를
붙여 항상 최신본을 받게 한다. docroot = ~/ai-news-daily-beacon/docs.
"""
import http.server
import os
import socketserver

DOCROOT = os.path.expanduser("~/ai-news-daily-beacon/docs")
PORT = 8096


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=DOCROOT, **k)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


if __name__ == "__main__":
    with Server(("127.0.0.1", PORT), NoCacheHandler) as httpd:
        httpd.serve_forever()
