// src/lib/ai.js
// Runtime AI using Anthropic API with browser CORS support

import { getSermons, searchSermonsByTitle } from "./firebase";

const ANTHROPIC_API = "https://api.anthropic.com/v1/messages";
const MODEL         = "claude-haiku-4-5-20251001";

function getApiKey() {
  return process.env.REACT_APP_ANTHROPIC_API_KEY || "";
}

async function callClaude(system, userMessage, maxTokens = 1024) {
  const key = getApiKey();
  if (!key) throw new Error("Anthropic API key not configured.");

  const response = await fetch(ANTHROPIC_API, {
    method: "POST",
    headers: {
      "Content-Type":                              "application/json",
      "x-api-key":                                 key,
      "anthropic-version":                         "2023-06-01",
      "anthropic-dangerous-direct-browser-access": "true",
    },
    body: JSON.stringify({
      model:      MODEL,
      max_tokens: maxTokens,
      system,
      messages:   [{ role: "user", content: userMessage }],
    }),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.error?.message || `API error ${response.status}`);
  }

  const data = await response.json();
  return data.content[0].text;
}

// ── RAG helpers ────────────────────────────────────────────────────────────

async function retrieveRelevantSermons(question, pastorId, max = 5) {
  const stopWords = new Set(["what","where","when","how","did","does","the","a","an",
    "and","or","in","of","to","is","was","were","about","that","this","for","my","me"]);
  const words = question.toLowerCase()
    .replace(/[^a-z0-9\s]/g, "").split(/\s+/)
    .filter(w => w.length > 3 && !stopWords.has(w));

  const results = [];
  const seen    = new Set();

  for (const word of words.slice(0, 3)) {
    try {
      const { sermons } = await getSermons({ keyword: word, pastorId, pageSize: 3 });
      for (const s of sermons) {
        if (!seen.has(s.id)) { seen.add(s.id); results.push(s); }
      }
    } catch (_) {}
  }

  if (words.length > 0) {
    try {
      const found = await searchSermonsByTitle(words[0], pastorId);
      for (const s of found.slice(0, 3)) {
        if (!seen.has(s.id)) { seen.add(s.id); results.push(s); }
      }
    } catch (_) {}
  }

  return results.slice(0, max);
}

function sermonContext(sermons) {
  return sermons.map((s, i) => [
    `SERMON ${i + 1}: "${s.title}"`,
    `Author: ${s.author}`,
    `Date: ${s.date || "Unknown"}`,
    `Summary: ${s.summary || "No summary"}`,
    `Keywords: ${(s.keywords || []).join(", ")}`,
    `Scripture: ${(s.scripture_references || []).map(r => r.reference).join(", ")}`,
  ].join("\n")).join("\n---\n");
}

// ── Public API ─────────────────────────────────────────────────────────────

export async function askCollection(question, pastor, pastorId) {
  const relevant = await retrieveRelevantSermons(question, pastorId);

  const system = `You are a knowledgeable assistant helping a family explore the sermon collection of ${pastor?.name || "a pastor"}.
Answer questions thoughtfully and accurately based on the sermon content provided.
If you don't have enough information, say so honestly.
When referencing specific sermons, mention the title.
Tone: warm, respectful, as if helping a family honor their loved one's ministry.`;

  const context = relevant.length > 0
    ? `Here are relevant sermons:\n\n${sermonContext(relevant)}\n\n`
    : "No closely matching sermons found.\n\n";

  const answer = await callClaude(system, `${context}Question: ${question}`, 1024);
  return { answer, sourcedFrom: relevant.map(s => ({ id: s.id, title: s.title })) };
}

export async function askSermon(question, sermon) {
  const system = `You are helping a family explore the sermon "${sermon.title}" by ${sermon.author}.
Answer questions accurately and warmly based only on the sermon text provided.`;
  const text    = sermon.full_text_raw || sermon.summary || "No text available.";
  return callClaude(system, `Sermon:\n\n${text.substring(0, 4000)}\n\nQuestion: ${question}`, 512);
}

export async function generateMinistrySummary(pastor, stats) {
  const system = `Write a warm, celebratory summary of a pastor's ministry for a family tribute. Reverent but personal.`;
  const msg    = `Pastor: ${pastor.name}
Total sermons: ${stats?.total_sermons || "unknown"}
Top themes: ${(stats?.top_keywords || []).slice(0, 10).map(k => k.word).join(", ")}
Top Bible books: ${(stats?.top_bible_books || []).slice(0, 8).map(b => b.book).join(", ")}
Description: ${pastor.description || ""}

Write 3-4 paragraphs.`;
  return callClaude(system, msg, 800);
}

export async function getRelatedSermons(sermon, pastorId) {
  const keyword = sermon.keywords?.[0];
  if (!keyword) return [];
  const { sermons } = await getSermons({ keyword, pastorId, pageSize: 4 });
  return sermons.filter(s => s.id !== sermon.id).slice(0, 3);
}
