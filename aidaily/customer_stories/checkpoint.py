"""Private daily checkpoint: freeze inputs and candidate before an async evaluator."""
from pathlib import Path
from contextlib import contextmanager
import fcntl
import json
import os
import re
from aidaily.integrations import openrouter

class Checkpoint:
    def __init__(self,path):
        self.path=path
        self.state=json.loads(path.read_text()) if path.exists() else {}
        if self.state and self.state.get('version')!=1:
            raise openrouter.RoutingBlocked('Unknown customer checkpoint version')
    def save(self,**fields):
        self.state.update(version=1,**fields)
        temp=self.path.with_suffix('.new')
        with temp.open('w') as f:
            os.chmod(temp,0o600);json.dump(self.state,f,ensure_ascii=False);f.flush();os.fsync(f.fileno())
        temp.replace(self.path)
        fd=os.open(self.path.parent,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
    def restart(self):
        if self.state and self.state.get('stage')!='complete':
            raise openrouter.RoutingBlocked('Unfinished customer run must be resumed first')
        if self.state:
            import time
            self.path.replace(self.path.with_name(self.path.stem+'.'+str(time.time_ns())+'.completed.json'))
            self.state={}

@contextmanager
def locked(data_dir,date):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',date):raise ValueError('Invalid customer run date')
    folder=Path(data_dir)/'checkpoints';folder.mkdir(mode=0o700,parents=True,exist_ok=True)
    with (folder/(date+'.lock')).open('a') as f:
        os.chmod(f.name,0o600);fcntl.flock(f,fcntl.LOCK_EX)
        yield Checkpoint(folder/(date+'.json'))

def unfinished_date(data_dir,requested):
    """Resume earlier unfinished daily work before collecting a new day's input."""
    folder=Path(data_dir)/'checkpoints'
    if not folder.exists():return requested
    candidates=[]
    for p in folder.glob('*.json'):
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}\.json',p.name) or p.stem>requested:continue
        state=json.loads(p.read_text())
        if state and state.get('stage') not in {'complete','review'}:candidates.append(p.stem)
    return min(candidates) if candidates else requested
