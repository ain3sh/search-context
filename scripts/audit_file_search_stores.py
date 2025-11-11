#!/usr/bin/env python3
"""
Audit script for FileSearchStores in Gemini API.

This script provides visibility into all FileSearchStores, identifying:
- Total storage usage
- Duplicate stores
- Orphaned or unused stores
- Store statistics

Usage:
    export GEMINI_API_KEY=your_api_key
    python audit_file_search_stores.py [--verbose]

Options:
    --verbose    Show detailed information for each store
"""

import os
import sys
from collections import defaultdict
from datetime import datetime
from google import genai


def format_size(bytes_size):
    """Format bytes into human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} PB"


def audit_file_search_stores(verbose=False):
    """
    Audit all FileSearchStores and report statistics.

    Args:
        verbose: If True, show detailed information for each store
    """
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        print("❌ Error: GEMINI_API_KEY environment variable not set")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    print("🔍 Fetching all FileSearchStores...\n")
    all_stores = list(client.file_search_stores.list())

    if not all_stores:
        print("✅ No FileSearchStores found")
        return

    # Group by display_name
    stores_by_name = defaultdict(list)
    total_size = 0
    total_active_docs = 0
    total_pending_docs = 0
    total_failed_docs = 0

    for store in all_stores:
        stores_by_name[store.display_name].append(store)
        total_size += store.size_bytes
        total_active_docs += store.active_documents_count
        total_pending_docs += store.pending_documents_count
        total_failed_docs += store.failed_documents_count

    # Overall statistics
    print("=" * 70)
    print("📊 OVERALL STATISTICS")
    print("=" * 70)
    print(f"Total stores:           {len(all_stores)}")
    print(f"Unique store names:     {len(stores_by_name)}")
    print(f"Total storage used:     {format_size(total_size)}")
    print(f"Total active documents: {total_active_docs}")
    print(f"Total pending documents: {total_pending_docs}")
    print(f"Total failed documents: {total_failed_docs}")
    print()

    # Quota information
    quota_limits = {
        'Free': 1 * 1024**3,      # 1 GB
        'Tier 1': 10 * 1024**3,   # 10 GB
        'Tier 2': 100 * 1024**3,  # 100 GB
        'Tier 3': 1 * 1024**4,    # 1 TB
    }

    print("📈 QUOTA USAGE (by tier):")
    for tier, limit in quota_limits.items():
        percentage = (total_size / limit) * 100
        status = "✅" if percentage < 50 else "⚠️" if percentage < 80 else "🚨"
        print(f"   {status} {tier:8} ({format_size(limit):>10}): {percentage:>6.2f}% used")
    print()

    # Check for duplicates
    duplicates = {name: stores for name, stores in stores_by_name.items() if len(stores) > 1}
    if duplicates:
        print("=" * 70)
        print(f"⚠️  DUPLICATE STORES DETECTED: {len(duplicates)} store names")
        print("=" * 70)
        total_duplicate_size = 0
        for name, stores in duplicates.items():
            print(f"\n📦 '{name}' - {len(stores)} copies:")
            stores.sort(key=lambda s: s.create_time, reverse=True)
            for i, store in enumerate(stores):
                age = "newest" if i == 0 else f"#{i+1}"
                print(f"   {age:8} | {store.name}")
                print(f"           | Created: {store.create_time}")
                print(f"           | Size: {format_size(store.size_bytes)}, Docs: {store.active_documents_count}")
                if i > 0:  # Count duplicates (not the keeper)
                    total_duplicate_size += store.size_bytes

        print(f"\n💡 Wasted storage from duplicates: {format_size(total_duplicate_size)}")
        print(f"   Run cleanup_duplicate_stores.py to remove duplicates")
        print()

    # Check for failed documents
    stores_with_failures = [s for s in all_stores if s.failed_documents_count > 0]
    if stores_with_failures:
        print("=" * 70)
        print(f"⚠️  STORES WITH FAILED DOCUMENTS: {len(stores_with_failures)}")
        print("=" * 70)
        for store in stores_with_failures:
            print(f"📦 {store.display_name}")
            print(f"   Store: {store.name}")
            print(f"   Failed docs: {store.failed_documents_count}")
            print(f"   Active docs: {store.active_documents_count}")
            print()

    # Verbose mode: list all stores
    if verbose:
        print("=" * 70)
        print("📋 ALL STORES (detailed)")
        print("=" * 70)
        for name, stores in sorted(stores_by_name.items()):
            for store in stores:
                print(f"\n📦 {store.display_name}")
                print(f"   Name:         {store.name}")
                print(f"   Created:      {store.create_time}")
                print(f"   Updated:      {store.update_time}")
                print(f"   Size:         {format_size(store.size_bytes)}")
                print(f"   Active docs:  {store.active_documents_count}")
                print(f"   Pending docs: {store.pending_documents_count}")
                print(f"   Failed docs:  {store.failed_documents_count}")

    # Recommendations
    print("=" * 70)
    print("💡 RECOMMENDATIONS")
    print("=" * 70)
    if duplicates:
        print("⚠️  Run cleanup_duplicate_stores.py to remove duplicate stores")
    if stores_with_failures:
        print("⚠️  Investigate failed documents and consider re-indexing")
    if total_size > 20 * 1024**3:
        print("⚠️  Total storage > 20 GB - consider splitting stores for optimal latency")
    if not duplicates and not stores_with_failures:
        print("✅ All stores look healthy!")
    print("=" * 70)


if __name__ == "__main__":
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    audit_file_search_stores(verbose=verbose)
