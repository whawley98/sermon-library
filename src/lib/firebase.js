// src/lib/firebase.js
// Complete data access layer for the Sermon Library platform.
// All Firestore queries live here — nothing else touches the DB directly.

import { initializeApp } from "firebase/app";
import {
  getFirestore,
  collection,
  doc,
  getDoc,
  getDocs,
  query,
  where,
  orderBy,
  limit,
  startAfter,
} from "firebase/firestore";

// ── Firebase config ────────────────────────────────────────────────────────
const firebaseConfig = {
  apiKey:            "AIzaSyBlrNposSO9q-fRORmmG6a_0bLy3TkXqgc",
  authDomain:        "sermon-library-89f46.firebaseapp.com",
  projectId:         "sermon-library-89f46",
  storageBucket:     "sermon-library-89f46.firebasestorage.app",
  messagingSenderId: "375159141051",
  appId:             "1:375159141051:web:337cc6aee9c01c8f12af9e",
};

const app = initializeApp(firebaseConfig);
export const db = getFirestore(app);

// ── Algolia config ─────────────────────────────────────────────────────────
const ALGOLIA_APP_ID    = "A4149APL2C";
const ALGOLIA_SEARCH_KEY = "fe82c32af1869d8ca8f461181610f4c5";
const ALGOLIA_INDEX     = "sermons";

// ══════════════════════════════════════════════════════════════════════════
//  PASTORS
// ══════════════════════════════════════════════════════════════════════════

export async function getPastors() {
  const snap = await getDocs(collection(db, "pastors"));
  return snap.docs.map(d => ({ id: d.id, ...d.data() }));
}

export async function getPastor(id) {
  const snap = await getDoc(doc(db, "pastors", id));
  return snap.exists() ? { id: snap.id, ...snap.data() } : null;
}

// ══════════════════════════════════════════════════════════════════════════
//  SERMONS — SINGLE
// ══════════════════════════════════════════════════════════════════════════

export async function getSermon(id) {
  const snap = await getDoc(doc(db, "sermons", id));
  return snap.exists() ? { id: snap.id, ...snap.data() } : null;
}

// ══════════════════════════════════════════════════════════════════════════
//  SERMONS — LIST WITH FILTERS
// ══════════════════════════════════════════════════════════════════════════

/**
 * Fetch sermons with optional filters. All filters are optional.
 * When a keyword or book filter is applied, results are sorted client-side
 * since Firestore requires composite indexes for array-contains + orderBy.
 */
export async function getSermons({
  pastorId   = null,
  keyword    = null,    // filter by keyword tag
  book       = null,    // filter by Bible book
  isPrimary  = null,    // true = primary pastor only, false = guests only
  decade     = null,    // e.g. "1980s"
  seriesId   = null,    // filter by series
  pageSize   = 24,
  lastDoc    = null,
} = {}) {
  const constraints = [];

  if (pastorId)           constraints.push(where("pastor_id",         "==",             pastorId));
  if (keyword)            constraints.push(where("keywords",          "array-contains", keyword));
  if (book)               constraints.push(where("bible_books",       "array-contains", book));
  if (isPrimary !== null) constraints.push(where("is_primary_pastor", "==",             isPrimary));
  if (decade)             constraints.push(where("decade",            "==",             decade));
  if (seriesId)           constraints.push(where("series_id",         "==",             seriesId));

  // Only use orderBy when safe (no array-contains filters — requires composite index)
  const needsClientSort = keyword || book;
  if (!needsClientSort) constraints.push(orderBy("title"));

  constraints.push(limit(pageSize));
  if (lastDoc) constraints.push(startAfter(lastDoc));

  try {
    const snap    = await getDocs(query(collection(db, "sermons"), ...constraints));
    const sermons = snap.docs.map(d => ({ id: d.id, ...d.data() }));
    if (needsClientSort) sermons.sort((a, b) => (a.title || "").localeCompare(b.title || ""));
    return {
      sermons,
      lastDoc:  snap.docs[snap.docs.length - 1] || null,
      hasMore:  snap.docs.length === pageSize,
    };
  } catch (err) {
    // Index missing — retry without orderBy
    if (err.code === "failed-precondition" || err.message?.includes("index")) {
      console.warn("Firestore index missing, falling back:", err.message);
      const fallback = constraints.filter(c => !c.toString().includes("orderBy"));
      const snap     = await getDocs(query(collection(db, "sermons"), ...fallback));
      const sermons  = snap.docs.map(d => ({ id: d.id, ...d.data() }));
      sermons.sort((a, b) => (a.title || "").localeCompare(b.title || ""));
      return { sermons, lastDoc: snap.docs[snap.docs.length - 1] || null, hasMore: snap.docs.length === pageSize };
    }
    throw err;
  }
}

// ══════════════════════════════════════════════════════════════════════════
//  SEARCH — ALGOLIA FULL TEXT
// ══════════════════════════════════════════════════════════════════════════

/**
 * Full-text search via Algolia.
 * Returns an array of sermon objects with all fields.
 * Falls back to Firestore prefix search if Algolia fails.
 */
export async function searchSermons(queryText, pastorId = null, maxResults = 20) {
  if (!queryText || queryText.trim().length < 2) return [];

  try {
    const url    = `https://${ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/${ALGOLIA_INDEX}/query`;
    const body   = {
      query:               queryText,
      hitsPerPage:         maxResults,
      attributesToRetrieve: ["objectID", "title", "author", "summary", "main_theme",
                             "keywords", "bible_books", "date", "decade", "folder",
                             "is_primary_pastor", "web_url", "word_count", "estimated_length"],
      ...(pastorId ? { filters: `pastor_id:${pastorId}` } : {}),
    };
    const resp   = await fetch(url, {
      method:  "POST",
      headers: {
        "X-Algolia-Application-Id": ALGOLIA_APP_ID,
        "X-Algolia-API-Key":        ALGOLIA_SEARCH_KEY,
        "Content-Type":             "application/json",
      },
      body: JSON.stringify(body),
    });
    if (!resp.ok) throw new Error(`Algolia error ${resp.status}`);
    const data = await resp.json();
    return data.hits.map(hit => ({
      id:    hit.objectID,
      ...hit,
    }));
  } catch (err) {
    console.warn("Algolia search failed, falling back to Firestore:", err.message);
    return searchSermonsByTitle(queryText, pastorId);
  }
}

/**
 * Firestore prefix search on title_lower — fallback when Algolia unavailable.
 */
export async function searchSermonsByTitle(titleQuery, pastorId = null) {
  const q   = titleQuery.toLowerCase().trim();
  if (!q) return [];
  const end = q.slice(0, -1) + String.fromCharCode(q.charCodeAt(q.length - 1) + 1);

  try {
    const constraints = [
      where("title_lower", ">=", q),
      where("title_lower", "<",  end),
      orderBy("title_lower"),
      limit(20),
    ];
    if (pastorId) constraints.unshift(where("pastor_id", "==", pastorId));
    const snap = await getDocs(query(collection(db, "sermons"), ...constraints));
    return snap.docs.map(d => ({ id: d.id, ...d.data() }));
  } catch (err) {
    // Try without pastor_id filter if index missing
    if (err.message?.includes("index") || err.code === "failed-precondition") {
      try {
        const snap = await getDocs(query(collection(db, "sermons"),
          where("title_lower", ">=", q),
          where("title_lower", "<", end),
          orderBy("title_lower"),
          limit(20),
        ));
        const results = snap.docs.map(d => ({ id: d.id, ...d.data() }));
        return pastorId ? results.filter(s => s.pastor_id === pastorId) : results;
      } catch (_) { return []; }
    }
    return [];
  }
}

// ══════════════════════════════════════════════════════════════════════════
//  SCRIPTURE REFERENCES
// ══════════════════════════════════════════════════════════════════════════

/**
 * Get all scripture references for a single sermon.
 * References are stored in their own collection for unlimited storage.
 */
export async function getScriptureRefs(sermonId) {
  if (!sermonId) return [];
  try {
    const snap = await getDocs(
      query(
        collection(db, "scripture_references"),
        where("sermon_id", "==", sermonId),
      )
    );
    return snap.docs.map(d => ({ id: d.id, ...d.data() }));
  } catch (err) {
    console.warn("Failed to fetch scripture refs:", err.message);
    return [];
  }
}

/**
 * Get all sermons that reference a specific verse (cross-reference feature).
 * Uses OSIS reference format e.g. "John.3.16"
 */
export async function getSermonsByVerse(osisRef, pastorId = null) {
  if (!osisRef) return [];
  try {
    const constraints = [where("osis_ref", "==", osisRef)];
    if (pastorId) constraints.push(where("pastor_id", "==", pastorId));
    const snap = await getDocs(query(collection(db, "scripture_references"), ...constraints));
    const sermonIds = [...new Set(snap.docs.map(d => d.data().sermon_id).filter(Boolean))];
    // Fetch each sermon
    const sermons = await Promise.all(sermonIds.map(id => getSermon(id)));
    return sermons.filter(Boolean);
  } catch (err) {
    console.warn("Failed to fetch sermons by verse:", err.message);
    return [];
  }
}

/**
 * Get all sermons referencing a Bible book.
 */
export async function getSermonsByBook(book, pastorId = null) {
  if (!book) return [];
  try {
    const constraints = [where("book", "==", book)];
    if (pastorId) constraints.push(where("pastor_id", "==", pastorId));
    const snap      = await getDocs(query(collection(db, "scripture_references"), ...constraints));
    const sermonIds = [...new Set(snap.docs.map(d => d.data().sermon_id).filter(Boolean))];
    const sermons   = await Promise.all(sermonIds.slice(0, 50).map(id => getSermon(id)));
    return sermons.filter(Boolean).sort((a, b) => (a.title || "").localeCompare(b.title || ""));
  } catch (err) {
    console.warn("Failed to fetch sermons by book:", err.message);
    return [];
  }
}

// ══════════════════════════════════════════════════════════════════════════
//  KJV BIBLE
// ══════════════════════════════════════════════════════════════════════════

/**
 * Get a single KJV verse by OSIS reference (e.g. "John.3.16").
 */
export async function getKJVVerse(osisRef) {
  if (!osisRef) return null;
  try {
    const snap = await getDoc(doc(db, "kjv", osisRef));
    return snap.exists() ? snap.data() : null;
  } catch (err) {
    console.warn("KJV verse fetch failed:", err.message);
    return null;
  }
}

/**
 * Get all verses in a KJV chapter.
 * Returns array sorted by verse number.
 * osisBook: e.g. "John", chapter: e.g. 3
 */
// Map OSIS abbreviations back to full book names as stored in Firestore
const OSIS_TO_BOOK = {
  "Gen":"Genesis","Exod":"Exodus","Lev":"Leviticus","Num":"Numbers",
  "Deut":"Deuteronomy","Josh":"Joshua","Judg":"Judges","Ruth":"Ruth",
  "1Sam":"1 Samuel","2Sam":"2 Samuel","1Kgs":"1 Kings","2Kgs":"2 Kings",
  "1Chr":"1 Chronicles","2Chr":"2 Chronicles","Ezra":"Ezra","Neh":"Nehemiah",
  "Esth":"Esther","Job":"Job","Ps":"Psalms","Prov":"Proverbs",
  "Eccl":"Ecclesiastes","Song":"Song of Solomon","Isa":"Isaiah",
  "Jer":"Jeremiah","Lam":"Lamentations","Ezek":"Ezekiel","Dan":"Daniel",
  "Hos":"Hosea","Joel":"Joel","Amos":"Amos","Obad":"Obadiah","Jonah":"Jonah",
  "Mic":"Micah","Nah":"Nahum","Hab":"Habakkuk","Zeph":"Zephaniah",
  "Hag":"Haggai","Zech":"Zechariah","Mal":"Malachi",
  "Matt":"Matthew","Mark":"Mark","Luke":"Luke","John":"John","Acts":"Acts",
  "Rom":"Romans","1Cor":"1 Corinthians","2Cor":"2 Corinthians",
  "Gal":"Galatians","Eph":"Ephesians","Phil":"Philippians",
  "Col":"Colossians","1Thess":"1 Thessalonians","2Thess":"2 Thessalonians",
  "1Tim":"1 Timothy","2Tim":"2 Timothy","Titus":"Titus","Phlm":"Philemon",
  "Heb":"Hebrews","Jas":"James","1Pet":"1 Peter","2Pet":"2 Peter",
  "1John":"1 John","2John":"2 John","3John":"3 John","Jude":"Jude",
  "Rev":"Revelation",
};

export function osisToFullName(osisBook) {
  return OSIS_TO_BOOK[osisBook] || osisBook;
}

export async function getKJVChapter(osisBook, chapter) {
  if (!osisBook || !chapter) return [];
  // Convert OSIS abbreviation to full book name as stored in Firestore
  const fullName = osisToFullName(osisBook);
  try {
    const snap = await getDocs(
      query(
        collection(db, "kjv"),
        where("book",    "==", fullName),
        where("chapter", "==", Number(chapter)),
      )
    );
    const verses = snap.docs.map(d => d.data());
    return verses.sort((a, b) => a.verse - b.verse);
  } catch (err) {
    console.warn("KJV chapter fetch failed:", err.message);
    return [];
  }
}

/**
 * Parse an OSIS ref string into its components.
 * "John.3.16" → { book: "John", chapter: 3, verse: 16 }
 */
export function parseOsisRef(osisRef) {
  if (!osisRef) return null;
  const parts = osisRef.split(".");
  if (parts.length < 3) return null;
  return {
    book:    parts[0],
    chapter: parseInt(parts[1], 10),
    verse:   parseInt(parts[2], 10),
  };
}

// ══════════════════════════════════════════════════════════════════════════
//  SERIES
// ══════════════════════════════════════════════════════════════════════════

export async function getSeries(pastorId) {
  if (!pastorId) return [];
  try {
    const snap = await getDocs(
      query(
        collection(db, "series"),
        where("pastor_id", "==", pastorId),
        orderBy("name"),
      )
    );
    return snap.docs.map(d => ({ id: d.id, ...d.data() }));
  } catch (err) {
    console.warn("Failed to fetch series:", err.message);
    return [];
  }
}

export async function getOneSeries(seriesId) {
  if (!seriesId) return null;
  const snap = await getDoc(doc(db, "series", seriesId));
  return snap.exists() ? { id: snap.id, ...snap.data() } : null;
}

// ══════════════════════════════════════════════════════════════════════════
//  STATS
// ══════════════════════════════════════════════════════════════════════════

export async function getStats(pastorId = null) {
  const id   = pastorId || "global";
  const snap = await getDoc(doc(db, "stats", id));
  return snap.exists() ? snap.data() : null;
}

// ══════════════════════════════════════════════════════════════════════════
//  ANNOTATIONS (structure ready, UI in future version)
// ══════════════════════════════════════════════════════════════════════════

export async function getAnnotations(sermonId) {
  if (!sermonId) return [];
  try {
    const snap = await getDocs(
      query(
        collection(db, "annotations"),
        where("sermon_id", "==", sermonId),
        orderBy("created_at"),
      )
    );
    return snap.docs.map(d => ({ id: d.id, ...d.data() }));
  } catch (err) {
    return [];
  }
}
