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
from typing import List, Set


def load_exclusion_patterns() -> Set[str]:
    """
    Load exclusion patterns from exclusion-list.txt in repo root.
    Returns a set of patterns to exclude from indexing.
    Handles missing file gracefully by returning empty set.
    """
    exclusion_file = Path("search-context/exclusion-list.txt")
    patterns = set()

    if not exclusion_file.exists():
        print("  ℹ️  No exclusion list found (this is fine)", file=sys.stderr)
        return patterns

    try:
        with open(exclusion_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if line and not line.startswith('#'):
                    patterns.add(line)

        if patterns:
            print(f"  📋 Loaded {len(patterns)} exclusion patterns", file=sys.stderr)
            for pattern in sorted(patterns):
                print(f"     - {pattern}", file=sys.stderr)
        else:
            print("  ℹ️  Exclusion list is empty (all directories will be indexed)", file=sys.stderr)
    except Exception as e:
        print(f"  ⚠️  Warning: Could not read exclusion list: {e}", file=sys.stderr)

    return patterns


def is_excluded(store_name: str, exclusion_patterns: Set[str]) -> bool:
    """
    Check if a store name matches any exclusion pattern.

    Supports two pattern types:
    1. Exact match: "archived" matches store "archived"
    2. Prefix match: "temp/*" matches any store starting with "temp/"

    Args:
        store_name: The store/directory name to check (e.g., "context" or "Factory-AI/factory")
        exclusion_patterns: Set of exclusion patterns

    Returns:
        True if store should be excluded, False otherwise
    """
    for pattern in exclusion_patterns:
        # Exact match
        if store_name == pattern:
            return True

        # Prefix match with wildcard (e.g., "archived/*")
        if pattern.endswith('/*'):
            prefix = pattern[:-2]  # Remove the /*
            if store_name.startswith(prefix + '/') or store_name == prefix:
                return True

    return False


def get_indexable_stores(docs_path, max_depth=2):
    """
    Find all indexable documentation directories.
    Only includes directories with files at their root level.
    Skips empty namespace containers.
    Applies exclusion patterns from .context-sync/exclusion-list.txt.
    """
    indexable = []
    exclusion_patterns = load_exclusion_patterns()

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

            # Check exclusion patterns
            if is_excluded(store_name, exclusion_patterns):
                print(f"  🚫 Excluded: {store_name} (matches exclusion pattern)", file=sys.stderr)
            else:
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
