#!/usr/bin/env python3
"""
Detect changed documentation directories for incremental sync.

Behavior:
- Reads env: DOCS_PATH (default 'docs'), MAX_DEPTH (default 2), LAST_SYNC_DOCS_COMMIT.
- If LAST_SYNC_DOCS_COMMIT is unset: full discovery of indexable stores (directories
  with ≥1 non-hidden file at their own root), honoring MAX_DEPTH and skipping hidden
  dirs/files. Output JSON list.
- If set: First run a sanity check inside DOCS_PATH: `git cat-file -e <sha>^{commit}`.
  If it fails, log warning and fall back to full discovery (do NOT crash the workflow).
  Otherwise run `git diff --name-only <sha>..HEAD` (cwd=DOCS_PATH) and map changed
  file paths to indexable stores precisely: store considered changed when the path
  equals store or starts with store + '/'. Ignore .github/ and any path segment
  starting with '.'.
- Write the JSON list to stdout. Also emit to GITHUB_OUTPUT as a multiline var
  named changed_dirs.
"""

import os
import sys
import json
import subprocess
from pathlib import Path


def get_indexable_stores(docs_path, max_depth=2):
    """
    Find all indexable documentation directories.
    Only includes directories with files at their root level.
    Skips empty namespace containers.
    """
    indexable = []

    def scan_directory(path: Path, depth=0, prefix=""):
        if depth > max_depth:
            return
        try:
            entries = [p for p in path.iterdir() if not p.name.startswith('.')]
        except FileNotFoundError:
            return

        files_at_root = sum(1 for f in entries if f.is_file())

        if files_at_root > 0:
            store_name = f"{prefix}{path.name}" if prefix else path.name
            indexable.append(store_name)
            print(f"  ✅ Indexable: {store_name} ({files_at_root} files at root)", file=sys.stderr)
        else:
            print(f"  ⏭️  Skipping: {prefix}{path.name} (0 files at root, checking subdirs)", file=sys.stderr)
            subdirs = [d for d in entries if d.is_dir()]
            for subdir in subdirs:
                new_prefix = f"{prefix}{path.name}/" if prefix or depth > 0 else f"{path.name}/"
                scan_directory(subdir, depth + 1, new_prefix)

    root = Path(docs_path)
    if not root.exists():
        # Idempotent guard: return empty list if DOCS_PATH doesn't exist
        return []

    for item in root.iterdir():
        if item.is_dir() and not item.name.startswith('.'):
            scan_directory(item, depth=0)

    return indexable


def write_github_output(key, value):
    """
    Write output to GITHUB_OUTPUT using multiline heredoc format.
    Format: key<<EOF_KEY\nvalue\nEOF_KEY\n
    """
    github_output = os.environ.get('GITHUB_OUTPUT')
    if github_output:
        with open(github_output, 'a') as f:
            f.write(f'{key}<<EOF_{key.upper()}\n')
            f.write(f'{value}\n')
            f.write(f'EOF_{key.upper()}\n')


def main():
    docs_path = os.environ.get('DOCS_PATH', 'docs')
    max_depth = int(os.environ.get('MAX_DEPTH', '2'))
    last_commit = os.environ.get('LAST_SYNC_DOCS_COMMIT', '')

    if not last_commit:
        print("First (or full) sync - scanning all directories", file=sys.stderr)
        all_stores = get_indexable_stores(docs_path, max_depth)
        changed_dirs_json = json.dumps(all_stores)
    else:
        # Sanity check: verify the recorded SHA exists in the docs repo
        print(f"Checking if commit {last_commit} exists in {docs_path}...", file=sys.stderr)
        try:
            subprocess.run(
                ['git', 'cat-file', '-e', f'{last_commit}^{{commit}}'],
                cwd=docs_path,
                check=True,
                capture_output=True,
                text=True
            )
            print(f"  ✅ Commit {last_commit} exists", file=sys.stderr)
        except subprocess.CalledProcessError:
            print(f"  ⚠️  WARNING: Commit {last_commit} not found in docs repo", file=sys.stderr)
            print("  Falling back to full discovery", file=sys.stderr)
            all_stores = get_indexable_stores(docs_path, max_depth)
            changed_dirs_json = json.dumps(all_stores)
            print(changed_dirs_json)
            write_github_output('changed_dirs', changed_dirs_json)
            return

        # Get changed files since last sync (explicit double-dot range)
        try:
            result = subprocess.run(
                ['git', 'diff', '--name-only', f'{last_commit}..HEAD'],
                cwd=docs_path,
                capture_output=True,
                text=True,
                check=True
            )
        except subprocess.CalledProcessError as e:
            print(f"  ❌ git diff failed: {e}", file=sys.stderr)
            all_stores = get_indexable_stores(docs_path, max_depth)
            changed_dirs_json = json.dumps(all_stores)
            print(changed_dirs_json)
            write_github_output('changed_dirs', changed_dirs_json)
            return

        changed_files = [l.strip() for l in result.stdout.split('\n') if l.strip()]
        if not changed_files:
            print("No changes since last sync", file=sys.stderr)
            changed_dirs_json = json.dumps([])
        else:
            # Get all indexable stores first
            all_stores = get_indexable_stores(docs_path, max_depth)
            # Map changed files to stores with precise prefix matching
            changed_stores = set()
            for file_path in changed_files:
                # Skip .github paths and any hidden segment
                parts = file_path.split('/')
                if parts[0].startswith('.github') or any(p.startswith('.') for p in parts):
                    continue
                for store in all_stores:
                    if file_path == store or file_path.startswith(store + '/'):
                        changed_stores.add(store)
                        break
            changed_stores_list = sorted(changed_stores)
            visible_changed_count = sum(
                1 for f in changed_files
                if not f.startswith('.github/') and not any(p.startswith('.') for p in f.split('/'))
            )
            print(f"Changed files considered: {visible_changed_count}", file=sys.stderr)
            print(f"Filtered to indexable changed stores: {changed_stores_list}", file=sys.stderr)
            changed_dirs_json = json.dumps(changed_stores_list)

    print(changed_dirs_json)
    write_github_output('changed_dirs', changed_dirs_json)


if __name__ == '__main__':
    main()
