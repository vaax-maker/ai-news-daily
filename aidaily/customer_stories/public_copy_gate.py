"""Conservative public-copy review gate; not a formal anonymization guarantee.

Rejects overt identifiers and apparent verbatim reuse of private input. Personal
names, indirect identification and semantic rephrasing still need editorial review.
Only known prose fields are inspected; evidence IDs and link URLs are not prose.
"""
from __future__ import annotations
import re
import unicodedata


class PublicCopyReviewRequired(ValueError):
    """Copy needs editorial review; error deliberately contains no source text."""
    def __init__(self, reason):
        self.reason = reason
        super().__init__('public_copy_review_required:' + reason)


_EMAIL = re.compile(r'(?<![\w.+-])[\w.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?!\w)')
_HANDLE = re.compile(r'(?<![\w.])@[A-Za-z0-9_]{2,}\b')
_MOBILE = re.compile(r'(?<!\d)(?:(?:\+?82)[ .-]?)?0?1[016789][ .-]?\d{3,4}[ .-]?\d{4}(?!\d)')
_LANDLINE = re.compile(r'(?<!\d)0(?:2|[3-6][1-5]|70|80|50[2-8])[ .-]\d{3,4}[ .-]\d{4}(?!\d)')
_LONG_ID = re.compile(r'(?<![A-Za-z0-9])\d{10,}(?![A-Za-z0-9])')
_LABELLED_ID = re.compile(r'(?:chat|room|message|log|방|대화|메시지)[ _-]*(?:id|아이디|식별자)[\s:=#-]*\d{5,}',re.I)
_ITEM_TEXT = ('issue', 'dek', 'commentary', 'title', 'overview', 'service', 'model', 'conditions', 'source', 'label')
_ROW_TEXT = ('text', 'label', 'source', 'stage', 'date')


def _normalize(value):
    value = unicodedata.normalize('NFKC', value).casefold()
    return ''.join(ch for ch in value if ch.isalnum())


def _meaningful(value):
    return sum(ch.isalpha() for ch in value) >= 8 and len(set(value)) >= 4


def _prose(report):
    if not isinstance(report,dict) or not isinstance(report.get('items'),list):
        raise PublicCopyReviewRequired('invalid_report')
    for key in ('title','overview','edition_note'):
        value=report.get(key)
        if value is not None:
            if not isinstance(value,str):raise PublicCopyReviewRequired('invalid_prose')
            yield value
    for item in report['items']:
        if not isinstance(item,dict):raise PublicCopyReviewRequired('invalid_item')
        for key in _ITEM_TEXT:
            value=item.get(key)
            if value is not None:
                if not isinstance(value,str):raise PublicCopyReviewRequired('invalid_prose')
                yield value
        sources=item.get('sources',[])
        if not isinstance(sources,list):raise PublicCopyReviewRequired('invalid_prose')
        for value in sources:
            if not isinstance(value,str):raise PublicCopyReviewRequired('invalid_prose')
            yield value
        for key in ('background','voices','timeline','related_links'):
            rows=item.get(key,[])
            if not isinstance(rows,list):raise PublicCopyReviewRequired('invalid_prose')
            for row in rows:
                if not isinstance(row,dict):raise PublicCopyReviewRequired('invalid_prose')
                for field in _ROW_TEXT:
                    value=row.get(field)
                    if value is not None:
                        if not isinstance(value,str):raise PublicCopyReviewRequired('invalid_prose')
                        yield value


def validate_public_copy(report,dossier,allow_anonymous_quotes=True):
    """Return None when no overt issue is found; otherwise require review.

    A private normalized span of >=24 characters is treated as possible copied
    source text. A meaningful private source of 12..23 characters is checked as
    an entire source string. Whitespace/punctuation changes cannot evade matching.
    This is a conservative review signal, not proof of copying or deidentification.
    """
    if not isinstance(dossier,dict) or not isinstance(dossier.get('evidence'),list):
        raise PublicCopyReviewRequired('invalid_dossier')
    # Owner policy 2026-11-06: anonymous verbatim quotes are allowed; overt
    # identifiers (email/phone/handle/ID) stay blocked. Pass False to re-enable.
    long_spans=set();short_sources=set()
    for row in dossier['evidence']:
        if not isinstance(row,dict):raise PublicCopyReviewRequired('invalid_evidence')
        private=row.get('private')
        # Missing private flags must be treated conservatively when text exists.
        # Public web evidence is explicitly private=False in the rolling collector.
        if private is False:continue
        text=row.get('text')
        if not isinstance(text,str):raise PublicCopyReviewRequired('private_evidence_has_no_text')
        normalized=_normalize(text)
        if not _meaningful(normalized):continue
        if 12<=len(normalized)<24:short_sources.add(normalized)
        elif len(normalized)>=24:
            long_spans.update(normalized[i:i+24]for i in range(len(normalized)-23))
    for text in _prose(report):
        text = unicodedata.normalize('NFKC',text)
        if _EMAIL.search(text):raise PublicCopyReviewRequired('email_in_prose')
        if _MOBILE.search(text) or _LANDLINE.search(text):raise PublicCopyReviewRequired('phone_in_prose')
        if _HANDLE.search(text):raise PublicCopyReviewRequired('handle_in_prose')
        if _LONG_ID.search(text) or _LABELLED_ID.search(text):raise PublicCopyReviewRequired('identifier_in_prose')
        normalized=_normalize(text)
        if not allow_anonymous_quotes and any(source in normalized for source in short_sources):
            raise PublicCopyReviewRequired('possible_private_source_copy')
        if not allow_anonymous_quotes and long_spans and any(normalized[i:i+24]in long_spans for i in range(max(0,len(normalized)-23))):
            raise PublicCopyReviewRequired('possible_private_source_copy')
    return None
