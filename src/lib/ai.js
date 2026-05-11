// src/lib/ai.js
// ─────────────────────────────────────────────────────────────
// Runtime AI layer — powers "Ask the Collection" and
// per-sermon Q&A using Anthropic API + Firestore data
// ─────────────────────────────────────────────────────────────

import { getSermons, searchSermonsByTitle } from "./firebase";

const ANTHROPIC_API = "https://api.anthropic.com/v1/messages";

// API key is stored in .env — NEVER hardcoded or committed
const getApiKey = () => process.env.REACT_APP_ANTHROPIC_API_KEY;

// ── Core API call ──────────────────────────────────────────────
async function callClaude(systemPrompt, userMessage, maxTokens = 1024) {
  const key = getApiKey();
  if (!key) throw new Error("Anthropic API key not configured");

  const response = await fetch(ANTHROPIC_API, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: "claude-sonnet-4-20250514",
      max_tokens: maxTokens,
      system: systemPrompt,
      messages: [{ role: "user", content: userMessage }],
    }),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.error?.message || `API error ${response.status}`);
  }

  const data = await response.json();
  return data.content[0].text;
}

// ── Retrieve relevant sermons for RAG ──────────────────────────
async function retrieveRelevantSermons(question, pastorId, maxSermons = 5) {
  // Extract potential keywords from the question
  const stopWords = new Set(["what","where","when","how","did","does","the","a","an","and","or","in","of","to","is","was","were","about","that","this","for","my","me","any","all","have","has","been"]);
  const words = question.toLowerCase()
    .replace(/[^a-z0-9\s]/g, "")
    .split(/\s+/)
    .filter(w => w.length > 3 && !stopWords.has(w));

  // Try to find sermons by keyword match
  const results = [];
  const seen = new Set();

  for (const word of words.slice(0, 3)) {
    try {
      const { sermons } = await getSermons({ keyword: word, pastorId, pageSize: 3 });
      for (const s of sermons) {
        if (!seen.has(s.id)) { seen.add(s.id); results.push(s); }
      }
    } catch (_) { /* keyword not indexed, skip */ }
  }

  // Also try title search
  if (words.length > 0) {
    try {
      const titleResults = await searchSermonsByTitle(words[0], pastorId);
      for (const s of titleResults.slice(0, 3)) {
        if (!seen.has(s.id)) { seen.add(s.id); results.push(s); }
      }
    } catch (_) {}
  }

  return results.slice(0, maxSermons);
}

// ── Build sermon context for prompts ──────────────────────────
function buildSermonContext(sermons) {
  return sermons.map((s, i) => `
SERMON ${i + 1}: "${s.title}"
Author: ${s.author}
Date: ${s.date || "Unknown"}
Summary: ${s.summary || "No summary"}
Keywords: ${(s.keywords || []).join(", ")}
Scripture: ${(s.scripture_references || []).map(r => r.reference).join(", ")}
${s.full_text_clean ? `Text excerpt: ${s.full_text_clean.substring(0, 800)}...` : ""}
`).join("\n---\n");
}

// ── Public AI functions ────────────────────────────────────────

/**
 * Ask a question about the entire sermon collection.
 * Uses RAG: retrieves relevant sermons, then sends to Claude.
 */
export async function askCollection(question, pastor, pastorId) {
  const relevantSermons = await retrieveRelevantSermons(question, pastorId);

  const systemPrompt = `You are a knowledgeable assistant helping a family explore the sermon collection of ${pastor?.name || "a pastor"}. 
You have access to excerpts from their sermons and should answer questions thoughtfully and accurately.
If you don't have enough information from the provided sermons, say so honestly rather than guessing.
When referencing specific sermons, mention the title so the user can find them.
Tone: warm, respectful, as if helping a family honor their loved one's ministry.`;

  const context = relevantSermons.length > 0
    ? `Here are the most relevant sermons I found:\n\n${buildSermonContext(relevantSermons)}\n\n`
    : "I couldn't find sermons closely matching this query, but I'll answer based on general knowledge.\n\n";

  const userMessage = `${context}Question: ${question}`;

  const answer = await callClaude(systemPrompt, userMessage, 1024);

  return {
    answer,
    sourcedFrom: relevantSermons.map(s => ({ id: s.id, title: s.title })),
  };
}

/**
 * Ask a question about a single specific sermon.
 */
export async function askSermon(question, sermon) {
  const systemPrompt = `You are helping a family explore a specific sermon titled "${sermon.title}" by ${sermon.author}.
Answer questions about this sermon accurately and warmly.
Only reference what is in the sermon text provided.`;

  const sermonText = sermon.full_text_clean || sermon.full_text_raw || sermon.summary || "No text available.";

  const userMessage = `Here is the sermon text:\n\n${sermonText.substring(0, 4000)}\n\nQuestion: ${question}`;

  return callClaude(systemPrompt, userMessage, 512);
}

/**
 * Generate a ministry summary across all of a pastor's sermons.
 */
export async function generateMinistrySummary(pastor, stats) {
  const systemPrompt = `You are writing a warm, celebratory summary of a pastor's ministry based on their sermon collection data.
Write in a tone appropriate for a family tribute — reverent but personal.`;

  const userMessage = `Please write a 3-4 paragraph summary of this pastor's ministry based on the following data:

Pastor: ${pastor.name}
Total sermons: ${stats?.total_sermons || "unknown"}
Top themes: ${(stats?.top_keywords || []).slice(0, 10).map(k => k.word).join(", ")}
Top Bible books: ${(stats?.top_bible_books || []).slice(0, 8).map(b => b.book).join(", ")}
Years of ministry: ${pastor.years_of_ministry || "approximately 40"}
Description: ${pastor.description || ""}`;

  return callClaude(systemPrompt, userMessage, 800);
}

/**
 * Suggest related sermons based on a given sermon.
 */
export async function getRelatedSermons(sermon, pastorId) {
  const keyword = sermon.keywords?.[0];
  if (!keyword) return [];
  const { sermons } = await getSermons({ keyword, pastorId, pageSize: 4 });
  return sermons.filter(s => s.id !== sermon.id).slice(0, 3);
}
