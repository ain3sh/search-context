#!/usr/bin/env python3
"""
Sync FileSearchStores for changed documentation directories.

Behavior:
- Reads env: DOCS_PATH (default 'docs'), CHANGED_DIRS (JSON), GEMINI_API_KEY.
- If CHANGED_DIRS is empty, write /tmp/sync_summary.txt with zeros, set output
  synced_count=0, and exit 0.
- For each store in CHANGED_DIRS:
  * Delete existing store (cached lookup) then recreate.
  * Collect files recursively under DOCS_PATH/<store_name>.
  * Upload files in parallel (≤10 workers) with MDX conversion where .mdx -> temp .md.
  * Track totals and write /tmp/sync_summary.txt (synced_count, total_cost, files_*).
  * Exit non-zero if failure rate > 20%.
"""

import os
import sys
import json
import time
import tempfile
import shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from google import genai

MIN_FILE_SIZE = 10
SUPPORTED_EXTENSIONS = {
    ".md", ".mdx", ".txt",
    ".py", ".js", ".json",
    ".ts", ".tsx", ".jsx", ".rst"
}


def write_output(key, value):
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")


def should_process_file(file_path: Path) -> bool:
    if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        return False
    try:
        size = file_path.stat().st_size
    except OSError:
        return False
    if size < MIN_FILE_SIZE:
        return False
    if file_path.name == "__init__.py" and size < 100:
        return False
    return True


def prepare_file_for_upload(file_path: Path, temp_dir: Path):
    if file_path.suffix.lower() == ".mdx":
        temp_name = file_path.stem + ".md"
        temp_path = temp_dir / temp_name
        shutil.copy2(file_path, temp_path)
        return temp_path, file_path.name
    return file_path, file_path.name


def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("❌ Error: GEMINI_API_KEY environment variable not set", file=sys.stderr)
        return 1

    docs_path = os.environ.get("DOCS_PATH", "docs")
    raw_changed = os.environ.get("CHANGED_DIRS", "[]")

    try:
        changed_dirs = json.loads(raw_changed)
        if not isinstance(changed_dirs, list):
            raise ValueError("CHANGED_DIRS is not a list")
    except Exception as e:
        print(f"❌ Error: Invalid CHANGED_DIRS value ({e}): {raw_changed}", file=sys.stderr)
        return 1

    if not changed_dirs:
        print("No directories changed, skipping sync.")
        _write_summary(0, 0.0, 0, 0, 0)
        write_output("synced_count", 0)
        return 0

    try:
        client = genai.Client(api_key=api_key)
    except Exception as e:
        print(f"❌ Failed to initialize GenAI client: {e}", file=sys.stderr)
        return 1

    # Cache existing stores to avoid repeated listing
    print("Fetching existing FileSearchStores...", file=sys.stderr)
    try:
        existing = list(client.file_search_stores.list())
        stores_by_display = {s.display_name: s for s in existing}
        print(f"  Found {len(existing)} existing stores", file=sys.stderr)
    except Exception as e:
        print(f"⚠️  Warning: Could not list existing stores: {e}", file=sys.stderr)
        stores_by_display = {}

    total_cost = 0.0
    total_uploaded = 0
    total_skipped = 0
    total_failed = 0

    for store_name in changed_dirs:
        print("\n" + "=" * 60)
        print(f"Processing store: {store_name}")
        print("=" * 60)

        # Delete existing
        existing_store = stores_by_display.get(store_name)
        if existing_store:
            try:
                print(f"Deleting existing store: {existing_store.name}")
                client.file_search_stores.delete(
                    name=existing_store.name,
                    config={"force": True}
                )
                # small wait to allow backend cleanup
                time.sleep(2)
            except Exception as e:
                print(f"❌ Error deleting store '{store_name}': {e}", file=sys.stderr)
                print("   Continuing with new store creation.")

        # Create new store
        try:
            store = client.file_search_stores.create(config={"display_name": store_name})
        except Exception as e:
            print(f"❌ Failed to create store '{store_name}': {e}", file=sys.stderr)
            continue

        store_dir = Path(docs_path) / store_name
        if not store_dir.exists():
            print(f"⚠️  Store directory does not exist: {store_dir} (skipping)")
            continue

        files = []
        skipped = 0
        for root, _, filenames in os.walk(store_dir):
            for fname in filenames:
                fp = Path(root) / fname
                if fp.name.startswith("."):
                    skipped += 1
                    continue
                if should_process_file(fp):
                    files.append(fp)
                else:
                    skipped += 1

        total_skipped += skipped
        print(f"Found {len(files)} files to upload (skipped {skipped}).")

        if not files:
            print("⚠️  No files remain after filtering; skipping store.")
            continue

        operations = []
        total_tokens_this_store = 0
        failed_uploads = []

        with tempfile.TemporaryDirectory() as td:
            tmp_dir = Path(td)

            def upload_one(fp: Path):
                try:
                    up_path, display_name = prepare_file_for_upload(fp, tmp_dir)
                    size = up_path.stat().st_size
                    est_tokens = size // 4
                    op = client.file_search_stores.upload_to_file_search_store(
                        file=str(up_path),
                        file_search_store_name=store.name,
                        config={"display_name": display_name}
                    )
                    return (op, est_tokens, fp, None)
                except Exception as ex:
                    return (None, 0, fp, str(ex))

            print("Uploading files in parallel...")
            with ThreadPoolExecutor(max_workers=10) as pool:
                futures = {pool.submit(upload_one, f): f for f in files}
                for i, fut in enumerate(as_completed(futures), 1):
                    op, tokens, fp, err = fut.result()
                    if err:
                        total_failed += 1
                        failed_uploads.append((fp.name, err))
                        if total_failed <= 5:
                            print(f"  ❌ [{i}/{len(files)}] {fp.name}: {err}")
                    else:
                        operations.append(op)
                        total_tokens_this_store += tokens
                        total_uploaded += 1
                        if i % 10 == 0 or i == len(files):
                            print(f"  ✅ [{i}/{len(files)}] queued")

        # Poll operations
        if operations:
            print(f"Waiting for {len(operations)} upload operations to finish...")
            completed = 0
            start = time.time()
            last_report = 0
            max_wait = 600
            while completed < len(operations):
                if time.time() - start > max_wait:
                    print(f"⚠️  Timeout while waiting: {completed}/{len(operations)} completed")
                    break
                newly = 0
                for idx, op in enumerate(operations):
                    if not getattr(op, "done", False):
                        try:
                            operations[idx] = client.operations.get(op)
                            if getattr(operations[idx], "done", False):
                                newly += 1
                        except Exception:
                            pass
                if newly:
                    completed += newly
                    if completed - last_report >= 10 or completed == len(operations):
                        print(f"  [{completed}/{len(operations)}] completed")
                        last_report = completed
                if completed < len(operations):
                    time.sleep(2)

        cost = (total_tokens_this_store / 1_000_000) * 0.15
        total_cost += cost

        print(f"\n✅ Store '{store_name}' sync complete:")
        print(f"   Files indexed: {len(operations)}")
        print(f"   Files skipped: {skipped}")
        if failed_uploads:
            print(f"   Files failed: {len(failed_uploads)}")
            mdx_converted = sum(1 for f in files if f.suffix.lower() == ".mdx")
            if mdx_converted:
                print(f"   MDX files converted: {mdx_converted}")
        print(f"   Estimated tokens: {total_tokens_this_store:,}")
        print(f"   Cost: ${cost:.4f}")

        if len(failed_uploads) > 5:
            print(f"⚠️  {len(failed_uploads)} files failed (summary truncated)")

    print("\n" + "=" * 60)
    print("✅ Total sync summary:")
    print(f"   Directories synced: {len(changed_dirs)}")
    print(f"   Files uploaded: {total_uploaded}")
    print(f"   Files skipped: {total_skipped}")
    print(f"   Files failed: {total_failed}")
    print(f"   Total cost: ${total_cost:.4f}")
    print("=" * 60)

    _write_summary(len(changed_dirs), total_cost, total_uploaded, total_skipped, total_failed)
    write_output("synced_count", len(changed_dirs))

    attempted = total_uploaded + total_failed
    if attempted > 0:
        failure_rate = total_failed / attempted
        if failure_rate > 0.20:
            print(f"\n❌ High failure rate: {failure_rate:.1%}", file=sys.stderr)
            return 1
    return 0


def _write_summary(synced, total_cost, uploaded, skipped, failed):
    with open("/tmp/sync_summary.txt", "w", encoding="utf-8") as f:
        f.write(f"synced_count={synced}\n")
        f.write(f"total_cost={total_cost:.4f}\n")
        f.write(f"files_uploaded={uploaded}\n")
        f.write(f"files_skipped={skipped}\n")
        f.write(f"files_failed={failed}\n")


if __name__ == "__main__":
    sys.exit(main())
