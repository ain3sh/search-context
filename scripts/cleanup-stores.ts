#!/usr/bin/env tsx
/**
 * One-time cleanup script to remove incorrectly created FileSearchStores.
 *
 * This script deletes stores that were created from ain3sh/search-context
 * internal directories instead of from ain3sh/docs documentation.
 */

import { GoogleGenAI } from "@google/genai";

async function main() {
  // Validate API key
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    console.error("❌ ERROR: GEMINI_API_KEY environment variable is required");
    console.error("   Set it with: export GEMINI_API_KEY=your_key_here");
    process.exit(1);
  }

  // Initialize client
  const client = new GoogleGenAI({ apiKey });

  // Define stores that should be deleted (from search-context repo)
  // These are internal project directories, not documentation
  const storesToDelete = [
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
    'Factory-AI',  // Empty namespace container - actual docs are in Factory-AI/factory
  ];

  // Stores that should be KEPT (legitimate documentation from ain3sh/docs)
  const storesToKeep = [
    'context',
    'Factory-AI',
    'Factory-AI/factory',
  ];

  console.log("🔍 Fetching all FileSearchStores...");
  let stores: any[] = [];

  try {
    const pager = await client.fileSearchStores.list({ config: { pageSize: 20 } });
    let page = pager.page;
    while (true) {
      stores.push(...Array.from(page));
      if (!pager.hasNextPage()) break;
      page = await pager.nextPage();
    }
    console.log(`   Found ${stores.length} total stores\n`);
  } catch (error) {
    console.error(`❌ Error fetching stores: ${error}`);
    process.exit(1);
  }

  // Analyze stores
  let deletedCount = 0;
  let keptCount = 0;
  let unknownCount = 0;

  for (const store of stores) {
    const storeName = store.displayName || "(no display name)";
    const storeId = store.name;

    if (storesToDelete.includes(storeName)) {
      // Delete incorrect store
      console.log(`🗑️  Deleting: ${storeName}`);
      console.log(`   ID: ${storeId}`);
      try {
        await client.fileSearchStores.delete({
          name: storeId,
          config: { force: true }
        });
        console.log(`   ✅ Successfully deleted\n`);
        deletedCount++;
      } catch (error) {
        console.error(`   ❌ Error deleting: ${error}\n`);
      }
    } else if (storesToKeep.includes(storeName)) {
      // Keep legitimate documentation store
      console.log(`✅ Keeping: ${storeName}`);
      console.log(`   ID: ${storeId}`);
      console.log(`   (Legitimate documentation store)\n`);
      keptCount++;
    } else {
      // Unknown store - list for manual review
      console.log(`⚠️  Unknown: ${storeName}`);
      console.log(`   ID: ${storeId}`);
      console.log(`   (Not in cleanup or keep list - review manually)\n`);
      unknownCount++;
    }
  }

  // Summary
  console.log("=".repeat(60));
  console.log("📊 CLEANUP SUMMARY");
  console.log("=".repeat(60));
  console.log(`   Deleted: ${deletedCount} stores`);
  console.log(`   Kept: ${keptCount} stores`);
  console.log(`   Unknown: ${unknownCount} stores (manual review needed)`);
  console.log(`   Total processed: ${stores.length} stores`);
  console.log("=".repeat(60));

  if (unknownCount > 0) {
    console.log("\n⚠️  WARNING: Some unknown stores were found.");
    console.log("   Review them manually and update this script if needed.");
  }

  console.log("\n✅ Cleanup complete!");
}

main().catch((error) => {
  console.error("Fatal error:", error);
  process.exit(1);
});
