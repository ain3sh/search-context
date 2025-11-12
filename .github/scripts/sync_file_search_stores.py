#!/usr/bin/env python3
"""
Sync FileSearchStores for changed documentation directories.

This script deletes and recreates FileSearchStores for directories that have
changed since the last sync. It handles file filtering, MDX conversion, parallel
uploads, and provides detailed progress reporting.

Responsibilities:
- Read CHANGED_DIRS from environment (JSON list)
- Delete and recreate FileSearchStores for changed directories
- Filter files by extension and size (skip empty/trivial files)
- Convert .mdx files to .md for upload compatibility
- Upload files in parallel with error handling
- Output sync summary statistics

Usage:
    export GEMINI_API_KEY=<your-api-key>
    export CHANGED_DIRS='["context", "Factory-AI/factory"]'
    python sync_file_search_stores.py

Environment Variables:
    GEMINI_API_KEY: Gemini API key (required)
    CHANGED_DIRS: JSON array of directory names to sync (required)
    GITHUB_OUTPUT: Path to GitHub Actions output file (optional)

Output:
    Creates /tmp/sync_summary.txt with statistics
    Writes synced_count to GITHUB_OUTPUT if set
"""

import os
import json
import time
import tempfile
import shutil
from pathlib import Path
from google import genai
from concurrent.futures import ThreadPoolExecutor, as_completed

# Minimum file size in bytes (skip empty files)
MIN_FILE_SIZE = 10


def write_output(key, value):
    """Write key-value pair to GitHub Actions output file."""
    out = os.environ.get('GITHUB_OUTPUT')
    if out:
        with open(out, 'a') as f:
            f.write(f"{key}={value}\n")


def should_process_file(file_path):
    """
    Determine if a file should be processed based on extension and size.

    Args:
        file_path: Path to the file to check

    Returns:
        bool: True if file should be processed, False otherwise
    """
    # Supported extensions (including MDX which we'll handle specially)
    extensions = {'.md', '.mdx', '.txt', '.py', '.js', '.json', '.ts', '.tsx', '.jsx', '.rst'}

    # Check extension
    if file_path.suffix.lower() not in extensions:
        return False

    # Check file size
    try:
        file_size = file_path.stat().st_size
        if file_size < MIN_FILE_SIZE:
            return False

        # Special handling for __init__.py files
        if file_path.name == '__init__.py' and file_size < 100:
            return False
    except Exception:
        return False

    return True


def prepare_file_for_upload(file_path, temp_dir):
    """
    Prepare a file for upload. For MDX files, create a copy with .md extension.

    Args:
        file_path: Path to the file to prepare
        temp_dir: Temporary directory for converted files

    Returns:
        tuple: (upload_path, display_name)
    """
    if file_path.suffix.lower() == '.mdx':
        # Create a temporary copy with .md extension
        temp_name = file_path.stem + '.md'
        temp_path = Path(temp_dir) / temp_name
        shutil.copy2(file_path, temp_path)
        # Keep original name for display
        return temp_path, file_path.name
    else:
        # Use original file as-is
        return file_path, file_path.name


def sync_file_search_stores(client, changed_dirs):
    """
    Sync FileSearchStores for changed directories.

    Args:
        client: Google GenAI client instance
        changed_dirs: List of directory names to sync

    Returns:
        dict: Statistics about the sync operation
    """
    if not changed_dirs:
        print("No directories changed, skipping sync.")
        return {
            'synced_count': 0,
            'total_cost': 0.0,
            'total_files_uploaded': 0,
            'total_files_skipped': 0,
            'total_files_failed': 0
        }

    total_cost = 0.0
    total_files_uploaded = 0
    total_files_skipped = 0
    total_files_failed = 0

    for store_name in changed_dirs:
        print(f"\n{'='*60}")
        print(f"Processing store: {store_name}")
        print(f"{'='*60}")

        # Delete existing store if present
        try:
            stores = list(client.file_search_stores.list())
            existing = [s for s in stores if s.display_name == store_name]
            if existing:
                print(f"Deleting existing store: {existing[0].name}")
                client.file_search_stores.delete(
                    name=existing[0].name,
                    config={'force': True}
                )
                time.sleep(2)
        except Exception as e:
            print(f"❌ Error deleting store {store_name}: {e}")
            print("   Continuing with creation attempt.")

        # Create new store
        print(f"Creating new FileSearchStore: {store_name}")
        try:
            store = client.file_search_stores.create(config={'display_name': store_name})
        except Exception as e:
            print(f"❌ Failed to create store: {e}")
            continue

        # Collect files with improved filtering
        store_path = Path('docs') / store_name
        files = []
        skipped_count = 0

        for root, _, filenames in os.walk(store_path):
            for filename in filenames:
                file_path = Path(root) / filename
                if should_process_file(file_path):
                    files.append(file_path)
                else:
                    skipped_count += 1

        total_files_skipped += skipped_count
        print(f"Found {len(files)} files to upload (skipped {skipped_count} files).")

        if len(files) == 0:
            print("⚠️  No files found after filtering, skipping store.")
            continue

        # Create temporary directory for MDX file conversion
        with tempfile.TemporaryDirectory() as temp_dir:
            # Upload files with improved error handling
            operations = []
            total_tokens = 0
            failed_uploads = []

            def upload_file(file_path):
                """Upload a single file and return operation"""
                try:
                    # Prepare file (convert MDX if needed)
                    upload_path, display_name = prepare_file_for_upload(file_path, temp_dir)

                    file_size = upload_path.stat().st_size
                    estimated_tokens = file_size // 4

                    # Upload using the prepared path
                    op = client.file_search_stores.upload_to_file_search_store(
                        file=str(upload_path),
                        file_search_store_name=store.name,
                        config={'display_name': display_name}
                    )

                    return (op, estimated_tokens, file_path, None)
                except Exception as e:
                    error_msg = str(e)
                    return (None, 0, file_path, error_msg)

            # Upload files in parallel (max 10 concurrent)
            print("Uploading files in parallel...")
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = {executor.submit(upload_file, f): f for f in files}

                for i, future in enumerate(as_completed(futures), 1):
                    op, tokens, file_path, error = future.result()
                    if error:
                        total_files_failed += 1
                        failed_uploads.append((file_path.name, error))
                        # Only show first few errors inline
                        if total_files_failed <= 5:
                            print(f"  ❌ [{i}/{len(files)}] Error: {file_path.name}: {error}")
                    else:
                        operations.append(op)
                        total_tokens += tokens
                        total_files_uploaded += 1
                        if i % 10 == 0 or i == len(files):
                            print(f"  ✅ [{i}/{len(files)}] queued")

        # Wait for uploads to complete
        if operations:
            print(f"Waiting for {len(operations)} uploads to complete...")
            completed = 0
            max_wait = 600  # 10 minutes max
            start_time = time.time()
            last_report = 0

            while completed < len(operations):
                if time.time() - start_time > max_wait:
                    print(f"⚠️  Timeout: {completed}/{len(operations)} completed")
                    break

                # Check all operations in batch
                newly_completed = 0
                for i, op in enumerate(operations):
                    if not op.done:
                        try:
                            operations[i] = client.operations.get(op)
                            if operations[i].done:
                                newly_completed += 1
                        except Exception:
                            pass  # Ignore errors in status checks

                completed += newly_completed

                # Report progress every 10 completions or when done
                if newly_completed > 0 and (completed - last_report >= 10 or completed == len(operations)):
                    print(f"  [{completed}/{len(operations)}] completed")
                    last_report = completed

                if completed < len(operations):
                    time.sleep(2)  # Poll every 2s

        cost = (total_tokens / 1_000_000) * 0.15
        total_cost += cost

        print(f"\n✅ Store '{store_name}' sync complete:")
        print(f"   Files indexed: {len(operations)}")
        print(f"   Files skipped: {skipped_count}")
        if failed_uploads:
            print(f"   Files failed: {len(failed_uploads)}")
            # Show MDX conversion note if any MDX files were processed
            mdx_count = sum(1 for f in files if f.suffix.lower() == '.mdx')
            if mdx_count > 0:
                print(f"   MDX files converted: {mdx_count}")
        print(f"   Estimated tokens: {total_tokens:,}")
        print(f"   Cost: ${cost:.4f}")

        # Show summary of failures if there were many
        if len(failed_uploads) > 5:
            print(f"\n⚠️  Total of {len(failed_uploads)} files failed to upload")

    return {
        'synced_count': len(changed_dirs),
        'total_cost': total_cost,
        'total_files_uploaded': total_files_uploaded,
        'total_files_skipped': total_files_skipped,
        'total_files_failed': total_files_failed
    }


def main():
    """Main entry point."""
    # Validate API key
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        print("❌ Error: GEMINI_API_KEY environment variable is required")
        exit(1)

    # Parse changed directories
    changed_dirs_json = os.environ.get('CHANGED_DIRS', '[]')
    try:
        changed_dirs = json.loads(changed_dirs_json)
    except json.JSONDecodeError as e:
        print(f"❌ Error parsing CHANGED_DIRS: {e}")
        exit(1)

    # Initialize client
    client = genai.Client(api_key=api_key)

    # Sync stores
    stats = sync_file_search_stores(client, changed_dirs)

    # Print summary
    print(f"\n{'='*60}")
    print(f"✅ Total sync summary:")
    print(f"   Directories synced: {stats['synced_count']}")
    print(f"   Files uploaded: {stats['total_files_uploaded']}")
    print(f"   Files skipped: {stats['total_files_skipped']}")
    print(f"   Files failed: {stats['total_files_failed']}")
    print(f"   Total cost: ${stats['total_cost']:.4f}")
    print(f"{'='*60}")

    # Write summary to file
    with open('/tmp/sync_summary.txt', 'w') as f:
        f.write(f"synced_count={stats['synced_count']}\n")
        f.write(f"total_cost={stats['total_cost']:.4f}\n")
        f.write(f"files_uploaded={stats['total_files_uploaded']}\n")
        f.write(f"files_skipped={stats['total_files_skipped']}\n")
        f.write(f"files_failed={stats['total_files_failed']}\n")

    # Write to GitHub Actions output
    write_output("synced_count", stats['synced_count'])

    # Exit with error if failure rate is too high
    total_attempted = stats['total_files_uploaded'] + stats['total_files_failed']
    if total_attempted > 0:
        failure_rate = stats['total_files_failed'] / total_attempted
        if failure_rate > 0.2:  # More than 20% failure rate
            print(f"\n❌ High failure rate: {failure_rate:.1%}")
            exit(1)


if __name__ == "__main__":
    main()
