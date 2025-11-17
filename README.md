# Search Context MCP Server

A generic MCP server that provides semantic search over documentation using Gemini File Search.

**What it does**: Queries Gemini FileSearchStores in the cloud and returns AI-generated answers with source citations.

**What it doesn't do**: Index files, manage git repos, or run workflows. Indexing happens separately (e.g., via GitHub Actions in your docs repo, or any custom pipeline).

## Features

- 🔍 Semantic search using Gemini File Search API
- 🤝 Dynamic store discovery via Gemini API (no local configuration needed)
- 🧠 Natural language queries with source citations
- ⚡ Token-efficient responses (~500–1000 tokens by default)
- 📊 Dual formats: Markdown (human-readable) and JSON (programmatic)
- 🌐 Generic: Works with any Gemini FileSearchStores you've created

---

## Architecture

```
Your indexing pipeline → Gemini FileSearchStores (cloud)
                              ↓
                         search-context MCP server (local)
                              ↓
                            Claude
```

**Key points**:
- MCP server **only queries** cloud-based FileSearchStores
- Does **not** interact with git repos or local files
- Stores are created and updated by **your** indexing workflow
- Server discovers stores dynamically via `client.file_search_stores.list()`

---

## Quick Start

### Recommended: `npx`

```bash
npx -y github:ain3sh/search-context
```

No cloning required. Always uses the latest version from GitHub.

### From Source

```bash
git clone https://github.com/ain3sh/search-context.git
cd search-context
npm install
npm run build
npm start
```

---

## Configuration

### Environment Variables

* `GEMINI_API_KEY` **(required)**: Your Gemini API key
* `LOG_LEVEL` *(optional)*: `debug`, `info`, or `error` (default: `info`)

Get an API key: [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey)

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "search-context": {
      "command": "npx",
      "args": ["-y", "github:ain3sh/search-context"],
      "env": {
        "GEMINI_API_KEY": "your_api_key_here"
      }
    }
  }
}
```

### Claude Code (Project-Level)

Create `.mcp.json` in your project root:

```json
{
  "mcpServers": {
    "search-context": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "github:ain3sh/search-context"],
      "env": {
        "GEMINI_API_KEY": "${GEMINI_API_KEY}"
      }
    }
  }
}
```

Then set:

```bash
export GEMINI_API_KEY=your_api_key_here
```

---

## Usage

### Discovering Stores

Stores are exposed as MCP Resources. Clients can discover them via `resources/list`.

The server queries Gemini's API on startup to find all available FileSearchStores and exposes them as URIs:

```text
store://context
store://Factory-AI/factory
store://other-docs
```

**Note**: Store names come from the `displayName` field you set when creating the FileSearchStore.

### Searching Documentation

Use the `search_context` tool with natural language queries:

```ts
// Minimal query (common case)
search_context({
  store: "context",
  query: "How does File Search chunking work?"
})
// → ~500–1000 tokens, answer + citations

// With evidence chunks (for verification)
search_context({
  store: "context",
  query: "authentication flow setup",
  include_chunks: true
})
// → ~2000–3000 tokens, answer + citations + chunk previews
```

#### Parameters

* `store` **(string, required)**: Store name from MCP Resources
  e.g. `"context"`, `"Factory-AI/factory"`
* `query` **(string, required)**: Natural language query
* `include_chunks` *(boolean, optional)*: Include chunk previews (default: `false`)
* `top_k` *(number, optional)*: Chunks to retrieve when `include_chunks=true`
  Default: `3`, max: `20`
* `response_format` *(string, optional)*: `"markdown"` or `"json"` (default: `"markdown"`)
* `metadata_filter` *(string, optional)*: Advanced filter using [List Filter syntax](https://google.aip.dev/160)

#### Response Format

**Default (`response_format="markdown"`, `include_chunks=false`):**

```markdown
# Search Results: context

**Query**: How does chunking work?

**Response**:
[Synthesized answer from semantic search]

---

**Sources** (2 files):
  - ai.google.dev_gemini-api_docs_file-search.md
  - CONTEXT_SEARCH_MCP_SPEC.md
```

**With chunks (`include_chunks=true`):**

```markdown
[... same as above, plus ...]

---

## Retrieved Context Chunks

### [1] ai.google.dev_gemini-api_docs_file-search.md

Files are automatically chunked when imported into a file search store...
[truncated to 500 chars per chunk]

---
```

JSON responses include structured `query`, `response`, `sources`, and optional `chunks[]`.

---

## Performance & Cost

### Token Efficiency

Responses are optimized to avoid context spam:

| Mode                                | Tokens (approx.) | Contents                                   |
| ----------------------------------- | ---------------- | ------------------------------------------ |
| Default (`include_chunks=false`)    | ~500–1000        | Synthesized answer + source citations      |
| With chunks (`include_chunks=true`) | ~2000–3000       | Answer + sources + 500-char chunk previews |

Safeguards:

* Chunk previews truncated to 500 characters
* Full responses capped at 25,000 characters
* Store metadata cached for 5 minutes

### Cost Model (Gemini File Search)

**For the MCP server** (querying):
* **Queries**: Free; retrieved chunks are charged as normal context tokens to your Gemini API usage

**For indexing** (done separately by your pipeline):
* **Indexing**: ~$0.15 per 1M tokens (one-time per file; re-run only when file changes)
* **Storage**: Free

**Example monthly estimate** (if using a daily indexing workflow):
* 100 files (~150k tokens): ~$0.0225 per sync
* Daily syncs, small changes: **~$0.25–$1/month**
* Heavy churn / active development: **~$3–$6/month**

---

## Setting Up Indexing (Separate from MCP Server)

The MCP server **only queries** existing Gemini FileSearchStores. You need a separate process to create and update these stores.

### Option 1: GitHub Actions Workflow

If you have a docs repository, you can automate indexing with GitHub Actions.

**Example**: See [`ain3sh/docs`](https://github.com/ain3sh/docs) for a complete implementation:
- `mirrors.json`: Configuration for which repos/directories to index
- `.github/scripts/sync.py`: Script that creates/updates FileSearchStores
- `.github/workflows/sync.yml`: Workflow that runs daily and on changes

**Key steps**:
1. Set `GEMINI_API_KEY` as a repository secret
2. Create a workflow that:
   - Clones/fetches documentation files
   - Uses Gemini File Search API to create/update stores
   - Sets a `displayName` for each store (this becomes the store name in MCP)
3. Run daily or on file changes

### Option 2: Custom Pipeline

You can index from any environment:

```python
from google import genai

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Create a store
store = client.file_search_stores.create(
    display_name="my-docs"  # This becomes store://my-docs in MCP
)

# Upload files
for file_path in doc_files:
    client.file_search_stores.upload_file(
        store_id=store.id,
        path=file_path
    )
```

### Store Naming

The `displayName` you set when creating a FileSearchStore becomes its MCP resource URI:

```python
# In your indexing script:
store = client.file_search_stores.create(display_name="context")

# In MCP:
search_context({ store: "context", query: "..." })
```

---

## Development

### Local Development

```bash
# Install dependencies
npm install

# Build
npm run build

# Development mode (auto-reload)
npm run dev

# Run with API key
GEMINI_API_KEY=your_key npm start
```

### Project Structure

```text
search-context/
├── src/
│   └── index.ts            # Main MCP server implementation
├── dist/
│   └── index.js            # Compiled output (committed for npx)
├── package.json            # Includes bin field for CLI
├── tsconfig.json
└── README.md
```

### Quick Local Test

```bash
npm run build
timeout 5s GEMINI_API_KEY=your_key npx .
```

MCP servers are long-lived; real testing is best via an MCP client (Claude Desktop, Claude Code, etc.).

---

## Troubleshooting

### Store Not Found

**Error**: `Error: Store 'xyz' not found`

**Check**:
- Store exists in Gemini (visit [Google AI Studio](https://aistudio.google.com/))
- Store has files uploaded
- Store's `displayName` matches what you're querying
- Restart the MCP server (store list is cached at startup)

### API Key Problems

**Symptoms**: `UNAUTHENTICATED`, `Invalid API key`

**Check**:
- `GEMINI_API_KEY` is set in environment/config
- Key works at [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey)
- File Search API access is enabled
- Quota not exceeded (free tier ~1500 RPD)

### No Results

**Symptoms**: `"No results found"`

**Try**:
- Broader or more precise query wording
- Confirm files exist in the store (check Google AI Studio)
- Confirm indexing completed successfully
- Use terms closer to the docs' own wording
- Ensure files use supported formats (Markdown, text, PDF, etc.)

### Rate Limits

**Error**: `429`, `RESOURCE_EXHAUSTED`

- Free tier: ~15 RPM
- Wait 60 seconds before retrying
- Reduce query rate
- If needed, upgrade to a paid tier

### Server Not Loading in Client

**Symptoms**: MCP client doesn't show `search-context`

**Check**:
- `npm run build` completes without errors
- MCP config JSON is valid
- Client logs (e.g. `~/Library/Logs/Claude/mcp*.log`)
- `npx` can access GitHub
- Manual run works:

  ```bash
  GEMINI_API_KEY=key npx -y github:ain3sh/search-context
  ```

---

## License

MIT License – see `LICENSE`.
