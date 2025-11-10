# Search Context MCP Server

TypeScript MCP server providing semantic search over documentation repositories using Google's Gemini File Search API.

Built for the [ain3sh/docs](https://github.com/ain3sh/docs) repository but easily adaptable to any documentation source.

## What It Does

Enables AI agents to search documentation using natural language queries that understand meaning and context, not just keywords. Each top-level directory becomes its own searchable store, automatically indexed and kept up-to-date via GitHub Actions.

**Key Capabilities:**
- Semantic search powered by Gemini's File Search API
- Natural language queries with source citations
- Auto-synced indexes (daily at 2 AM UTC)
- MCP Resources for automatic store discovery
- Token-efficient responses (500-1000 tokens by default)
- Ultra-low cost (~$0.25-$1/month for typical usage)

## Installation

### Recommended: npx

```bash
npx -y github:ain3sh/search-context
```

No installation or cloning required. Always uses the latest version from GitHub.

### Alternative: From Source

```bash
git clone https://github.com/ain3sh/search-context.git
cd search-context
npm install
npm run build
npm start
```

## Configuration

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

Get your API key: https://aistudio.google.com/apikey

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

Set the environment variable:

```bash
export GEMINI_API_KEY=your_api_key_here
```

### Environment Variables

- `GEMINI_API_KEY` (required): Your Gemini API key
- `LOG_LEVEL` (optional): Logging verbosity - `debug`, `info`, or `error` (default: `info`)

## Usage

### Discovering Stores

Stores are automatically exposed via MCP Resources. Clients can discover available documentation stores using `resources/list`:

```typescript
// MCP Resources automatically lists available stores
// Each store appears as: store://context, store://Factory-AI/factory, etc.
```

### Searching Documentation

The `search_context` tool accepts natural language queries:

```typescript
// Minimal query (most common)
search_context({
  store: "context",
  query: "How does File Search chunking work?"
})
// Returns: ~500-1000 tokens with answer + citations

// With evidence chunks (for verification)
search_context({
  store: "context",
  query: "authentication flow setup",
  include_chunks: true
})
// Returns: ~2000-3000 tokens with answer + citations + chunk previews
```

**Parameters:**
- `store` (string, required): Store name from resources (e.g., "context", "Factory-AI/factory")
- `query` (string, required): Natural language search query
- `include_chunks` (boolean, optional): Include document chunk previews (default: `false`)
- `top_k` (number, optional): Number of chunks to retrieve when `include_chunks=true` (default: `3`, max: `20`)
- `response_format` (string, optional): `"markdown"` or `"json"` (default: `"markdown"`)
- `metadata_filter` (string, optional): Advanced filtering using [List Filter syntax](https://google.aip.dev/160)

**Response Format:**

Default (Markdown, `include_chunks=false`):
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

With chunks (Markdown, `include_chunks=true`):
```markdown
[... same as above, plus ...]

---

## Retrieved Context Chunks

### [1] ai.google.dev_gemini-api_docs_file-search.md

Files are automatically chunked when imported into a file search store...
[truncated to 500 chars per chunk]

---
```

JSON format includes structured `query`, `response`, `sources`, and optionally `chunks` arrays.

## Architecture

### Data Flow

```
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
- **Schedule**: Daily at 2 AM UTC
- **Trigger**: Manual or on push to main
- **Process**:
  1. Detects changed directories via git tag (`last-context-sync`)
  2. Rebuilds only modified FileSearchStores
  3. Logs indexing cost per sync
  4. Updates stores in Gemini File Search API

### Store Organization

Each top-level directory in the target repository becomes an isolated FileSearchStore:

```
ain3sh/docs/
├── context/               → store://context
├── Factory-AI/factory/    → store://Factory-AI/factory
└── other-docs/            → store://other-docs
```

### Cost Model

- **Indexing**: $0.15 per 1M tokens (one-time per file, repeated only when changed)
- **Storage**: Free
- **Queries**: Free (retrieved chunks charged as standard context tokens)

**Monthly Estimate:**
- 100 files (~150k tokens): $0.0225 per sync
- Daily syncs with 1-2 directories changing: **$0.25-$1/month**
- Active development (frequent changes): **$3-$6/month**

## Token Efficiency

Responses are optimized for minimal token usage:

| Mode | Tokens | Contents |
|------|--------|----------|
| Default (`include_chunks=false`) | ~500-1000 | Synthesized answer + source citations |
| With chunks (`include_chunks=true`) | ~2000-3000 | Answer + sources + chunk previews (500 chars each) |

**Previous implementation**: ~10,000+ tokens per query
**Current implementation**: ~500-1000 tokens by default (**90% reduction**)

Automatic safeguards:
- Chunk previews truncated to 500 characters
- Full responses capped at 25,000 characters
- Store metadata cached for 5 minutes

## Adapting to Your Repository

This server is built for [ain3sh/docs](https://github.com/ain3sh/docs) but can be adapted to any documentation repository.

### Requirements

1. **Repository structure**: Top-level directories become stores
2. **GitHub Actions**: Add workflow file (see `.github/workflows/sync-stores.yml`)
3. **Gemini API key**: Set as repository secret `GEMINI_API_KEY`
4. **File formats**: Markdown, text, PDF, or any Gemini-supported format

### Customization Points

**Change target repository:**
- Update GitHub Actions workflow to point to your repository
- Modify sync script to match your directory structure

**Adjust sync frequency:**
- Edit workflow cron schedule (currently `0 2 * * *`)

**Filter directories:**
- Modify sync script to include/exclude specific paths

**Custom chunking:**
- Configure `chunking_config` in `src/index.ts` (see Gemini docs)

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

```
search-context/
├── src/
│   └── index.ts           # Main implementation
├── dist/
│   └── index.js           # Compiled output (committed for npx)
├── .github/
│   └── workflows/
│       └── sync-stores.yml # Auto-sync workflow
├── package.json           # Includes bin field for CLI
├── tsconfig.json
└── README.md
```

### Testing

```bash
# Build first
npm run build

# Test locally with timeout (server runs indefinitely)
timeout 5s GEMINI_API_KEY=your_key npx .
```

**Note**: MCP servers are long-running processes. Testing is best done via MCP client integration (Claude Desktop, Claude Code, etc.).

## Troubleshooting

### Store Not Found

**Error**: `"Error: Store 'xyz' not found"`

**Solutions**:
- Verify directory exists in repository
- Check GitHub Actions workflow completed successfully
- Inspect workflow logs in repository Actions tab
- Resources may take a few minutes to sync after workflow runs

### API Key Issues

**Symptoms**: `UNAUTHENTICATED`, `Invalid API key`

**Solutions**:
- Confirm `GEMINI_API_KEY` environment variable is set
- Test key at https://aistudio.google.com/apikey
- Verify key has File Search API access enabled
- Check API quota hasn't been exceeded (free tier: 1500 RPD)

### No Results Found

**Symptoms**: Query returns "No results found"

**Solutions**:
- Try broader or more specific queries
- Verify files exist in target store directory
- Check GitHub Actions sync completed for that directory
- Use different terminology or rephrase question
- Ensure files are in supported formats (text, markdown, PDF)

### Rate Limit Exceeded

**Error**: `429`, `RESOURCE_EXHAUSTED`

**Solutions**:
- Free tier: 15 RPM (requests per minute)
- Wait 60 seconds before retrying
- Reduce query frequency
- Upgrade to paid tier: https://console.cloud.google.com/

### Server Not Loading

**Symptoms**: MCP client doesn't recognize server

**Solutions**:
- Verify `npm run build` completes without errors
- Check MCP configuration syntax (JSON valid)
- Review client logs (e.g., `~/Library/Logs/Claude/mcp*.log`)
- Ensure npx can access GitHub
- Test server manually: `GEMINI_API_KEY=key npx -y github:ain3sh/search-context`

## GitHub Actions Setup

The repository using this server needs a workflow to keep stores synced.

### Repository Secret

1. Go to **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Name: `GEMINI_API_KEY`
4. Value: Your Gemini API key from https://aistudio.google.com/apikey
5. Click **Add secret**

### Workflow File

See `.github/workflows/sync-stores.yml` in this repository for a complete example.

**Manual Trigger:**
1. Go to **Actions** tab in your repository
2. Select **Sync Context Search Stores** workflow
3. Click **Run workflow**
4. Monitor logs for sync progress and cost reporting

## Features

- **🔍 Semantic Search**: Understands meaning and context, not just keywords
- **📁 Isolated Stores**: Each directory is independently searchable
- **🔄 Auto-Sync**: GitHub Actions keeps indexes fresh
- **💰 Ultra-Low Cost**: $0.25-$1/month typical usage
- **🎯 Source Citations**: Every answer includes file references
- **⚡ Token Efficient**: 90% reduction vs naive implementations
- **📊 Dual Formats**: Markdown (human) and JSON (programmatic)
- **🔒 Smart Caching**: 5-minute store cache reduces API calls
- **📦 MCP Resources**: Standard protocol for store discovery

## License

MIT License - See LICENSE file
