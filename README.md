# Context Search MCP Server

> TypeScript MCP server for semantic search over documentation using Google's Gemini File Search API

**Semantic search** that understands meaning, not just keywords. Search across documentation repositories with natural language queries and get results with citations.

## Why Context Search?

Traditional documentation search has limitations:

- **Keyword matching only** - Miss relevant results that use different terminology
- **No semantic understanding** - Can't interpret "how to authenticate users" vs "user login implementation"
- **Manual navigation** - Browse through folders and files to find what you need
- **No citation tracking** - Hard to verify where information comes from

Context Search solves these by:

- **Semantic retrieval** powered by Gemini's File Search API
- **Natural language queries** - Ask questions like you would a colleague
- **Automatic citations** - Every result shows which files were used
- **Directory-scoped searches** - Search specific documentation collections
- **Auto-synced indexes** - GitHub Actions keeps documentation up-to-date

## Installation

### Recommended: Direct from GitHub

```bash
npx -y github:ain3sh/docs/search-tool
```

This downloads and runs the latest version directly. No installation or repository cloning required.

### Alternative: Local Development

```bash
git clone https://github.com/ain3sh/docs.git
cd docs/search-tool
npm install
npm run build
npm start
```

## Usage

### For Claude Desktop Users

Add this to your Claude Desktop configuration file at `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "context-search": {
      "command": "npx",
      "args": ["-y", "github:ain3sh/docs/search-tool"],
      "env": {
        "GEMINI_API_KEY": "your_api_key_here"
      }
    }
  }
}
```

**Get your API key**: https://aistudio.google.com/apikey

Restart Claude Desktop to load the server.

### For CLI Agents (Project-Level)

Create `.mcp.json` in your project root:

```json
{
  "mcpServers": {
    "context-search": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "github:ain3sh/docs/search-tool"],
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

## Features

- 🔍 **Semantic Search** - Understands meaning and context, not just keywords
- 📁 **Directory Isolation** - Each top-level directory maps to its own FileSearchStore
- 🔄 **Auto-Sync** - GitHub Actions updates indexes daily at 2 AM UTC
- 💰 **Ultra-Low Cost** - $0.25-$6/month for active development (~$0.0225 per 100 files)
- 🎯 **Citations Included** - Every response shows source files used
- 📊 **Dual Formats** - Markdown for humans, JSON for programmatic use
- ⚡ **Character Limits** - Automatic truncation at 25k chars with clear messaging

## Configuration

### Tool Parameters

These are controlled by the LLM agent per request:

#### `search_context`

Search documentation with natural language queries.

**Parameters:**
- `store` (string, required): FileSearchStore name - directory path like "context" or "Factory-AI/factory"
- `query` (string, required): Natural language search query
- `top_k` (number, optional): Number of chunks to retrieve (1-20, default: 5)
- `response_format` (enum, optional): "markdown" or "json" (default: "markdown")

**Example:**
```typescript
search_context({
  store: "context",
  query: "How does Gemini's File Search handle chunking?",
  top_k: 3,
  response_format: "markdown"
})
```

#### `list_stores`

List all available documentation stores.

**No parameters required.**

**Example:**
```typescript
list_stores()
```

### Server Configuration

Set once via environment variables. Not configurable per-request.

#### Environment Variables

- `GEMINI_API_KEY` (required): Your Gemini API key from https://aistudio.google.com/apikey

## Use Cases

### 1. Finding Implementation Examples

**Scenario**: Need to understand how File Search chunking works

```typescript
search_context({
  store: "context",
  query: "file search chunking configuration and token limits",
  top_k: 5
})
```

Returns relevant documentation with chunking examples and configuration options, including citations to specific files.

### 2. Cross-Repository Search

**Scenario**: Search across different documentation collections

```typescript
// First, see what's available
list_stores()

// Then search specific collection
search_context({
  store: "Factory-AI/factory",
  query: "authentication flow setup",
  top_k: 3
})
```

### 3. Programmatic Integration

**Scenario**: Build tooling that needs structured responses

```typescript
search_context({
  store: "context",
  query: "Gemini API rate limits and quotas",
  response_format: "json"
})
```

Returns structured JSON with `query`, `response`, `chunks[]`, and `sources[]` fields.

## Architecture

```
User Query
    ↓
search_context(store="context", query="...")
    ↓
Validate store exists
    ↓
Gemini File Search API
    ↓
Semantic retrieval from FileSearchStore
    ↓
Format results (markdown or JSON)
    ↓
Return with citations
```

**Indexing Flow:**
- GitHub Actions runs daily at 2 AM UTC
- Detects changed directories via git tag (`last-context-sync`)
- Rebuilds only changed FileSearchStores
- Logs cost per sync

**Cost Model:**
- **Indexing**: $0.15 per 1M tokens (one-time per file per sync)
- **Storage**: Free
- **Queries**: Free (retrieved chunks charged as context tokens)

**Typical Monthly Cost:**
- 100 files (150k tokens) = $0.0225 per sync
- Daily sync with 1-2 dirs changing = **$0.25-$1/month**

## Development

### Building from Source

```bash
# Install dependencies
npm install

# Build TypeScript
npm run build

# Development with auto-reload
npm run dev
```

### Project Structure

```
search-tool/
├── src/index.ts              # Main implementation (411 lines)
├── dist/index.js             # Compiled with shebang (committed for npx)
├── package.json              # Includes bin field for CLI execution
├── tsconfig.json
└── README.md
```

### Testing Locally

```bash
# Build first
npm run build

# Test with environment variable
GEMINI_API_KEY=your_key npx .
```

## Troubleshooting

### "Store not found" error
- Ensure GitHub Actions sync has run successfully
- Check workflow logs in repository Actions tab
- Verify directory exists in the repository

### API Key Issues
- Confirm `GEMINI_API_KEY` is set in environment
- Test key at https://aistudio.google.com
- Verify key has File Search API access
- Check API quota hasn't been exceeded

### No Results Found
- Try broader or more specific keywords
- Verify files exist in the target store directory
- Check GitHub Actions sync status
- Try different terminology

### Server Not Loading
- Verify npm dependencies installed
- Check `npm run build` completes successfully
- Review Claude Desktop logs for errors
- Ensure npx can access GitHub

## GitHub Actions Setup

The sync workflow requires one repository secret:

1. Go to repository **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Name: `GEMINI_API_KEY`
4. Value: Your Gemini API key
5. Click **Add secret**

Manual trigger:
1. Go to **Actions** tab
2. Select **Sync Context Search Stores** workflow
3. Click **Run workflow**
4. Monitor logs for completion and cost reporting

## License

MIT License - See repository LICENSE file
