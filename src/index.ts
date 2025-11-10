#!/usr/bin/env node
/**
 * Context Search MCP Server
 *
 * Semantic search over ain3sh/docs repository using Gemini File Search API.
 * Provides tools for searching documentation with natural language queries.
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { GoogleGenAI } from "@google/genai";

// ---------- Constants ----------

const CHARACTER_LIMIT = 25000;
const CHUNK_CHAR_LIMIT = 500; // Truncate each chunk preview to 500 chars
const MODEL_NAME = "gemini-2.5-flash";
const STORE_CACHE_TTL = 300000; // Cache stores for 5 minutes (300k ms)

// ---------- Logging ----------

const LOG_LEVEL = process.env.LOG_LEVEL || 'info';
function log(level: 'debug' | 'info' | 'error', message: string, data?: any) {
  const levels = { debug: 0, info: 1, error: 2 };
  if (levels[level] >= levels[LOG_LEVEL as 'debug' | 'info' | 'error']) {
    const timestamp = new Date().toISOString();
    const logData = data ? ` ${JSON.stringify(data)}` : '';
    console.error(`[${timestamp}] [${level.toUpperCase()}] ${message}${logData}`);
  }
}

// ---------- Types ----------

enum ResponseFormat {
  MARKDOWN = "markdown",
  JSON = "json"
}

interface StoreInfo {
  name: string;
  displayName: string;
  createTime?: string;
  updateTime?: string;
}

interface StoreCache {
  stores: Map<string, string>; // displayName -> storeName
  storeList: StoreInfo[];
  timestamp: number;
}

// ---------- Zod Schemas ----------

const SearchContextInputSchema = z.object({
  store: z.string()
    .min(1, "Store name is required")
    .max(100, "Store name must not exceed 100 characters")
    .describe("FileSearchStore name (directory path). Examples: 'context', 'Factory-AI/factory'")
    .refine(val => !val.startsWith('/') && !val.endsWith('/'), {
      message: "Store name should not start or end with '/'"
    })
    .refine(val => !val.includes('..'), {
      message: "Store name should not contain '..'"
    }),
  query: z.string()
    .min(1, "Query is required")
    .max(500, "Query must not exceed 500 characters")
    .describe("Natural language search query"),
  include_chunks: z.boolean()
    .default(false)
    .describe("Include retrieved document chunks in response (default: false). When false, only returns synthesized answer + sources. When true, includes chunk previews for verification."),
  top_k: z.number()
    .int("top_k must be an integer")
    .min(1, "top_k must be at least 1")
    .max(20, "top_k cannot exceed 20")
    .default(3)
    .describe("Number of relevant document chunks to retrieve (1-20). Only relevant when include_chunks=true."),
  response_format: z.nativeEnum(ResponseFormat)
    .default(ResponseFormat.MARKDOWN)
    .describe("Output format: 'markdown' for human-readable or 'json' for structured data"),
  metadata_filter: z.string()
    .optional()
    .describe("Optional metadata filter using List Filter syntax (google.aip.dev/160). Example: 'author=\"Robert Graves\" AND year=1934'")
}).strict();

type SearchContextInput = z.infer<typeof SearchContextInputSchema>;

// ---------- Response Formatters ----------

function formatMarkdownResponse(
  params: SearchContextInput,
  mainResponse: string,
  grounding: any
): string {
  const output: string[] = [];

  output.push(`# Search Results: ${params.store}\n\n`);
  output.push(`**Query**: ${params.query}\n\n`);
  output.push(`**Response**:\n${mainResponse}\n\n`);

  // Collect source list
  const chunks = grounding.groundingChunks || [];
  const sources = new Set<string>();
  for (const chunk of chunks) {
    if (chunk.retrievedContext?.title) {
      sources.add(chunk.retrievedContext.title);
    }
  }

  // Add sources
  output.push(`---\n\n`);
  output.push(`**Sources** (${sources.size} files):\n`);
  for (const source of Array.from(sources).sort()) {
    output.push(`  - ${source}\n`);
  }

  // Optionally add chunk previews for verification
  if (params.include_chunks) {
    output.push(`\n---\n\n`);
    output.push(`## Retrieved Context Chunks\n\n`);

    for (let i = 0; i < Math.min(params.top_k, chunks.length); i++) {
      const chunk = chunks[i];
      if (chunk.retrievedContext) {
        const ctx = chunk.retrievedContext;
        const text = ctx.text.length > CHUNK_CHAR_LIMIT
          ? ctx.text.slice(0, CHUNK_CHAR_LIMIT) + `... [truncated, ${ctx.text.length - CHUNK_CHAR_LIMIT} chars omitted]`
          : ctx.text;

        output.push(`### [${i + 1}] ${ctx.title}\n\n`);
        output.push(`${text}\n\n`);
        output.push(`---\n\n`);
      }
    }
  }

  let result = output.join('');

  // Check character limit
  if (result.length > CHARACTER_LIMIT) {
    const truncated = result.slice(0, CHARACTER_LIMIT);
    result = truncated + (
      `\n\n[TRUNCATED - Response exceeds ${CHARACTER_LIMIT} characters. ` +
      `Original length: ${result.length}. ` +
      `Try reducing top_k or disabling include_chunks.]`
    );
  }

  return result;
}

function formatJsonResponse(
  params: SearchContextInput,
  mainResponse: string,
  grounding: any
): string {
  const chunks = grounding.groundingChunks || [];
  const sources = new Set<string>();
  const chunkData: any[] = [];

  // Collect sources
  for (const chunk of chunks) {
    if (chunk.retrievedContext?.title) {
      sources.add(chunk.retrievedContext.title);
    }
  }

  // Optionally include chunk previews
  if (params.include_chunks) {
    for (let i = 0; i < Math.min(params.top_k, chunks.length); i++) {
      const chunk = chunks[i];
      if (chunk.retrievedContext) {
        const text = chunk.retrievedContext.text;
        const truncatedText = text.length > CHUNK_CHAR_LIMIT
          ? text.slice(0, CHUNK_CHAR_LIMIT)
          : text;

        chunkData.push({
          title: chunk.retrievedContext.title,
          text: truncatedText,
          truncated: text.length > CHUNK_CHAR_LIMIT,
          original_length: text.length
        });
      }
    }
  }

  const result = {
    query: params.query,
    store: params.store,
    response: mainResponse,
    sources: Array.from(sources).sort(),
    ...(params.include_chunks && { chunks: chunkData })
  };

  return JSON.stringify(result, null, 2);
}

// ---------- Error Handler ----------

function handleError(error: unknown): string {
  if (error instanceof Error) {
    const message = error.message;

    if (message.includes('API key') || message.includes('UNAUTHENTICATED')) {
      return (
        "❌ Error: Invalid or missing GEMINI_API_KEY.\n\n" +
        "**Troubleshooting Steps:**\n" +
        "1. Verify environment variable is set:\n" +
        "   ```bash\n" +
        "   echo $GEMINI_API_KEY\n" +
        "   ```\n" +
        "2. Get a new API key: https://aistudio.google.com/apikey\n" +
        "3. Ensure key has File Search API access enabled\n" +
        "4. Check key isn't expired or revoked\n\n" +
        "**For Claude Desktop**: Update `claude_desktop_config.json`:\n" +
        "```json\n" +
        "{\n" +
        "  \"mcpServers\": {\n" +
        "    \"context-search\": {\n" +
        "      \"env\": { \"GEMINI_API_KEY\": \"your-key-here\" }\n" +
        "    }\n" +
        "  }\n" +
        "}\n" +
        "```"
      );
    }

    if (message.includes('404') || message.includes('NOT_FOUND')) {
      return (
        "❌ Error: FileSearchStore not found.\n\n" +
        "**Next Steps:**\n" +
        "1. Run `list_stores` tool to see all available stores\n" +
        "2. Verify the GitHub Actions sync workflow ran successfully:\n" +
        "   https://github.com/ain3sh/docs/actions\n" +
        "3. Check if directory exists in repository\n" +
        "4. Manual sync: Go to Actions → 'Sync Context Search Stores' → 'Run workflow'"
      );
    }

    if (message.includes('429') || message.includes('RESOURCE_EXHAUSTED')) {
      return (
        "❌ Error: Gemini API rate limit exceeded.\n\n" +
        "**Rate Limit Info:**\n" +
        "- Free tier: 15 RPM (requests per minute)\n" +
        "- Upgrade at: https://console.cloud.google.com/\n\n" +
        "**Immediate Solutions:**\n" +
        "1. Wait 60 seconds before retrying\n" +
        "2. Reduce query frequency\n" +
        "3. Consider upgrading to paid tier for higher limits"
      );
    }

    if (message.includes('403') || message.includes('PERMISSION_DENIED')) {
      return (
        "❌ Error: Permission denied.\n\n" +
        "**Common Causes:**\n" +
        "1. API key doesn't have File Search API enabled\n" +
        "2. Free tier quota exceeded\n" +
        "3. Geographic restrictions (File Search not available in all regions)\n\n" +
        "**Solutions:**\n" +
        "- Enable File Search API in Google AI Studio\n" +
        "- Check billing status: https://console.cloud.google.com/billing\n" +
        "- Verify service availability: https://ai.google.dev/gemini-api/docs/available-regions"
      );
    }

    if (message.includes('DEADLINE_EXCEEDED') || message.includes('timeout')) {
      return (
        "❌ Error: Request timed out.\n\n" +
        "**Possible Causes:**\n" +
        "1. Large FileSearchStore (>20 GB) causing slow retrieval\n" +
        "2. Network connectivity issues\n" +
        "3. Gemini API service degradation\n\n" +
        "**Try:**\n" +
        "- Reduce top_k parameter (currently retrieving too many chunks)\n" +
        "- Use more specific query to narrow search scope\n" +
        "- Retry in a few minutes\n" +
        "- Check Gemini API status: https://status.cloud.google.com/"
      );
    }

    return `❌ Error: ${message}\n\nIf this persists, file an issue: https://github.com/ain3sh/docs/issues`;
  }

  return `❌ Unexpected error: ${String(error)}\n\nPlease file an issue with steps to reproduce.`;
}

// ---------- Store Cache Management ----------

let storeCache: StoreCache | null = null;

async function fetchStores(client: GoogleGenAI): Promise<StoreCache> {
  log('debug', 'Fetching stores from Gemini API');
  const pager = await client.fileSearchStores.list({ config: { pageSize: 20 } });
  const stores: any[] = [];
  let page = pager.page;
  while (true) {
    stores.push(...Array.from(page));
    if (!pager.hasNextPage()) break;
    page = await pager.nextPage();
  }

  const storeMap = new Map<string, string>();
  const storeList: StoreInfo[] = [];

  for (const store of stores) {
    if (store.displayName && store.name) {
      storeMap.set(store.displayName, store.name);
      storeList.push({
        name: store.name,
        displayName: store.displayName,
        createTime: store.createTime,
        updateTime: store.updateTime
      });
    }
  }

  log('info', 'Stores fetched and cached', { count: stores.length });

  return {
    stores: storeMap,
    storeList,
    timestamp: Date.now()
  };
}

async function getStores(client: GoogleGenAI, forceRefresh: boolean = false): Promise<StoreCache> {
  const now = Date.now();

  if (!forceRefresh && storeCache && (now - storeCache.timestamp) < STORE_CACHE_TTL) {
    log('debug', 'Using cached stores');
    return storeCache;
  }

  storeCache = await fetchStores(client);
  return storeCache;
}

// ---------- Tool Implementations ----------

async function searchContext(
  client: GoogleGenAI,
  params: SearchContextInput
): Promise<string> {
  log('info', 'searchContext called', { store: params.store, query: params.query.substring(0, 50) });
  try {
    // Get stores from cache
    const cache = await getStores(client);

    if (!cache.stores.has(params.store)) {
      const available = Array.from(cache.stores.keys()).sort();
      return (
        `Error: Store '${params.store}' not found.\n\n` +
        `Available stores:\n` +
        available.map(s => `  - ${s}`).join('\n') +
        `\n\nNote: Stores are automatically synced from repository directories. ` +
        `If this directory exists but isn't listed, it may not have been indexed yet. ` +
        `Check GitHub Actions sync status.`
      );
    }

    const storeName = cache.stores.get(params.store)!;

    // Query Gemini with file search
    const response = await client.models.generateContent({
      model: MODEL_NAME,
      contents: params.query,
      config: {
        tools: [{
          fileSearch: {
            fileSearchStoreNames: [storeName],
            ...(params.metadata_filter && { metadataFilter: params.metadata_filter })
          }
        }],
        temperature: 0.0
      }
    });
    log('debug', 'Gemini API response received', { hasGrounding: !!response.candidates?.[0]?.groundingMetadata });

    // Extract grounding metadata
    if (!response.candidates || !response.candidates[0]?.groundingMetadata) {
      return (
        `No results found in store '${params.store}' for query: ${params.query}\n\n` +
        `Try:\n` +
        `  - Using different keywords\n` +
        `  - Being more specific or more general\n` +
        `  - Searching a different store`
      );
    }

    const grounding = response.candidates[0].groundingMetadata;
    const mainResponse = response.text || "No response generated";

    // Format response based on requested format
    if (params.response_format === ResponseFormat.JSON) {
      return formatJsonResponse(params, mainResponse, grounding);
    } else {
      return formatMarkdownResponse(params, mainResponse, grounding);
    }
  } catch (error) {
    log('error', 'Search failed', { error: error instanceof Error ? error.message : String(error) });
    return handleError(error);
  }
}


// ---------- Main Function ----------

async function main() {
  // Validate environment
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    console.error("ERROR: GEMINI_API_KEY environment variable is required");
    console.error("Get your key from: https://aistudio.google.com/apikey");
    process.exit(1);
  }

  // Initialize Gemini client
  const client = new GoogleGenAI({ apiKey });

  // Create MCP server
  const server = new McpServer({
    name: "context-search-mcp",
    version: "1.0.0"
  });

  // Register resources for each store dynamically
  // Fetch stores and register each one as a resource
  try {
    const cache = await getStores(client);
    log('info', 'Registering store resources', { count: cache.storeList.length });

    for (const store of cache.storeList) {
      const uri = `store://${store.displayName}`;
      server.registerResource(
        store.displayName,
        uri,
        {
          title: `${store.displayName} Documentation Store`,
          description: `FileSearchStore for '${store.displayName}' documentation. Use with search_context tool.`,
          mimeType: "application/json"
        },
        async (resourceUri) => {
          log('debug', 'Resource read', { uri: resourceUri.href });
          const content = JSON.stringify({
            displayName: store.displayName,
            name: store.name,
            createTime: store.createTime,
            updateTime: store.updateTime,
            usage: `Use this store with search_context tool: { store: "${store.displayName}", query: "your query" }`
          }, null, 2);

          return {
            contents: [{
              uri: resourceUri.href,
              mimeType: "application/json",
              text: content
            }]
          };
        }
      );
    }
    log('info', 'Store resources registered successfully');
  } catch (error) {
    log('error', 'Failed to register store resources', { error });
    // Continue anyway - tools can still work even if resources aren't registered
  }

  // Register search_context tool
  server.registerTool(
    "search_context",
    {
      title: "Search Context Documentation",
      description: `Search documentation using semantic search powered by Gemini File Search API.

**Simple Usage**: Just provide store name and query. Sane defaults handle everything else.

Queries FileSearchStores automatically synced from ain3sh/docs repository. Each top-level directory maps to its own FileSearchStore.

**Required Parameters:**
  - store (string): FileSearchStore name (e.g., 'context', 'Factory-AI/factory')
    Discover available stores via MCP Resources (resources/list)
  - query (string): Natural language search query

**Optional Parameters (rarely needed):**
  - include_chunks (boolean, default: false): Include document chunk previews for verification
    When false: Returns only synthesized answer + source citations (token-efficient)
    When true: Includes truncated chunk previews (500 chars each) for evidence
  - top_k (number, default: 3): Number of chunks to retrieve (only relevant if include_chunks=true)
  - response_format ('markdown' | 'json', default: 'markdown'): Output format
  - metadata_filter (string): Advanced filtering (syntax: google.aip.dev/160)

**Default Response** (include_chunks=false):
  - Synthesized answer from semantic search
  - Source file citations
  - ~500-1000 tokens total

**With Chunks** (include_chunks=true):
  - Synthesized answer
  - Source file citations
  - Document chunk previews (truncated to 500 chars each)
  - ~2000-3000 tokens total

**Examples:**
  - Simple: {store: "context", query: "How does File Search chunking work?"}
  - With evidence: {store: "context", query: "authentication flow", include_chunks: true}
  - Advanced filtering: {store: "context", query: "books", metadata_filter: 'author="Robert Graves"'}

**Error Handling:**
  - Invalid store → Lists available stores
  - No results → Suggests alternative queries
  - Responses truncated at 25,000 chars if needed`,
      inputSchema: SearchContextInputSchema.shape,
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: true
      }
    },
    async (params: SearchContextInput) => {
      const result = await searchContext(client, params);
      return {
        content: [{
          type: "text" as const,
          text: result
        }]
      };
    }
  );

  // Connect to stdio transport
  const transport = new StdioServerTransport();
  await server.connect(transport);

  console.error("Context Search MCP server running via stdio");
}

// Run the server
main().catch((error) => {
  console.error("Server error:", error);
  process.exit(1);
});
