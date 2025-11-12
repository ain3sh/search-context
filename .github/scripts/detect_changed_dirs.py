#!/usr/bin/env python3
"""
Detect changed documentation directories for FileSearchStore sync.

This script identifies which documentation directories have changes since the
last sync and need their FileSearchStores to be recreated.

Responsibilities:
- Read LAST_SYNC_COMMIT from environment (if absent, perform full discovery)
- Discover indexable stores: directories with ≥1 non-hidden file at root
- Run git diff --name-only LAST_SYNC_COMMIT..HEAD scoped to docs/
- Normalize changed file paths, ignore .github/, hidden files
- Map changed files to store directories precisely
- Output JSON list of changed directories to stdout

Usage:
    cd docs
    export LAST_SYNC_COMMIT=<commit-sha>  # Optional
    python detect_changed_dirs.py

Environment Variables:
    LAST_SYNC_COMMIT: Git commit SHA of the last sync (optional)
                      If not set, performs full discovery of all indexable stores

Output:
    JSON array of changed directory names (e.g., ["context", "Factory-AI/factory"])
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

    Args:
        docs_path: Path to the documentation root directory
        max_depth: Maximum depth to scan for stores (default: 2)

    Returns:
        List of indexable store names (relative paths)
    """
    indexable = []

    def scan_directory(path, depth=0, prefix=""):
        if depth > max_depth:
            return

        files_at_root = sum(
            1 for f in path.iterdir()
            if f.is_file() and not f.name.startswith('.')
        )

        if files_at_root > 0:
            store_name = f"{prefix}{path.name}" if prefix else path.name
            indexable.append(store_name)
            print(f"  ✅ Indexable: {store_name} ({files_at_root} files at root)", file=sys.stderr)
        else:
            print(f"  ⏭️  Skipping: {prefix}{path.name} (0 files at root, checking subdirs)", file=sys.stderr)
            subdirs = [
                d for d in path.iterdir()
                if d.is_dir() and not d.name.startswith('.')
            ]
            for subdir in subdirs:
                new_prefix = f"{prefix}{path.name}/" if prefix or depth > 0 else f"{path.name}/"
                scan_directory(subdir, depth + 1, new_prefix)

    for item in Path(docs_path).iterdir():
        if item.is_dir() and not item.name.startswith('.'):
            scan_directory(item, depth=0)

    return indexable


def detect_changed_directories():
    """
    Detect which documentation directories have changed since last sync.

    Returns:
        List of changed directory names
    """
    last_commit = os.environ.get('LAST_SYNC_COMMIT', '')

    if not last_commit:
        print("First (or full) sync - scanning all directories", file=sys.stderr)
        all_stores = get_indexable_stores('.')
        return all_stores

    # Get changed files since last sync
    try:
        result = subprocess.run(
            ['git', 'diff', '--name-only', last_commit, 'HEAD'],
            capture_output=True,
            text=True,
            check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"❌ Error running git diff: {e}", file=sys.stderr)
        print(f"   stdout: {e.stdout}", file=sys.stderr)
        print(f"   stderr: {e.stderr}", file=sys.stderr)
        sys.exit(1)

    changed_files = result.stdout.strip().split('\n')

    if not changed_files or changed_files == ['']:
        print("No changes since last sync", file=sys.stderr)
        return []

    # Normalize changed paths and filter out ignored patterns
    changed_paths = set()
    for file in changed_files:
        # Ignore .github/ changes
        if file.startswith('.github/'):
            continue

        # Ignore hidden files
        path_parts = file.split('/')
        if any(part.startswith('.') for part in path_parts):
            continue

        # Add top-level directory
        if path_parts:
            changed_paths.add(path_parts[0])

        # Add second-level directory (for nested stores)
        if len(path_parts) >= 2:
            changed_paths.add(f"{path_parts[0]}/{path_parts[1]}")

    # Get all indexable stores
    all_stores = get_indexable_stores('.')

    # Filter to only changed stores that are indexable
    changed_stores = [s for s in all_stores if s in changed_paths]

    print(f"Changed paths considered: {len(changed_paths)}", file=sys.stderr)
    print(f"Filtered to indexable changed stores: {changed_stores}", file=sys.stderr)

    return changed_stores


def main():
    """Main entry point."""
    try:
        changed_dirs = detect_changed_directories()
        # Output JSON to stdout for consumption by workflow
        print(json.dumps(changed_dirs))
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
