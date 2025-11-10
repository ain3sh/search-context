#!/usr/bin/env python3
"""
One-time cleanup script to remove incorrectly created FileSearchStores.

This script deletes stores that were created from ain3sh/search-context
internal directories instead of from ain3sh/docs documentation.
"""

import os
import sys
from google import genai

def main():
    # Validate API key
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        print("❌ ERROR: GEMINI_API_KEY environment variable is required")
        print("   Set it with: export GEMINI_API_KEY=your_key_here")
        sys.exit(1)

    # Initialize client
    client = genai.Client(api_key=api_key)

    # Define stores that should be deleted (from search-context repo)
    # These are internal project directories, not documentation
    stores_to_delete = [
        'src',
        'dist',
        'evaluations',
        'node_modules',
        '.github',
        'scripts',
        'search-tool',
        'search-tool/.gitignore',
        'search-tool/dist',
        'search-tool/package-lock.json',
        'search-tool/package.json',
        'search-tool/README.md',
        'search-tool/src',
        'search-tool/tsconfig.json',
        'README.md',
        'package.json',
        'tsconfig.json',
        '.gitignore',
    ]

    # Stores that should be KEPT (legitimate documentation from ain3sh/docs)
    stores_to_keep = [
        'context',
        'Factory-AI',
        'Factory-AI/factory',
    ]

    print("🔍 Fetching all FileSearchStores...")
    try:
        stores = list(client.file_search_stores.list())
        print(f"   Found {len(stores)} total stores\n")
    except Exception as e:
        print(f"❌ Error fetching stores: {e}")
        sys.exit(1)

    # Analyze stores
    deleted_count = 0
    kept_count = 0
    unknown_count = 0

    for store in stores:
        store_name = store.display_name or "(no display name)"
        store_id = store.name

        if store_name in stores_to_delete:
            # Delete incorrect store
            print(f"🗑️  Deleting: {store_name}")
            print(f"   ID: {store_id}")
            try:
                client.file_search_stores.delete(
                    name=store_id,
                    force=True  # ✅ CORRECT SYNTAX (direct parameter)
                )
                print(f"   ✅ Successfully deleted\n")
                deleted_count += 1
            except Exception as e:
                print(f"   ❌ Error deleting: {e}\n")

        elif store_name in stores_to_keep:
            # Keep legitimate documentation store
            print(f"✅ Keeping: {store_name}")
            print(f"   ID: {store_id}")
            print(f"   (Legitimate documentation store)\n")
            kept_count += 1

        else:
            # Unknown store - list for manual review
            print(f"⚠️  Unknown: {store_name}")
            print(f"   ID: {store_id}")
            print(f"   (Not in cleanup or keep list - review manually)\n")
            unknown_count += 1

    # Summary
    print("=" * 60)
    print("📊 CLEANUP SUMMARY")
    print("=" * 60)
    print(f"   Deleted: {deleted_count} stores")
    print(f"   Kept: {kept_count} stores")
    print(f"   Unknown: {unknown_count} stores (manual review needed)")
    print(f"   Total processed: {len(stores)} stores")
    print("=" * 60)

    if unknown_count > 0:
        print("\n⚠️  WARNING: Some unknown stores were found.")
        print("   Review them manually and update this script if needed.")

    print("\n✅ Cleanup complete!")

if __name__ == "__main__":
    main()
