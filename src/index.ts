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
const MODEL_NAME = "gemini-2.5-flash";

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
  top_k: z.number()
    .int("top_k must be an integer")
    .min(1, "top_k must be at least 1")
    .max(20, "top_k cannot exceed 20")
    .default(5)
    .describe("Number of relevant document chunks to retrieve (1-20)"),
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
  output.push(`---\n\n`);
  output.push(`## Retrieved Context\n\n`);

  // Add top_k chunks with citations
  const chunks = grounding.groundingChunks || [];
  for (let i = 0; i < Math.min(params.top_k, chunks.length); i++) {
    const chunk = chunks[i];
    if (chunk.retrievedContext) {
      const ctx = chunk.retrievedContext;
      output.push(`### [${i + 1}] ${ctx.title}\n\n`);
      output.push(`${ctx.text}\n\n`);
      output.push(`---\n\n`);
    }
  }

  // Add source list
  const sources = new Set<string>();
  for (const chunk of chunks) {
    if (chunk.retrievedContext?.title) {
      sources.add(chunk.retrievedContext.title);
    }
  }

  output.push(`**Sources** (${sources.size} files):\n`);
  for (const source of Array.from(sources).sort()) {
    output.push(`  - ${source}\n`);
  }

  let result = output.join('');

  // Check character limit
  if (result.length > CHARACTER_LIMIT) {
    const truncated = result.slice(0, CHARACTER_LIMIT);
    result = truncated + (
      `\n\n[TRUNCATED - Response exceeds ${CHARACTER_LIMIT} characters. ` +
      `Original length: ${result.length}. ` +
      `Try reducing top_k or using more specific query.]`
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

  for (let i = 0; i < Math.min(params.top_k, chunks.length); i++) {
    const chunk = chunks[i];
    if (chunk.retrievedContext) {
      chunkData.push({
        title: chunk.retrievedContext.title,
        text: chunk.retrievedContext.text
      });
      if (chunk.retrievedContext.title) {
        sources.add(chunk.retrievedContext.title);
      }
    }
  }

  const result = {
    query: params.query,
    store: params.store,
    response: mainResponse,
    chunks: chunkData,
    sources: Array.from(sources).sort()
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

// ---------- Tool Implementations ----------

async function searchContext(
  client: GoogleGenAI,
  params: SearchContextInput
): Promise<string> {
  log('info', 'searchContext called', { store: params.store, query: params.query.substring(0, 50) });
  try {
    // List available stores and validate
    const pager = await client.fileSearchStores.list({ config: { pageSize: 20 } });
    const stores: any[] = [];
    let page = pager.page;
    while (true) {
      stores.push(...Array.from(page));
      if (!pager.hasNextPage()) break;
      page = await pager.nextPage();
    }

    const storeMap = new Map<string, string>();
    for (const store of stores) {
      if (store.displayName && store.name) {
        storeMap.set(store.displayName, store.name);
      }
    }
    log('debug', 'Retrieved stores', { count: stores.length });

    if (!storeMap.has(params.store)) {
      const available = Array.from(storeMap.keys()).sort();
      return (
        `Error: Store '${params.store}' not found.\n\n` +
        `Available stores:\n` +
        available.map(s => `  - ${s}`).join('\n') +
        `\n\nNote: Stores are automatically synced from repository directories. ` +
        `If this directory exists but isn't listed, it may not have been indexed yet. ` +
        `Check GitHub Actions sync status.`
      );
    }

    const storeName = storeMap.get(params.store)!;

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

async function listStores(client: GoogleGenAI): Promise<string> {
  try {
    const pager = await client.fileSearchStores.list({ config: { pageSize: 20 } });
    const stores: any[] = [];
    let page = pager.page;
    while (true) {
      stores.push(...Array.from(page));
      if (!pager.hasNextPage()) break;
      page = await pager.nextPage();
    }

    if (stores.length === 0) {
      return (
        "No FileSearchStores found.\n\n" +
        "This could mean:\n" +
        "  - The GitHub Actions sync hasn't run yet\n" +
        "  - No directories in ain3sh/docs repository to index\n" +
        "  - API key doesn't have access to the project stores\n\n" +
        "Check the GitHub Actions workflow logs for more information."
      );
    }

    const output: string[] = [];
    output.push(`# Available Context Stores\n\n`);
    output.push(`Total: ${stores.length} stores\n\n`);

    // Sort by display name
    const sortedStores = stores.sort((a: any, b: any) => {
      const nameA = a.displayName || a.name;
      const nameB = b.displayName || b.name;
      return nameA.localeCompare(nameB);
    });

    for (const store of sortedStores) {
      const displayName = store.displayName || "(no display name)";
      output.push(`- **${displayName}**\n`);
      output.push(`  - ID: \`${store.name}\`\n`);
      if (store.createTime) {
        output.push(`  - Created: ${store.createTime}\n`);
      }
      if (store.updateTime) {
        output.push(`  - Updated: ${store.updateTime}\n`);
      }
      output.push(`\n`);
    }

    output.push(`\n**Usage**:\n`);
    output.push(`\`\`\`\n`);
    output.push(`search_context(\n`);
    output.push(`  store: "context",  // Use display name here\n`);
    output.push(`  query: "your search query"\n`);
    output.push(`)\n`);
    output.push(`\`\`\`\n`);

    return output.join('');
  } catch (error) {
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

  // Register search_context tool
  server.registerTool(
    "search_context",
    {
      title: "Search Context Documentation",
      description: `Search documentation using semantic search powered by Gemini File Search API.

Queries FileSearchStores automatically synced from ain3sh/docs repository. Each top-level directory maps to its own FileSearchStore. Returns relevant content with citations showing source files.

Args:
  - store (string): FileSearchStore name (directory path like 'context' or 'Factory-AI/factory')
  - query (string): Natural language search query
  - top_k (number): Number of chunks to retrieve (1-20, default: 5)
  - response_format ('markdown' | 'json'): Output format (default: 'markdown')
  - metadata_filter (string, optional): Filter by custom metadata (syntax: google.aip.dev/160)

Returns:
  Markdown format: Human-readable results with headers, context chunks, and source citations
  JSON format: Structured data with query, response, chunks array, and sources array

Examples:
  - Use when: "Search Factory-AI docs for authentication flow" -> {store: "Factory-AI/factory", query: "authentication flow"}
  - Use when: "Find Gemini API usage patterns" -> {store: "context", query: "Gemini API usage", top_k: 3}
  - Use when: "Find docs authored by Graves" -> {store: "context", query: "book recommendations", metadata_filter: 'author="Robert Graves"'}

Error Handling:
  - Returns "Error: Store not found" with list of available stores if invalid store name
  - Returns "No results found" with suggestions if query returns empty
  - Truncates responses exceeding 25,000 characters with clear message`,
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

  // Register list_stores tool
  server.registerTool(
    "list_stores",
    {
      title: "List Available Stores",
      description: `List all available FileSearchStores for documentation search.

Returns the names of all indexed documentation stores. Use these names as the 'store' parameter in search_context tool calls.

Returns:
  Markdown-formatted list of available stores with their display names, IDs, and timestamps.

Examples:
  - Use when: "What documentation stores are available?"
  - Use when: Need to find the correct store name before searching`,
      inputSchema: {},
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: true
      }
    },
    async () => {
      const result = await listStores(client);
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
