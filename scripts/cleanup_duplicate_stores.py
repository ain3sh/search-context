#!/usr/bin/env python3
"""
Cleanup script for duplicate FileSearchStores in Gemini API.

This script identifies and removes duplicate stores with the same display_name,
keeping only the most recently created store for each name.

Usage:
    export GEMINI_API_KEY=your_api_key
    python cleanup_duplicate_stores.py [--dry-run]

Options:
    --dry-run    Show what would be deleted without actually deleting
"""

import os
import sys
from collections import defaultdict
from datetime import datetime
from google import genai


def cleanup_duplicate_stores(dry_run=False):
    """
    Remove duplicate stores, keeping only the most recent one for each display_name.

    Args:
        dry_run: If True, only report what would be deleted without actually deleting
    """
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        print("❌ Error: GEMINI_API_KEY environment variable not set")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    print("🔍 Fetching all FileSearchStores...")
    all_stores = list(client.file_search_stores.list())
    print(f"   Found {len(all_stores)} total stores\n")

    # Group stores by display_name
    stores_by_name = defaultdict(list)
    for store in all_stores:
        stores_by_name[store.display_name].append(store)

    # Find duplicates
    duplicates = {name: stores for name, stores in stores_by_name.items() if len(stores) > 1}

    if not duplicates:
        print("✅ No duplicate stores found!")
        return 0

    print(f"⚠️  Found {len(duplicates)} store names with duplicates:\n")

    deleted_count = 0
    total_size_freed = 0

    for name, stores in duplicates.items():
        print(f"📦 Store name: '{name}' ({len(stores)} copies)")

        # Sort by creation time (newest first)
        stores.sort(key=lambda s: s.create_time, reverse=True)
        keep = stores[0]
        delete = stores[1:]

        print(f"   ✅ KEEPING: {keep.name}")
        print(f"      Created: {keep.create_time}")
        print(f"      Active docs: {keep.active_documents_count}")
        print(f"      Size: {keep.size_bytes / (1024**2):.2f} MB")

        for old_store in delete:
            size_mb = old_store.size_bytes / (1024**2)
            print(f"   {'🔍 WOULD DELETE' if dry_run else '🗑️  DELETING'}: {old_store.name}")
            print(f"      Created: {old_store.create_time}")
            print(f"      Active docs: {old_store.active_documents_count}")
            print(f"      Size: {size_mb:.2f} MB")

            if not dry_run:
                try:
                    client.file_search_stores.delete(
                        name=old_store.name,
                        config={'force': True}  # Cascade delete all documents and chunks
                    )
                    print(f"      ✅ Deleted successfully")
                    deleted_count += 1
                    total_size_freed += old_store.size_bytes
                except Exception as e:
                    print(f"      ❌ Error deleting: {e}")
            else:
                deleted_count += 1
                total_size_freed += old_store.size_bytes

        print()

    # Summary
    print("=" * 60)
    if dry_run:
        print(f"🔍 DRY RUN SUMMARY:")
        print(f"   Would delete: {deleted_count} duplicate stores")
        print(f"   Would free: {total_size_freed / (1024**2):.2f} MB")
        print(f"\nRun without --dry-run to actually delete these stores.")
    else:
        print(f"✅ CLEANUP COMPLETE:")
        print(f"   Deleted: {deleted_count} duplicate stores")
        print(f"   Freed: {total_size_freed / (1024**2):.2f} MB")
    print("=" * 60)

    return deleted_count


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        print("🔍 Running in DRY RUN mode - no stores will be deleted\n")
    else:
        print("⚠️  Running in LIVE mode - duplicates will be permanently deleted")
        print("   Press Ctrl+C within 5 seconds to cancel...\n")
        import time
        try:
            time.sleep(5)
        except KeyboardInterrupt:
            print("\n❌ Cancelled by user")
            sys.exit(0)

    deleted = cleanup_duplicate_stores(dry_run=dry_run)
    sys.exit(0 if deleted >= 0 else 1)
