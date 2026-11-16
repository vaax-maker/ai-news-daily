"""Verify this publication's reports are reachable from the intended daily list."""
from pathlib import Path
from urllib.parse import urljoin, urlsplit, unquote
from html.parser import HTMLParser
from urllib.request import urlopen
from urllib.error import HTTPError
import argparse


class Links(HTMLParser):
    def __init__(self):
        super().__init__();self.targets=set()
    def handle_starttag(self, tag, attrs):
        if tag=='a':
            href=dict(attrs).get('href','')
            self.targets.add(href)


def verify(webroot, date, slugs, public_base=None):
    root=Path(webroot)
    def read(name):
        if public_base:
            with urlopen(urljoin(public_base.rstrip('/')+'/',name),timeout=30) as response:
                return response.read()
        return (root/name).read_bytes()
    lists={}
    for name in [f'{date}-daily-brief-ai.html',f'{date}-daily-brief-econ.html']:
        try:
            lists[name]=read(name).decode('utf-8')
        except (FileNotFoundError,HTTPError):
            continue
    if not lists:
        raise RuntimeError('No daily brief list exists for date: '+date)
    links=Links()
    for html in lists.values():links.feed(html)
    for slug in slugs:
        if Path(slug).name!=slug or not slug.startswith(date+'-'):
            raise RuntimeError('Report date differs from publication date: '+slug)
        base=(public_base or 'https://publication.invalid/news/').rstrip('/')+'/'
        expected=urlsplit(urljoin(base,slug+'.html'))
        def matches(href):
            actual=urlsplit(urljoin(base,href))
            return (actual.scheme,actual.netloc,unquote(actual.path)) == (expected.scheme,expected.netloc,unquote(expected.path))
        if not any(matches(href) for href in links.targets):
            raise RuntimeError('Published report missing from daily list: '+slug)
        report=read(slug+'.html')
        if b'<html' not in report.lower():raise RuntimeError('Invalid report HTML: '+slug)
        image=read('assets/ig/'+slug+'.jpg')
        if not image.startswith(b'\xff\xd8'):raise RuntimeError('Missing JPEG: '+slug)
    return True


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--webroot',required=True);p.add_argument('--date',required=True);p.add_argument('--public-base');p.add_argument('slugs',nargs='+');a=p.parse_args()
    verify(a.webroot,a.date,a.slugs,a.public_base)
    print('Publication membership, report and image verified for '+str(len(a.slugs))+' report(s)')
