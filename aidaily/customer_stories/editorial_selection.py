"""Auditable newsroom candidate rules; counts are signals, never conversation shares.

Callers establish topic identity, source identity, research verification and history.
This pure module validates that contract, nominates at most two review candidates,
and never authorizes publication or claims that a source was independently checked.
"""
from dataclasses import asdict, dataclass
from datetime import date
from urllib.parse import urlsplit
import re


class EditorialInputError(ValueError):
    pass


@dataclass(frozen=True)
class EditorialConfig:
    minimum_observations: int = 2
    minimum_days: int = 2
    minimum_sources: int = 2
    maximum_topics: int = 2


def _id(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9:_-]{0,159}',value):
        raise EditorialInputError('expected an opaque ASCII identifier')
    return value


def _url(value):
    if not isinstance(value,str) or any(ord(c)<33 for c in value):
        return None
    try:
        p=urlsplit(value)
        if p.scheme not in ('http','https') or not p.hostname or p.username is not None or p.password is not None:
            return None
        p.port
    except ValueError:
        return None
    return value


def evaluate_candidates(topics, config=None):
    """Return editorial review candidates, not publication decisions.

    Topic fields: topic_id, observations, research, already_reported,
    new_development. Observation fields: evidence_id, date (ISO), source_id,
    kind (question/experience/promotion); already_published=False must be explicit
    for evidence used to justify a follow-up. Prior topics also need an explicit
    new_evidence_ids list. Research: url, verified: bool, primary: bool.
    Duplicate evidence IDs are invalid, including across topic assignments: callers
    must resolve topic identity rather than inflate two candidates with one report.
    """
    config=config or EditorialConfig()
    if not isinstance(config,EditorialConfig):
        raise EditorialInputError('invalid config')
    for name,value in asdict(config).items():
        if type(value) is not int or value<1:
            raise EditorialInputError('config values must be positive integers')
    if config.maximum_topics>2:
        raise EditorialInputError('maximum_topics cannot exceed two')
    if not isinstance(topics,list):
        raise EditorialInputError('topics must be a list')
    topic_ids, evidence_ids, results=set(),set(),[]
    for topic in topics:
        if not isinstance(topic,dict):
            raise EditorialInputError('invalid topic')
        tid=_id(topic.get('topic_id'))
        if tid in topic_ids:
            raise EditorialInputError('duplicate topic ID')
        topic_ids.add(tid)
        if any(type(topic.get(k)) is not bool for k in ('already_reported','new_development')):
            raise EditorialInputError('explicit history flags required')
        observations=topic.get('observations')
        research=topic.get('research')
        if not isinstance(observations,list) or not isinstance(research,list):
            raise EditorialInputError('observations and research must be lists')
        useful={}
        for obs in observations:
            if not isinstance(obs,dict):
                raise EditorialInputError('invalid observation')
            eid=_id(obs.get('evidence_id'))
            if eid in evidence_ids:
                raise EditorialInputError('duplicate evidence ID')
            evidence_ids.add(eid)
            _id(obs.get('source_id'))
            value=obs.get('date')
            try:
                if not isinstance(value,str) or date.fromisoformat(value).isoformat()!=value:
                    raise ValueError()
            except ValueError:
                raise EditorialInputError('invalid observation date') from None
            if obs.get('kind') not in ('question','experience','promotion'):
                raise EditorialInputError('invalid observation kind')
            if 'already_published' in obs and type(obs['already_published']) is not bool:
                raise EditorialInputError('invalid evidence history flag')
            if obs['kind']!='promotion':
                useful[eid]=obs
        grounded=[]
        for row in research:
            if not isinstance(row,dict) or any(type(row.get(k)) is not bool for k in ('verified','primary')):
                raise EditorialInputError('explicit research verification flags required')
            url=_url(row.get('url'))
            if url is None:
                raise EditorialInputError('invalid research URL')
            if row['verified'] and row['primary'] and url not in grounded:
                grounded.append(url)
        days={o['date'] for o in useful.values()}
        sources={o['source_id'] for o in useful.values()}
        repeated=len(useful)>=config.minimum_observations and (len(days)>=config.minimum_days or len(sources)>=config.minimum_sources)
        has_experience=any(o['kind']=='experience' for o in useful.values())
        kind='experience' if has_experience else 'explainer'
        reasons=[]
        if has_experience:
            if not grounded and not repeated:
                reasons.append('experience_needs_grounding_or_repetition')
        else:
            if not repeated:
                reasons.append('questions_need_repetition')
            if not grounded:
                reasons.append('questions_need_verified_primary_research')
        if topic['already_reported']:
            new=topic.get('new_evidence_ids')
            if not isinstance(new,list):
                new=[]
            if any(not isinstance(e,str) for e in new) or len(new)!=len(set(new)):
                raise EditorialInputError('invalid new evidence IDs')
            if any(e not in useful for e in new):
                raise EditorialInputError('new evidence must reference a nonpromotion observation')
            if not topic['new_development'] or not new or any(useful[e].get('already_published') is not False for e in new):
                reasons.append('previously_reported_without_new_evidence')
        results.append(dict(topic_id=tid,article_kind=kind,eligible=not reasons,
            reasons=reasons,observation_count=len(useful),distinct_days=len(days),
            distinct_sources=len(sources),evidence_ids=sorted(useful),
            verified_primary_urls=sorted(grounded),publication_allowed=False))
    results.sort(key=lambda r:(not r['eligible'],-r['distinct_days'],-r['distinct_sources'],-r['observation_count'],r['topic_id']))
    return dict(config=asdict(config),candidates=results,
        selected_topic_ids=[r['topic_id'] for r in results if r['eligible']][:config.maximum_topics],
        publication_allowed=False)
