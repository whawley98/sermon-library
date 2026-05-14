// src/lib/ai.js
// AI layer — Claude API calls for the Sermon Library platform.
// All AI interactions go through this file.

import { getSermons, searchSermons, getStats, getScriptureRefs } from "./firebase";

const ANTHROPIC_API = "https://api.anthropic.com/v1/messages";
const MODEL         = "claude-haiku-4-5-20251001";

function getApiKey() {
  return process.env.REACT_APP_ANTHROPIC_API_KEY || "";
}

// ── Core Claude call ───────────────────────────────────────────────────────

async function callClaude(system, userMessage, maxTokens = 1024) {
  const key = getApiKey();
  if (!key) throw new Error("Anthropic API key not configured. Add REACT_APP_ANTHROPIC_API_KEY to GitHub secrets.");

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

// ══════════════════════════════════════════════════════════════════════════
//  COLLECTION-LEVEL ASK
//  Uses stats + relevant sermon retrieval for accurate big-picture answers.
// ══════════════════════════════════════════════════════════════════════════

/**
 * Determine if a question is "big picture" (about the whole collection)
 * or "specific" (about particular sermons/topics).
 */
function isBigPictureQuestion(question) {
  const bigPictureWords = [
    "most often", "most frequently", "favorite", "how many", "total",
    "throughout", "whole", "entire", "all", "career", "ministry",
    "over the years", "across", "pattern", "trend", "emphasis",
  ];
  const q = question.toLowerCase();
  return bigPictureWords.some(w => q.includes(w));
}

/**
 * Build context from stats for big-picture questions.
 * This gives Claude accurate data without retrieving individual sermons.
 */
function statsContext(stats, pastor) {
  if (!stats) return "";
  const topKw    = (stats.top_keywords    || []).slice(0, 15).map(k => `${k.word} (${k.count})`).join(", ");
  const topBooks = (stats.top_bible_books || []).slice(0, 15).map(b => `${b.book} (${b.count})`).join(", ");
  const topVerse = (stats.top_verses      || []).slice(0,  5).map(v => `${v.reference} (${v.count})`).join(", ");
  const decades  = Object.entries(stats.sermons_by_decade || {})
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([d, c]) => `${d}: ${c} sermons`).join(", ");

  return `COLLECTION STATISTICS FOR ${(pastor?.name || "this pastor").toUpperCase()}:
Total sermons: ${stats.total_sermons || "unknown"}
Sermons by decade: ${decades || "unknown"}
Most referenced Bible books: ${topBooks || "unknown"}
Most used keywords/themes: ${topKw || "unknown"}
Most cited verses: ${topVerse || "unknown"}
`;
}

/**
 * Retrieve relevant sermons using Algolia search + keyword matching.
 */
async function retrieveRelevantSermons(question, pastorId, max = 6) {
  const stopWords = new Set([
    "what","where","when","how","did","does","the","a","an","and","or",
    "in","of","to","is","was","were","about","that","this","for","my",
    "me","any","all","have","has","been","his","her","their","which",
  ]);

  const words = question.toLowerCase()
    .replace(/[^a-z0-9\s]/g, "")
    .split(/\s+/)
    .filter(w => w.length > 3 && !stopWords.has(w));

  const results = [];
  const seen    = new Set();

  // Algolia full-text search first
  try {
    const hits = await searchSermons(question, pastorId, 5);
    for (const s of hits) {
      if (!seen.has(s.id)) { seen.add(s.id); results.push(s); }
    }
  } catch (_) {}

  // Keyword-based Firestore search as supplement
  for (const word of words.slice(0, 3)) {
    if (results.length >= max) break;
    try {
      const { sermons } = await getSermons({ keyword: word, pastorId, pageSize: 3 });
      for (const s of sermons) {
        if (!seen.has(s.id)) { seen.add(s.id); results.push(s); }
      }
    } catch (_) {}
  }

  return results.slice(0, max);
}

/**
 * Build sermon context string for Claude prompt.
 */
async function buildSermonContext(sermons) {
  const sections = await Promise.all(sermons.map(async (s, i) => {
    // Try to get scripture refs from separate collection
    let refs = [];
    try {
      refs = await getScriptureRefs(s.id);
    } catch (_) {}
    const refStr = refs.length > 0
      ? refs.map(r => r.reference).join(", ")
      : (s.bible_books || []).join(", ");

    return [
      `SERMON ${i + 1}: "${s.title}"`,
      `Author: ${s.author || "Unknown"}`,
      `Date: ${s.date || "Unknown"}  Decade: ${s.decade || "Unknown"}`,
      `Summary: ${s.summary || "No summary available"}`,
      `Main theme: ${s.main_theme || ""}`,
      `Keywords: ${(s.keywords || []).join(", ")}`,
      `Scripture: ${refStr}`,
    ].filter(Boolean).join("\n");
  }));
  return sections.join("\n---\n");
}

// ── Public: Ask the Collection ─────────────────────────────────────────────

export async function askCollection(question, pastor, pastorId) {
  const bigPicture = isBigPictureQuestion(question);

  // For big-picture questions, fetch stats AND a few relevant sermons
  const [stats, relevant] = await Promise.all([
    bigPicture ? getStats(pastorId) : Promise.resolve(null),
    retrieveRelevantSermons(question, pastorId, bigPicture ? 3 : 6),
  ]);

  const system = `You are a knowledgeable assistant helping a family explore the sermon collection of ${pastor?.name || "a pastor"}.
Answer questions thoughtfully and accurately based on the data provided.
Be specific — cite actual sermon titles, dates, themes, and scripture references when available.
If asked about patterns or frequencies, use the statistics provided, not guesses.
Tone: warm, respectful, as if helping a family honor their loved one's ministry.
Format your response using markdown — use **bold** for emphasis, bullet points for lists.`;

  const contextParts = [];
  if (stats) contextParts.push(statsContext(stats, pastor));
  if (relevant.length > 0) {
    const sermonCtx = await buildSermonContext(relevant);
    contextParts.push(`RELEVANT SERMONS:\n${sermonCtx}`);
  }

  const context = contextParts.length > 0
    ? contextParts.join("\n\n")
    : "No specific sermons found for this query.";

  const answer = await callClaude(
    system,
    `${context}\n\nQuestion: ${question}`,
    1200,
  );

  return {
    answer,
    sourcedFrom: relevant.map(s => ({ id: s.id, title: s.title })),
  };
}

// ── Public: Ask About a Specific Sermon ───────────────────────────────────

export async function askSermon(question, sermon, scriptureRefs = []) {
  const refStr = scriptureRefs.length > 0
    ? scriptureRefs.map(r => `${r.reference}: ${r.context || ""}`).join("\n")
    : "";

  const system = `You are helping a family explore the sermon "${sermon.title}" by ${sermon.author || "the pastor"}.
Answer questions accurately and warmly based on the sermon content provided.
Be specific — reference actual points from the sermon when answering.
Format your response using markdown for readability.`;

  const text    = sermon.full_text_raw || sermon.summary || "No text available.";
  const context = [
    `Title: ${sermon.title}`,
    `Author: ${sermon.author || "Unknown"}`,
    `Date: ${sermon.date || "Unknown"}`,
    `Main theme: ${sermon.main_theme || ""}`,
    refStr ? `Scripture references:\n${refStr}` : "",
    `\nSermon text:\n${text.substring(0, 5000)}`,
  ].filter(Boolean).join("\n");

  return callClaude(system, `${context}\n\nQuestion: ${question}`, 800);
}

// ── Public: Generate Ministry Summary ─────────────────────────────────────

export async function generateMinistrySummary(pastor, stats) {
  if (!pastor || !stats) throw new Error("Pastor and stats required");

  const topThemes = (stats.top_keywords    || []).slice(0, 10).map(k => k.word).join(", ");
  const topBooks  = (stats.top_bible_books || []).slice(0,  8).map(b => b.book).join(", ");
  const decades   = Object.entries(stats.sermons_by_decade || {})
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([d, c]) => `${d} (${c} sermons)`).join(", ");

  const system = `Write a warm, celebratory tribute to a pastor's ministry.
Tone: reverent yet personal, as if written for a family gathering or memorial service.
Format with markdown — use paragraph breaks, occasional **bold** for emphasis.
Write 3-4 substantial paragraphs.`;

  const msg = `Please write a tribute summary of this pastor's ministry:

Pastor: ${pastor.name}
Description: ${pastor.description || ""}
Total sermons preserved: ${stats.total_sermons || "unknown"}
Decades of ministry: ${decades || "unknown"}
Most emphasized themes: ${topThemes || "unknown"}
Most preached Bible books: ${topBooks || "unknown"}
Total scripture references catalogued: ${stats.total_references || "unknown"}`;

  return callClaude(system, msg, 1000);
}

// ── Public: Get Related Sermons ────────────────────────────────────────────

export async function getRelatedSermons(sermon, pastorId) {
  if (!sermon) return [];

  const results = [];
  const seen    = new Set([sermon.id]);

  // Search by main theme
  if (sermon.main_theme) {
    try {
      const hits = await searchSermons(sermon.main_theme, pastorId, 4);
      for (const s of hits) {
        if (!seen.has(s.id)) { seen.add(s.id); results.push(s); }
      }
    } catch (_) {}
  }

  // Supplement with keyword matching
  if (results.length < 3 && sermon.keywords?.length > 0) {
    try {
      const { sermons } = await getSermons({
        keyword:  sermon.keywords[0],
        pastorId,
        pageSize: 5,
      });
      for (const s of sermons) {
        if (!seen.has(s.id)) { seen.add(s.id); results.push(s); }
      }
    } catch (_) {}
  }

  return results.slice(0, 3);
}
