#!/usr/bin/env node
import { XMLParser } from 'fast-xml-parser';
import { readFileSync } from 'fs';
import { GoogleGenAI } from '@google/genai';
import { join } from 'path';

interface QAPair {
  question: string;
  answer: string;
}

async function runEvaluation() {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    console.error("❌ GEMINI_API_KEY environment variable required");
    process.exit(1);
  }

  const client = new GoogleGenAI({ apiKey });

  // Parse questions
  const xmlPath = join(__dirname, 'questions.xml');
  const xmlContent = readFileSync(xmlPath, 'utf-8');
  const parser = new XMLParser();
  const data = parser.parse(xmlContent);
  const qaPairs: QAPair[] = Array.isArray(data.evaluation.qa_pair)
    ? data.evaluation.qa_pair
    : [data.evaluation.qa_pair];

  console.log(`\n${'='.repeat(60)}`);
  console.log(`Running ${qaPairs.length} evaluation questions...`);
  console.log(`${'='.repeat(60)}\n`);

  let passed = 0;
  let failed = 0;

  for (let i = 0; i < qaPairs.length; i++) {
    const pair = qaPairs[i];
    const questionNum = i + 1;

    try {
      // Search context store
      const pager = await client.fileSearchStores.list({ config: { pageSize: 20 } });
      const stores: any[] = [];
      let page = pager.page;
      while (true) {
        stores.push(...Array.from(page));
        if (!pager.hasNextPage()) break;
        page = await pager.nextPage();
      }

      const contextStore = stores.find(s => s.displayName === 'context');
      if (!contextStore) {
        console.error(`❌ SKIP [${questionNum}/${qaPairs.length}]: Context store not found`);
        failed++;
        continue;
      }

      const response = await client.models.generateContent({
        model: "gemini-2.5-flash",
        contents: pair.question,
        config: {
          tools: [{
            fileSearch: {
              fileSearchStoreNames: [contextStore.name]
            }
          }],
          temperature: 0.0
        }
      });

      const answer = response.text || "";
      const expectedAnswer = pair.answer.toLowerCase().trim();
      const gotAnswer = answer.toLowerCase().trim();

      if (gotAnswer.includes(expectedAnswer)) {
        console.log(`✅ PASS [${questionNum}/${qaPairs.length}]: ${pair.question.substring(0, 80)}...`);
        passed++;
      } else {
        console.log(`❌ FAIL [${questionNum}/${qaPairs.length}]: ${pair.question.substring(0, 80)}...`);
        console.log(`   Expected: "${pair.answer}"`);
        console.log(`   Got: "${answer.substring(0, 100)}..."`);
        failed++;
      }
    } catch (error) {
      console.error(`❌ ERROR [${questionNum}/${qaPairs.length}]: ${pair.question.substring(0, 80)}...`);
      console.error(`   ${error instanceof Error ? error.message : String(error)}`);
      failed++;
    }
  }

  console.log(`\n${'='.repeat(60)}`);
  console.log(`📊 Evaluation Results`);
  console.log(`${'='.repeat(60)}`);
  console.log(`Passed: ${passed}`);
  console.log(`Failed: ${failed}`);
  console.log(`Total: ${passed + failed}`);
  console.log(`Success rate: ${((passed / (passed + failed)) * 100).toFixed(1)}%`);
  console.log(`${'='.repeat(60)}\n`);

  if (passed / (passed + failed) >= 0.8) {
    console.log(`✅ Evaluation PASSED (≥80% success rate)`);
    process.exit(0);
  } else {
    console.log(`❌ Evaluation FAILED (<80% success rate)`);
    process.exit(1);
  }
}

runEvaluation().catch(error => {
  console.error("Fatal error:", error);
  process.exit(1);
});
