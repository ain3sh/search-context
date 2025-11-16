# Search Context MCP Server

TypeScript MCP server that provides semantic search over documentation repositories using Gemini File Search.

Originally built for [`ain3sh/docs`](https://github.com/ain3sh/docs), but easily adapted to any docs repo.

## Features

- 🔍 Semantic search over docs using Gemini File Search
- 📁 One store per top-level directory (e.g. `store://context`)
- 🤝 MCP Resources for automatic store discovery
- 🧠 Natural language queries with source citations
- ⚡ Token-efficient responses (~500–1000 tokens by default)
- 🔄 Auto-synced indexes via GitHub Actions (daily at 2 AM UTC)
- 💰 Ultra-low cost (typically ~$0.25–$1/month)
- 📊 Dual formats: Markdown (human) and JSON (programmatic)

---

## Quick Start

### Recommended: `npx`

```bash
npx -y github:ain3sh/search-context
````

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

Each top-level directory in the target repo appears as a store URI:

```text
store://context
store://Factory-AI/factory
store://other-docs
```

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

## Architecture

### Data Flow

```text
Agent Query
    ↓
MCP search_context(store, query)
    ↓
Validate store (cached lookup)
    ↓
Gemini File Search API
    ↓
Semantic retrieval + synthesis
    ↓
Format response (markdown/JSON)
    ↓
Return answer + citations (± chunks)
```

### Indexing Flow

GitHub Actions workflow (`sync-stores.yml`) runs:

* **Schedule**: Daily at 2 AM UTC
* **Triggers**: Manual or on push to `main`
* **Process**:

  1. Detect changed directories via git tag (`last-context-sync`)
  2. Rebuild only modified FileSearchStores
  3. Log indexing cost per sync
  4. Update stores in Gemini File Search

### Store Organization

Each top-level directory in the docs repo becomes an isolated `FileSearchStore`:

```text
ain3sh/docs/
├── context/               → store://context
├── Factory-AI/factory/    → store://Factory-AI/factory
└── other-docs/            → store://other-docs
```

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

**Compared to a naive implementation:**

* Previous: ~10,000+ tokens per query
* Current: ~500–1000 tokens by default (~90% reduction)

### Cost Model (Gemini File Search)

* **Indexing**: ~$0.15 per 1M tokens (one-time per file; re-run only when file changes)
* **Storage**: Free
* **Queries**: Free; retrieved chunks are charged as normal context tokens

**Example monthly estimate:**

* 100 files (~150k tokens): ~$0.0225 per sync
* Daily syncs, small changes: **~$0.25–$1/month**
* Heavy churn / active development: **~$3–$6/month**

---

## Adapting to Your Repository

The server is built for [`ain3sh/docs`](https://github.com/ain3sh/docs) but works for any docs repo with minimal changes.

### Requirements

1. **Repository structure**: Top-level directories map to stores
2. **GitHub Actions**: Add a workflow file (e.g. `.github/workflows/sync-stores.yml`)
3. **Gemini API key**: Set repo secret `GEMINI_API_KEY`
4. **File formats**: Use Markdown, text, PDF, or any Gemini-supported format

### Customization Points

* **Target repository**

  * Update the workflow checkout / paths to point at your repo
  * Adjust the sync script for your directory layout

* **Sync frequency**

  * Edit the cron schedule (default: `0 2 * * *` for 2 AM UTC)

* **Directory filtering**

  * Modify the sync script to include/exclude paths

* **Chunking behavior**

  * Tune `chunking_config` in `src/index.ts` (see Gemini docs)

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
│   └── index.ts            # Main implementation
├── dist/
│   └── index.js            # Compiled output (committed for npx)
├── .github/
│   └── workflows/
│       └── sync-stores.yml # Auto-sync workflow
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

Check:

* Directory exists in the docs repo
* GitHub Actions sync workflow completed successfully
* Workflow logs (repository → **Actions**)
* Resources have had a few minutes to sync after a run

### API Key Problems

**Symptoms**: `UNAUTHENTICATED`, `Invalid API key`

Check:

* `GEMINI_API_KEY` is set in the environment / repo secrets
* Key works at [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey)
* File Search API access is enabled
* Quota not exceeded (free tier ~1500 RPD)

### No Results

**Symptoms**: `"No results found"`

Try:

* Broader or more precise query wording
* Confirm files exist in the target directory
* Confirm the latest sync completed
* Use terms closer to the docs’ own wording
* Ensure files use supported formats (Markdown, text, PDF, etc.)

### Rate Limits

**Error**: `429`, `RESOURCE_EXHAUSTED`

* Free tier: ~15 RPM
* Wait 60 seconds before retrying
* Reduce query rate
* If needed, upgrade to a paid tier in the cloud console

### Server Not Loading in Client

**Symptoms**: MCP client doesn’t show `search-context`

Check:

* `npm run build` completes without errors
* MCP config JSON is valid
* Client logs (e.g. `~/Library/Logs/Claude/mcp*.log`)
* `npx` can access GitHub
* Manual run works:

  ```bash
  GEMINI_API_KEY=key npx -y github:ain3sh/search-context
  ```

---

## GitHub Actions Setup

To keep stores in sync, the **docs repository** (not this server repo) needs a workflow.

### Repository Secret

1. Go to **Settings → Secrets and variables → Actions**
2. Click **New repository secret**
3. Name: `GEMINI_API_KEY`
4. Value: your Gemini API key
5. Click **Add secret**

### Workflow File

Copy or adapt `.github/workflows/sync-stores.yml` from this repo into your docs repo.

To trigger manually:

1. Open the **Actions** tab
2. Select the **Sync Context Search Stores** workflow
3. Click **Run workflow**
4. Watch the logs for sync status and cost reporting

---

## License

MIT License – see `LICENSE`.
