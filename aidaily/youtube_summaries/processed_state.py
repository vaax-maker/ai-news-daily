"""Local durable published-video history; never access Drive at runtime."""
from __future__ import annotations
import fcntl
import hashlib
import json
import os
import tempfile
import warnings
from datetime import datetime, timezone
from pathlib import Path
from aidaily import config

class ProcessedStateError(RuntimeError):
    pass

def state_path() -> Path:
    values=[Path(os.environ[k]).expanduser().resolve() for k in
            ('YOUTUBE_SUMMARIES_STATE','YOUTUBE_SUMMARIES_PROCESSED_LOG') if os.environ.get(k)]
    if len(set(values))>1:
        raise ProcessedStateError('Reader/writer processed-state overrides disagree')
    path=values[0] if values else (config.DATA_ROOT/'youtube_summaries/processed-video-ids.json').resolve()
    if '/Library/CloudStorage/' in str(path) or '/Google Drive/' in str(path):
        raise ProcessedStateError('Processed-video runtime state must be outside cloud-synced storage')
    return path

def _receipt_dir(path: Path) -> Path:
    return path.parent/(path.stem+'-receipts')

def _ids(value, source):
    if not isinstance(value,dict) or not isinstance(value.get('processed_video_ids'),list):
        raise ProcessedStateError('Invalid processed-video state: '+str(source))
    ids=value['processed_video_ids']
    if any(not isinstance(v,str) or not v.strip() for v in ids):
        raise ProcessedStateError('Invalid video ID in '+str(source))
    return set(ids)

def _read(path):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError) as error:
        raise ProcessedStateError('Cannot read processed-video state: '+str(path)) from error

def _load(path, *, require_initialized=True):
    ids=set();initialized=False
    if path.exists():ids|=_ids(_read(path),path);initialized=True
    for receipt in sorted(_receipt_dir(path).glob('*.json')):
        data=_read(receipt)
        if not isinstance(data,dict):raise ProcessedStateError('Invalid publication receipt: '+str(receipt))
        if data.get('status')!='published':continue
        ids|=_ids(data,receipt);initialized=True
    if require_initialized and not initialized:
        raise ProcessedStateError('Processed-video state needs explicit migration; refusing empty dedup')
    return ids

def load_processed_ids() -> set[str]:
    path=state_path();path.parent.mkdir(parents=True,exist_ok=True)
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_SH)
        return _load(path)

def _atomic_write(path: Path, value: dict):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.'+path.name+'.',suffix='.new',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
        os.replace(name,path)
        directory=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:
        try:os.unlink(name)
        except FileNotFoundError:pass

def initialize(video_ids, *, sources=()):
    """Explicit migration only. Keep all IDs and any existing local history."""
    ids=_ids({'processed_video_ids':list(video_ids)},'migration')
    path=state_path();path.parent.mkdir(parents=True,exist_ok=True)
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        ids|=_load(path,require_initialized=False)
        value={'schema':1,'processed_video_ids':sorted(ids),'total_processed':len(ids),
               'last_run':datetime.now(timezone.utc).isoformat(),'migration_sources':list(sources)}
        _atomic_write(path,value)
    return value

def record_published(video_ids, publication_date, slugs=()):
    """Call only after confirmed Git publication. Two local durability paths."""
    new=_ids({'processed_video_ids':list(video_ids)},'publication')
    path=state_path();path.parent.mkdir(parents=True,exist_ok=True)
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        existing=_load(path)  # Corrupt/missing history must not silently disappear.
        key=hashlib.sha256(json.dumps([publication_date,sorted(new)],sort_keys=True).encode()).hexdigest()
        receipt=_receipt_dir(path)/(key+'.json');now=datetime.now(timezone.utc).isoformat()
        event={'status':'published','date':publication_date,'processed_video_ids':sorted(existing|new),'new_video_ids':sorted(new),'slugs':list(slugs),'recorded_at':now}
        receipt_ok=state_ok=False;errors=[]
        try:_atomic_write(receipt,event);receipt_ok=True
        except OSError as error:errors.append('receipt:'+type(error).__name__)
        ids=existing|new
        value={'schema':1,'processed_video_ids':sorted(ids),'total_processed':len(ids),'last_run':now}
        try:_atomic_write(path,value);state_ok=True
        except OSError as error:errors.append('state:'+type(error).__name__)
        if not state_ok and not receipt_ok:
            raise ProcessedStateError('Both local processed-state and publication receipt failed: '+','.join(errors))
        status='complete' if state_ok and receipt_ok else 'receipt_only' if receipt_ok else 'state_only'
        if status!='complete':warnings.warn('Processed history '+status+'; durable local recovery retained; '+','.join(errors),RuntimeWarning)
        return {'status':status,'path':str(path),'receipt':str(receipt) if receipt_ok else None,'total_processed':len(ids),'warnings':errors}
