#!/usr/bin/env python3
"""Stage anonymous PV hooks in existing published HTML, then explicitly publish.

Never generates content, mutates runtime repositories, or sends notifications.
Prepare: python deploy/enable_pv_existing.py --stage-dir /private/tmp/aidaily-pv-stage
Publish (only after collector readiness): ... --stage-dir SAME --publish
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aidaily.publishing.engagement import collector_url, instrument_html


def git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True, timeout=180)
    if result.returncode:
        # Git diagnostics can contain credential-bearing remote URLs.
        raise RuntimeError('Git operation failed: ' + args[0])
    return result.stdout.strip()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def paths(root):
    return [name for name in git(root, 'diff', '--name-only', '-z').split('\0') if name]


def validate_endpoint(endpoint):
    parsed = urlsplit(endpoint)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError('An HTTPS collector endpoint without credentials is required')
    return endpoint


def prepare(stage, endpoint, sources):
    if stage.exists() and any(stage.iterdir()):
        raise ValueError('Stage directory must be new or empty; use existing manifest with --publish')
    stage.mkdir(parents=True, exist_ok=True)
    manifest = {'version': 1, 'endpoint': endpoint, 'preparation_complete': False, 'repositories': []}
    for key, source, scope in sources:
        remote = git(source, 'remote', 'get-url', '--push', 'origin')
        clone = stage / key
        result = subprocess.run(['git', 'clone', '--quiet', '--depth', '1', '--filter=blob:none', '--no-checkout', '--single-branch', '--branch', 'main', '--', remote, str(clone)], capture_output=True, text=True, timeout=180)
        if result.returncode:
            raise RuntimeError('Clone failed for ' + key)
        git(clone, 'config', 'core.sparseCheckout', 'true')
        (clone / '.git/info/sparse-checkout').write_text('/docs/*.html\n/docs/**/*.html\n' if scope else '/*.html\n/**/*.html\n')
        git(clone, 'checkout', '--quiet', 'main')
        tracked = git(clone, 'ls-files', '-z').split('\0')
        candidates = [name for name in tracked if name.lower().endswith('.html') and (not scope or name.startswith(scope + '/'))]
        modifications = []
        for name in candidates:
            target = clone / name
            if target.is_symlink() or not target.is_file():
                continue
            before = target.read_text(encoding='utf-8')
            after = instrument_html(before, endpoint=endpoint)
            if after != before:
                target.write_text(after, encoding='utf-8')
                modifications.append({'path': name, 'sha256': sha(target)})
        entry = {'name': key, 'branch': 'main', 'scope': scope, 'base': git(clone, 'rev-parse', 'HEAD'), 'scanned_html': len(candidates), 'files': modifications, 'status': 'prepared'}
        manifest['repositories'].append(entry)
        (stage / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
        print(json.dumps({k: entry[k] for k in ['name','branch','scanned_html']} | {'changed_html': len(modifications)}, ensure_ascii=False))
    manifest['preparation_complete'] = True
    (stage / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    return manifest



def restage(stage, endpoint=''):
    """Reinstrument clean previously published clones while preserving commits."""
    manifest_path = stage / 'manifest.json'
    previous = json.loads(manifest_path.read_text())
    endpoint = validate_endpoint(endpoint or collector_url() or previous['endpoint'])
    # Validate every repository before modifying any file.
    for entry in previous['repositories']:
        clone = stage / entry['name']
        if entry.get('status') not in ('pushed', 'unchanged') or git(clone, 'status', '--porcelain'):
            raise RuntimeError('Restage requires clean, successfully published repositories')
        git(clone, 'fetch', '--quiet', 'origin', entry['branch'])
        if git(clone, 'rev-parse', 'HEAD') != git(clone, 'rev-parse', 'FETCH_HEAD'):
            raise RuntimeError('Remote changed since prior publication; prepare a fresh stage')
    import datetime
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    (stage / ('manifest.history.'+stamp+'.json')).write_text(manifest_path.read_text())
    manifest = {'version': 1, 'endpoint': endpoint, 'preparation_complete': False, 'repositories': []}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    for old in previous['repositories']:
        clone = stage / old['name']
        tracked = git(clone, 'ls-files', '-z').split('\0')
        scope = old['scope']
        candidates = [name for name in tracked if name.lower().endswith('.html') and (not scope or name.startswith(scope+'/'))]
        modifications = []
        for name in candidates:
            target = clone / name
            if target.is_symlink() or not target.is_file():
                continue
            before = target.read_text(encoding='utf-8')
            after = instrument_html(before, endpoint=endpoint)
            if after != before:
                target.write_text(after, encoding='utf-8')
                modifications.append({'path': name, 'sha256': sha(target)})
        entry = {'name': old['name'], 'branch': old['branch'], 'scope': scope, 'base': git(clone, 'rev-parse', 'HEAD'), 'scanned_html': len(candidates), 'files': modifications, 'status': 'prepared'}
        manifest['repositories'].append(entry)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
        print(json.dumps({'name': entry['name'], 'branch': entry['branch'], 'base': entry['base'], 'changed_html': len(modifications)}))
    manifest['preparation_complete'] = True
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    return manifest


def publish(stage):
    manifest_path = stage / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    validate_endpoint(manifest['endpoint'])
    if not manifest.get('preparation_complete'):
        raise RuntimeError('Preparation did not finish for every repository')
    for entry in manifest['repositories']:
        if entry.get('status') == 'pushed':
            print(entry['name'] + ': already pushed; skipped')
            continue
        clone = stage / entry['name']
        expected = {f['path'] for f in entry['files']}
        if not expected:
            entry['status'] = 'unchanged'
            continue
        if git(clone, 'rev-parse', 'HEAD') != entry.get('commit', entry['base']):
            raise RuntimeError('Stage HEAD changed; do not overwrite or retry blindly')
        if not entry.get('commit'):
            if set(paths(clone)) != expected or git(clone, 'diff', '--cached', '--name-only') or git(clone, 'ls-files', '--others', '--exclude-standard'):
                raise RuntimeError('Stage contains changes outside the reviewed HTML set')
            for item in entry['files']:
                name = item['path']
                if not name.endswith('.html') or '..' in Path(name).parts or (entry['scope'] and not name.startswith(entry['scope']+'/')):
                    raise ValueError('Non-HTML or out-of-scope publication rejected')
                target = clone / name
                if target.is_symlink() or sha(target) != item['sha256']:
                    raise RuntimeError('Reviewed HTML changed')
            git(clone, 'add', '--', *sorted(expected))
            git(clone, '-c', 'user.name=AI Daily', '-c', 'user.email=aifoundry01@gmail.com', 'commit', '--quiet', '-m', 'Enable anonymous page view collection on existing pages')
            entry['commit'] = git(clone, 'rev-parse', 'HEAD')
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
        # No force, rebase, regeneration, or automatic retry on uncertain push.
        git(clone, 'push', 'origin', 'HEAD:'+entry['branch'])
        entry['status'] = 'pushed'
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
        print(json.dumps({'name':entry['name'],'commit':entry['commit'],'changed_html':len(expected),'status':'pushed'}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage-dir', required=True, type=Path)
    parser.add_argument('--endpoint', default='')
    parser.add_argument('--aidaily-repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--news-repo', type=Path, default=Path.home()/'Sites/ai-infographic')
    parser.add_argument('--restage', action='store_true', help='Reinstrument clean previously published clones, without pushing')
    parser.add_argument('--publish', action='store_true', help='Explicitly push only previously prepared HTML')
    args = parser.parse_args()
    stage = args.stage_dir.resolve()
    if args.publish and args.restage:
        parser.error('--publish and --restage are separate operations')
    if args.publish:
        publish(stage)
    elif args.restage:
        restage(stage, args.endpoint)
    else:
        prepare(stage, validate_endpoint(args.endpoint or collector_url()), [('aidaily',args.aidaily_repo,'docs'),('news',args.news_repo,'')])

if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as error:
        print('PV instrumentation stopped: '+('Git subprocess failed or timed out; remote details withheld' if isinstance(error, subprocess.SubprocessError) else str(error)), file=sys.stderr)
        sys.exit(1)
