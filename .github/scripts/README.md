# GitHub Actions Scripts

This directory contains versioned Python scripts used by GitHub Actions workflows for managing FileSearchStore synchronization.

## Scripts

### `detect_changed_dirs.py`

Detects which documentation directories have changes since the last sync and need their FileSearchStores to be recreated.

**Responsibilities:**
- Read `LAST_SYNC_COMMIT` from environment (if absent, perform full discovery)
- Discover indexable stores: directories with ≥1 non-hidden file at root level
- Run `git diff --name-only LAST_SYNC_COMMIT..HEAD` scoped to docs/
- Normalize changed file paths, ignore `.github/`, hidden files
- Map changed files to store directories precisely
- Output JSON list of changed directories to stdout

**Usage:**
```bash
cd docs
export LAST_SYNC_COMMIT=<commit-sha>  # Optional
python detect_changed_dirs.py
```

**Environment Variables:**
- `LAST_SYNC_COMMIT`: Git commit SHA of the last sync (optional)
  - If not set, performs full discovery of all indexable stores

**Output:**
- JSON array of changed directory names (e.g., `["context", "Factory-AI/factory"]`)

---

### `sync_file_search_stores.py`

Synchronizes FileSearchStores for changed documentation directories by deleting and recreating them.

**Responsibilities:**
- Read `CHANGED_DIRS` from environment (JSON list)
- Delete and recreate FileSearchStores for changed directories
- Filter files by extension and size (skip empty/trivial files)
- Convert `.mdx` files to `.md` for upload compatibility
- Upload files in parallel with error handling
- Output sync summary statistics

**Usage:**
```bash
export GEMINI_API_KEY=<your-api-key>
export CHANGED_DIRS='["context", "Factory-AI/factory"]'
python sync_file_search_stores.py
```

**Environment Variables:**
- `GEMINI_API_KEY`: Gemini API key (required)
- `CHANGED_DIRS`: JSON array of directory names to sync (required)
- `GITHUB_OUTPUT`: Path to GitHub Actions output file (optional)

**Output:**
- Creates `/tmp/sync_summary.txt` with statistics
- Writes `synced_count` to `GITHUB_OUTPUT` if set

**Supported File Extensions:**
- `.md`, `.mdx`, `.txt`, `.py`, `.js`, `.json`, `.ts`, `.tsx`, `.jsx`, `.rst`

---

## Design Rationale

These scripts were extracted from the inline Python code in the sync workflow to:

1. **Improve Maintainability**: Version-controlled, testable scripts are easier to maintain than embedded heredocs
2. **Enable Testing**: Scripts can be tested independently of the workflow
3. **Better Debugging**: Easier to test and debug script logic locally
4. **Clearer Separation**: Each script has a single, well-defined responsibility
5. **Tighter Diff Detection**: Only delete and recreate stores for directories that actually changed

## Testing Locally

You can test these scripts locally to verify behavior before running in CI:

```bash
# Test detect_changed_dirs.py
cd /path/to/docs/repo
python /path/to/detect_changed_dirs.py

# Test sync_file_search_stores.py (with fake data)
export GEMINI_API_KEY=your_test_key
export CHANGED_DIRS='[]'
python /path/to/sync_file_search_stores.py
```
