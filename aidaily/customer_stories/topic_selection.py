"""Deterministic, auditable selection over a complete classified collection.

The caller must establish collection completeness; this module cannot verify it.
It never accepts or returns message text. One message may support multiple topics,
so topic counts can overlap; each message contributes only once to the denominator.
"""
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from uuid import UUID


class SelectionInputError(ValueError):
    """The selection cannot be computed reliably from the supplied input."""


@dataclass(frozen=True)
class SelectionConfig:
    overall_minimum: str = '0.30'
    source_minimum: str = '0.30'
    minimum_topic_messages: int = 3
    minimum_source_messages: int = 3
    maximum_topics: int = 2


def _fraction(value, name):
    if isinstance(value, bool):
        raise SelectionInputError(f'{name} must be a number in [0,1]')
    try:
        value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise SelectionInputError(f'{name} must be a number in [0,1]') from None
    if not value.is_finite() or not 0 <= value <= 1:
        raise SelectionInputError(f'{name} must be a number in [0,1]')
    return value


def _id(value, name):
    try:
        parsed = UUID(value) if isinstance(value, str) else None
    except (ValueError, AttributeError):
        parsed = None
    if parsed is None or parsed.version != 4 or str(parsed) != value:
        raise SelectionInputError(f'{name} must be an opaque lowercase UUIDv4')
    return value


def _instant(value, name):
    if not isinstance(value, str):
        raise SelectionInputError(f'{name} must be a timezone-aware ISO datetime')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise SelectionInputError(f'{name} must be a timezone-aware ISO datetime') from None
    if parsed.utcoffset() is None:
        raise SelectionInputError(f'{name} must be a timezone-aware ISO datetime')
    return parsed.astimezone(timezone.utc)


def select_topics(sources, assignments, config=None):
    """Select topics from explicit complete source receipts and classifications.

    sources: iterable of {source_id, complete: True, unit, window_start,
    window_end, message_ids: [str, ...]}. All units and time windows must match.
    assignments: dict mapping every collected message ID to an object containing
    status='reviewed' and topic_ids list; an empty list means no matching topic.
    Any failure, unreviewed or unknown status blocks selection. All IDs must be
    randomly generated UUIDv4; syntax validation cannot establish randomness.
    Result contains only opaque topic/source IDs, counts, thresholds and decisions.
    Raises SelectionInputError instead of reporting false zero for invalid inputs.
    """
    config = config or SelectionConfig()
    if not isinstance(config, SelectionConfig):
        raise SelectionInputError('config must be SelectionConfig')
    overall = _fraction(config.overall_minimum, 'overall_minimum')
    per_source = _fraction(config.source_minimum, 'source_minimum')
    for field in ('minimum_topic_messages', 'minimum_source_messages', 'maximum_topics'):
        v = getattr(config, field)
        if isinstance(v, bool) or not isinstance(v, int) or v < 1:
            raise SelectionInputError(f'{field} must be a positive integer')
    if config.maximum_topics > 2:
        raise SelectionInputError('maximum_topics cannot exceed two')
    if not isinstance(sources, (list, tuple)) or not sources:
        raise SelectionInputError('at least one source receipt is required')
    if not isinstance(assignments, dict):
        raise SelectionInputError('assignments must be a dictionary')

    source_totals, message_sources = {}, {}
    common_unit = common_window = None
    for source in sources:
        if not isinstance(source, dict):
            raise SelectionInputError('invalid source receipt')
        sid = _id(source.get('source_id'), 'source_id')
        if sid in source_totals:
            raise SelectionInputError('duplicate source_id')
        if source.get('complete') is not True:
            raise SelectionInputError('incomplete collection')
        unit = source.get('unit')
        if unit not in ('message', 'post', 'comment'):
            raise SelectionInputError('unit must be message, post or comment')
        start = _instant(source.get('window_start'), 'window_start')
        end = _instant(source.get('window_end'), 'window_end')
        if start >= end:
            raise SelectionInputError('window_start must precede window_end')
        if common_unit is None:
            common_unit, common_window = unit, (start, end)
        elif unit != common_unit or (start, end) != common_window:
            raise SelectionInputError('all source units and time windows must match')
        ids = source.get('message_ids')
        if not isinstance(ids, (list, tuple)):
            raise SelectionInputError('message_ids must be a list')
        source_totals[sid] = len(ids)
        for mid in ids:
            _id(mid, 'message_id')
            if mid in message_sources:
                raise SelectionInputError('duplicate message_id')
            message_sources[mid] = sid
    if not message_sources:
        raise SelectionInputError('empty collection cannot establish a proportion')
    if set(assignments) != set(message_sources):
        raise SelectionInputError('assignments must cover exactly the collected message IDs')

    totals, per_topic_source = Counter(), {}
    for mid, assignment in assignments.items():
        if not isinstance(assignment, dict) or assignment.get('status') != 'reviewed':
            raise SelectionInputError('every classification must have reviewed status')
        topics = assignment.get('topic_ids')
        if not isinstance(topics, (list, tuple)):
            raise SelectionInputError('each assignment must be a topic ID list')
        seen = set()
        for topic in topics:
            _id(topic, 'topic_id')
            if topic in seen:
                raise SelectionInputError('duplicate topic assignment for one message')
            seen.add(topic)
            totals[topic] += 1
            per_topic_source.setdefault(topic, Counter())[message_sources[mid]] += 1

    total = len(message_sources)
    results = []
    for topic, count in totals.items():
        source_counts = per_topic_source[topic]
        qualifying = sorted(sid for sid, n in source_counts.items()
                            if source_totals[sid] >= config.minimum_source_messages
                            and Decimal(n) >= per_source * source_totals[sid])
        reasons = []
        if count < config.minimum_topic_messages:
            reasons.append('below_minimum_topic_messages')
        if Decimal(count) < overall * total:
            reasons.append('below_overall_threshold')
        if not qualifying:
            reasons.append('no_qualifying_source')
        eligible = not reasons
        results.append({'topic_id': topic, 'message_count': count,
                        'denominator': total,
                        'source_counts': {sid: {'count': source_counts.get(sid, 0),
                                                'denominator': source_totals[sid]}
                                          for sid in sorted(source_totals)},
                        'qualifying_sources': qualifying, 'eligible': eligible,
                        'ineligibility_reasons': reasons})
    # Tie-breaking is explicit and stable even when input order changes.
    results.sort(key=lambda row: (-row['message_count'], row['topic_id']))
    selected = [row['topic_id'] for row in results if row['eligible']][:config.maximum_topics]
    return {'total_messages': total, 'source_totals': dict(sorted(source_totals.items())),
            'unit': common_unit,
            'window_start': common_window[0].isoformat(),
            'window_end': common_window[1].isoformat(),
            'config': {'overall_minimum': str(overall), 'source_minimum': str(per_source),
                       'minimum_topic_messages': config.minimum_topic_messages,
                       'minimum_source_messages': config.minimum_source_messages,
                       'maximum_topics': config.maximum_topics},
            'topics': results, 'selected_topic_ids': selected,
            'selection_status': ('no_classified_topics' if not results else
                                 'no_eligible_topics' if not selected else
                                 'fewer_than_maximum' if len(selected) < config.maximum_topics else
                                 'maximum_selected')}
