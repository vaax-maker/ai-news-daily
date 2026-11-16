"""Conservative XR title evidence and bounded daily selection ordering."""
import re

_XR=re.compile(r'(?i)(?<![a-z0-9])(?:xr|vr|ar|psvr2?|oculus)(?![a-z0-9])|virtual\s+reality|augmented\s+reality|mixed\s+reality|spatial\s+computing|vision\s+pro|steam\s+frame|xreal\s+aura|meta\s+quest|quest\s*(?:2|3s?|pro)\b|가상현실|증강현실|혼합현실|확장현실|공간\s*컴퓨팅|메타\s*퀘스트|비전\s*프로|브이알|엑스알')

def is_xr(video):
    """Require explicit XR terminology in the title; channel name alone is insufficient."""
    return bool(_XR.search(str(video.get('source_title') or video.get('title') or '')))

def prioritize(videos,limit):
    """Reserve one slot for a verified XR candidate while preserving original order."""
    unique=[];seen=set()
    for video in videos:
        vid=video.get('video_id')
        if not vid or vid in seen:continue
        seen.add(vid);unique.append(video)
    if limit<=0:return []
    first=next((v for v in unique if is_xr(v)),None)
    return ([first] if first else [])+[v for v in unique if v is not first][:limit-(1 if first else 0)]


def pin_first_xr(rows):
    """Move the first title-evidenced XR row forward; preserve all other order."""
    result=list(rows)
    for index,row in enumerate(result):
        if is_xr(row):
            if index:result.insert(0,result.pop(index))
            break
    return result
