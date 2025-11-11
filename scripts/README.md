# Gemini FileSearchStore Management Scripts

Utility scripts for managing FileSearchStores in the Gemini API to prevent cost ballooning and quota issues.

## Overview

The Gemini File Search API stores data indefinitely until manually deleted. These scripts help maintain healthy storage by:
- Auditing current usage and identifying issues
- Cleaning up duplicate stores
- Preventing quota limit exhaustion

## Background

### Key Facts
- **Storage**: FREE (no ongoing costs)
- **Indexing**: $0.15 per 1M tokens (one-time)
- **Data persistence**: Indefinite (must manually delete)
- **Quota limits**:
  - Free tier: 1 GB
  - Tier 1: 10 GB
  - Tier 2: 100 GB
  - Tier 3: 1 TB

### The Problem
Prior to 2025-01-11, the workflow deletion was missing the `force` parameter, causing:
- Failed deletions when stores contained documents
- Accumulating duplicate stores
- Wasted storage quota (though storage is free, quotas are not unlimited)

## Scripts

### 1. `audit_file_search_stores.py`

**Purpose**: Monitor and report on all FileSearchStores

**Usage**:
```bash
export GEMINI_API_KEY=your_api_key
python scripts/audit_file_search_stores.py [--verbose]
```

**Features**:
- Total storage usage across all stores
- Quota usage by tier
- Duplicate store detection
- Failed document identification
- Health recommendations

**Example Output**:
```
📊 OVERALL STATISTICS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total stores:           8
Unique store names:     4
Total storage used:     245.67 MB
Total active documents: 234

📈 QUOTA USAGE (by tier):
   ✅ Free     (   1.00 GB):  23.99% used
   ✅ Tier 1   (  10.00 GB):   2.40% used
```

### 2. `cleanup_duplicate_stores.py`

**Purpose**: Remove duplicate stores, keeping only the most recent

**Usage**:
```bash
# Dry run (safe - shows what would be deleted)
export GEMINI_API_KEY=your_api_key
python scripts/cleanup_duplicate_stores.py --dry-run

# Live deletion (waits 5 seconds for cancel)
python scripts/cleanup_duplicate_stores.py
```

**Features**:
- Identifies stores with duplicate display names
- Keeps newest store, deletes older duplicates
- Uses `force=True` for cascading deletion
- Dry-run mode for safe testing
- Reports storage freed

**Example Output**:
```
⚠️  Found 2 store names with duplicates:

📦 Store name: 'anthropic-docs' (3 copies)
   ✅ KEEPING: fileSearchStores/abc123
      Created: 2025-01-11T10:30:00Z
      Active docs: 150
      Size: 85.23 MB
   🗑️  DELETING: fileSearchStores/xyz789
      Created: 2025-01-10T08:15:00Z
      Active docs: 148
      Size: 84.11 MB
```

## Workflow Integration

The main workflow (`.github/workflows/sync-context-search.yml`) has been fixed to properly delete stores:

```python
# Before (BROKEN - would fail):
client.file_search_stores.delete(name=existing[0].name)

# After (FIXED):
client.file_search_stores.delete(
    name=existing[0].name,
    config={'force': True}  # Cascade delete all documents and chunks
)
```

## Recommended Maintenance

### Initial Cleanup (one-time)
```bash
# Audit current state
python scripts/audit_file_search_stores.py --verbose

# Clean up existing duplicates (if any found)
python scripts/cleanup_duplicate_stores.py --dry-run  # Preview
python scripts/cleanup_duplicate_stores.py             # Execute
```

### Ongoing Monitoring (optional)

Add to GitHub Actions workflow for regular audits:

```yaml
- name: Audit FileSearchStores
  if: always()
  run: |
    python scripts/audit_file_search_stores.py
```

## API Reference

### Delete FileSearchStore
```python
client.file_search_stores.delete(
    name='fileSearchStores/store-id',
    config={'force': True}  # Required to delete stores with documents
)
```

**Parameters**:
- `force=false` (default): Fails with `FAILED_PRECONDITION` if store has documents
- `force=true`: Cascades deletion to all Documents and Chunks

### Delete Document
```python
client.file_search_stores.documents.delete(
    name='fileSearchStores/store-id/documents/doc-id',
    config={'force': True}  # Required to delete documents with chunks
)
```

## Troubleshooting

### "FAILED_PRECONDITION" Error
**Cause**: Trying to delete a store/document without `force=True`
**Fix**: Add `config={'force': True}` to the delete call

### High Quota Usage
**Cause**: Accumulated orphaned stores
**Fix**: Run `cleanup_duplicate_stores.py`

### Failed Documents
**Cause**: Processing errors during indexing
**Check**: Run `audit_file_search_stores.py` to identify affected stores
**Fix**: Delete and re-index the store

## Cost Implications

While storage is free, proper cleanup matters because:
1. **Quota limits**: Free tier has only 1 GB - duplicates waste quota
2. **API performance**: Excess stores slow down list operations
3. **Operational clarity**: Duplicates cause confusion
4. **Future-proofing**: Pricing models may change

## Learn More

- [Gemini File Search Docs](https://ai.google.dev/gemini-api/docs/file-search)
- [FileSearchStores API](https://ai.google.dev/api/file-search/file-search-stores)
- [Documents API](https://ai.google.dev/api/file-search/documents)
