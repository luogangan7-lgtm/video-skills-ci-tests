"""GitHub-only scoped history cleanup; invoked by history-cleanup.yml.

Depends on Git and pinned git-filter-repo. Preserves every non-target tree entry
and parent edge; only an explicit apply with a backed-up ref digest may publish.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

assert os.environ.get('GITHUB_ACTIONS') == 'true', 'GitHub CI only'
REPO = 'luogangan7-lgtm/video-skills-ci-tests'
assert os.environ['GITHUB_REPOSITORY'] == REPO
URL = f'https://github.com/{REPO}.git'
MEDIA = {'factory-presenter/assets/' + n for n in (
    'presenter-01.mp4', 'presenter-anchor.png', 'presenter-fixed.mp4',
    'presenter-handheld-anchor.png', 'presenter-handheld.mp4')}
PRODUCT = 'factory-presenter/assets/product.png'
PRODUCT_HASH = 'ee3db821975dba15127aa5e08b6793c37bbd9a9a124e6be13bf80feac634d349'
OUT = Path('history-out').resolve()
OUT.mkdir()
MODE = os.environ.get('CLEANUP_MODE', 'prepare')
assert MODE in ('prepare', 'apply')


def run(*args, cwd=None, env=None):
    return subprocess.check_output(args, cwd=cwd, env=env, timeout=180)


def git(repo, *args):
    return run('git', '-C', str(repo), *args)


def refs(repo):
    return dict(line.split(' ', 1)[::-1] for line in git(
        repo, 'for-each-ref', '--format=%(objectname) %(refname)',
        'refs/heads', 'refs/tags').decode().splitlines())


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def tree(repo, commit):
    return {p: meta for row in git(repo, 'ls-tree', '-r', '-z', commit).decode().split('\0')
            if row for meta, p in [row.split('\t', 1)]}


def commits(repo, heads):
    return git(repo, 'rev-list', '--topo-order', *heads.values()).decode().splitlines()


def parents(repo, commit):
    return git(repo, 'show', '-s', '--format=%P', commit).decode().strip().split()


def enforce(trees, forbidden):
    for c, entries in trees.items():
        assert MEDIA.isdisjoint(entries), f'Retired media path in {c}'
        assert all(meta.split()[-1] not in forbidden for meta in entries.values()), f'Retired blob in {c}'


mirror = Path('history-mirror.git').resolve()
run('git', 'clone', '--mirror', URL, str(mirror))
before_refs = refs(mirror)
before_refs_hash = digest(before_refs)
assert set(before_refs) <= {'refs/heads/main', 'refs/heads/test/model-free-skills',
                           'refs/heads/cleanup/factory-history-20261024'}, before_refs
assert 'refs/heads/main' in before_refs
all_refs = git(mirror, 'for-each-ref', '--format=%(objectname) %(refname)').decode()
before_commits = commits(mirror, before_refs)
before_trees = {c: tree(mirror, c) for c in before_commits}
before_parents = {c: parents(mirror, c) for c in before_commits}
before_messages = {c: git(mirror, 'show', '-s', '--format=%B', c) for c in before_commits}
forbidden = {meta.split()[-1] for entries in before_trees.values()
             for path, meta in entries.items() if path in MEDIA}
assert len(forbidden) >= 5, 'Expected historical target blobs missing'
assert all(entries.get(PRODUCT, '').split()[-1:] not in [[b] for b in forbidden]
           for entries in before_trees.values())
try:
    enforce(before_trees, forbidden)
except AssertionError:
    print('RED: original reachable history rejected by the exact same gate', flush=True)
else:
    raise AssertionError('Negative control did not fail')

if MODE == 'apply':
    assert os.environ['GITHUB_REF'] == 'refs/heads/main', 'Apply only from main'
    assert re.fullmatch(r'[0-9a-f]{64}', os.environ.get('BACKUP_SHA256', ''))
    assert before_refs_hash == os.environ.get('EXPECTED_REFS_SHA256'), 'Remote refs drifted since backup'
    assert before_refs['refs/heads/main'] == os.environ.get('EXPECTED_MAIN_SHA'), 'Main drifted'
    backup_dir = Path('verified-backup')
    saved = json.loads((backup_dir / 'backup.json').read_text())
    assert saved['refs'] == before_refs and saved['sha'] == os.environ['GITHUB_SHA']
    assert saved['repo'] == REPO and str(saved['run_id']) == os.environ['BACKUP_RUN_ID']
    assert hashlib.sha256((backup_dir / 'before.bundle').read_bytes()).hexdigest() == saved['bundle_sha256'] == os.environ['BACKUP_SHA256']
    git(mirror, 'bundle', 'verify', str((backup_dir / 'before.bundle').resolve()))
else:
    bundle = OUT / 'before.bundle'
    git(mirror, 'bundle', 'create', str(bundle), '--all')
    git(mirror, 'bundle', 'verify', str(bundle))
    backup_hash = hashlib.sha256(bundle.read_bytes()).hexdigest()
    (OUT / 'backup.json').write_text(json.dumps({
        'repo': REPO, 'run_id': os.environ['GITHUB_RUN_ID'],
        'sha': os.environ['GITHUB_SHA'], 'refs': before_refs,
        'refs_sha256': before_refs_hash, 'all_refs': all_refs,
        'bundle_sha256': backup_hash, 'bundle_bytes': bundle.stat().st_size}, indent=2))

# PR refs are server-owned. Backed up above, but never publish or claim to erase them.
for line in git(mirror, 'for-each-ref', '--format=%(refname)').decode().splitlines():
    if not line.startswith(('refs/heads/', 'refs/tags/')):
        git(mirror, 'update-ref', '-d', line)
blob_file = OUT / 'forbidden-blobs.txt'
blob_file.write_text('\n'.join(sorted(forbidden)) + '\n')
command = ['git', '-C', str(mirror), 'filter-repo', '--force', '--invert-paths',
           '--strip-blobs-with-ids', str(blob_file), '--prune-empty', 'never',
           '--prune-degenerate', 'never', '--preserve-commit-hashes']
for path in sorted(MEDIA):
    command += ['--path', path]
run(*command)
mapping = dict(line.split() for line in (mirror / 'filter-repo/commit-map').read_text().splitlines()[1:])
assert set(mapping) == set(before_commits), 'Unexpected commit coverage'
assert all(re.fullmatch(r'[0-9a-f]{40}', n) and n != '0' * 40 for n in mapping.values())
after_refs = refs(mirror)
assert set(after_refs) == set(before_refs)
assert all(after_refs[r] == mapping.get(old, old) for r, old in before_refs.items())
after_trees = {mapping[c]: tree(mirror, mapping[c]) for c in before_commits}
enforce(after_trees, forbidden)
for old, new in mapping.items():
    protected = {p: m for p, m in before_trees[old].items()
                 if p not in MEDIA and m.split()[-1] not in forbidden}
    assert protected == after_trees[new], f'Protected source changed: {old}'
    assert parents(mirror, new) == [mapping[p] for p in before_parents[old]], 'Parent graph changed'
    assert before_messages[old] == git(mirror, 'show', '-s', '--format=%B', new)
assert hashlib.sha256(git(mirror, 'show', f'{after_refs["refs/heads/main"]}:{PRODUCT}')).hexdigest() == PRODUCT_HASH
print('GREEN: all commit trees, parent edges, messages and product bytes preserved outside targets', flush=True)
report = {'status': 'CANDIDATE_PASS', 'repo': REPO, 'source_sha': os.environ['GITHUB_SHA'],
          'run_id': os.environ['GITHUB_RUN_ID'], 'mode': MODE, 'before_refs': before_refs,
          'before_refs_sha256': before_refs_hash, 'after_refs': after_refs,
          'commit_map': mapping, 'checked_commits': len(mapping), 'forbidden_paths': sorted(MEDIA),
          'forbidden_blobs': sorted(forbidden), 'product_sha256': PRODUCT_HASH,
          'protected_historical_trees_equal': True, 'parents_equal': True,
          'server_pr_refs_and_cached_objects': 'NOT_ERASED_READ_ONLY_GITHUB_LIMITATION'}
(OUT / 'report.json').write_text(json.dumps(report, indent=2))

if MODE == 'apply':
    # Ephemeral GITHUB_TOKEN stays in an env-only askpass helper; never in URLs or logs.
    askpass = Path(os.environ['RUNNER_TEMP']) / 'history-askpass.sh'
    askpass.write_text('#!/bin/sh\ncase "$1" in *Username*) echo x-access-token;; *) printf "%s\\n" "$GH_TOKEN";; esac\n')
    askpass.chmod(0o700)
    push_env = {**os.environ, 'GIT_ASKPASS': str(askpass), 'GIT_TERMINAL_PROMPT': '0'}
    try:
        args = ['git', '-C', str(mirror), 'push', '--atomic']
        args += [f'--force-with-lease={r}:{old}' for r, old in before_refs.items()]
        args += [URL] + [f'{r}:{r}' for r in before_refs]
        run(*args, env=push_env)
    finally:
        askpass.unlink(missing_ok=True)
    fresh = Path('history-fresh.git').resolve()
    run('git', 'clone', '--bare', URL, str(fresh))
    assert refs(fresh) == after_refs, 'Published refs mismatch'
    fresh_trees = {c: tree(fresh, c) for c in commits(fresh, after_refs)}
    enforce(fresh_trees, forbidden)
    assert fresh_trees == after_trees, 'Fresh-clone historical trees mismatch'
    assert hashlib.sha256(git(fresh, 'show', f'{after_refs["refs/heads/main"]}:{PRODUCT}')).hexdigest() == PRODUCT_HASH
    report.update(status='PUBLISHED_FRESH_CLONE_PASS', fresh_clone_refs=refs(fresh),
                  checked_fresh_commits=len(fresh_trees), backup_sha256=os.environ['BACKUP_SHA256'])
    (OUT / 'report.json').write_text(json.dumps(report, indent=2))
    print('PASS: published refs and fresh-clone full-history verification', flush=True)
