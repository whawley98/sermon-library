// src/lib/firebase.js
import { initializeApp } from "firebase/app";
import {
  getFirestore, collection, doc,
  getDoc, getDocs, query,
  where, orderBy, limit, startAfter,
} from "firebase/firestore";

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

export async function getPastors() {
  const snap = await getDocs(collection(db, "pastors"));
  return snap.docs.map(d => ({ id: d.id, ...d.data() }));
}

export async function getSermon(id) {
  const snap = await getDoc(doc(db, "sermons", id));
  return snap.exists() ? { id: snap.id, ...snap.data() } : null;
}

export async function getStats(pastorId = null) {
  const snap = await getDoc(doc(db, "stats", pastorId || "global"));
  return snap.exists() ? snap.data() : null;
}

// ── Build a query safely, falling back if index missing ───────────────────
async function runQuery(constraints) {
  try {
    const snap = await getDocs(query(collection(db, "sermons"), ...constraints));
    return snap.docs.map(d => ({ id: d.id, ...d.data() }));
  } catch (err) {
    if (err.code === "failed-precondition" || (err.message && err.message.includes("index"))) {
      console.warn("Index missing, retrying without orderBy:", err.message);
      // Remove any orderBy constraints and retry
      const fallback = constraints.filter(c => {
        const str = c.toString();
        return !str.includes("orderBy");
      });
      // Simpler: just rebuild without orderBy
      return null; // signal to caller to use fallback
    }
    throw err;
  }
}

export async function getSermons({
  pastorId     = null,
  keyword      = null,
  book         = null,
  isPrimary    = null,   // true = William Hawley only, false = others only
  pageSize     = 24,
  lastDoc      = null,
} = {}) {
  const base = [];
  if (pastorId)            base.push(where("pastor_id",       "==",             pastorId));
  if (keyword)             base.push(where("keywords",        "array-contains", keyword));
  if (book)                base.push(where("bible_books",     "array-contains", book));
  if (isPrimary !== null)  base.push(where("is_primary_pastor", "==",           isPrimary));

  // Only add orderBy when it won't require a missing composite index
  // Safe: single equality filter + orderBy on same or different field
  const canOrderBy = !keyword && !book && isPrimary === null;
  if (canOrderBy) base.push(orderBy("title"));

  base.push(limit(pageSize));
  if (lastDoc) base.push(startAfter(lastDoc));

  try {
    const snap    = await getDocs(query(collection(db, "sermons"), ...base));
    const sermons = snap.docs.map(d => ({ id: d.id, ...d.data() }));
    // Client-side sort when we couldn't use orderBy
    if (!canOrderBy) sermons.sort((a, b) => (a.title || "").localeCompare(b.title || ""));
    return {
      sermons,
      lastDoc: snap.docs[snap.docs.length - 1] || null,
      hasMore: snap.docs.length === pageSize,
    };
  } catch (err) {
    if (err.code === "failed-precondition" || (err.message && err.message.includes("index"))) {
      console.warn("Index missing, falling back to unordered query");
      const fallbackBase = [];
      if (pastorId)           fallbackBase.push(where("pastor_id",         "==",             pastorId));
      if (keyword)            fallbackBase.push(where("keywords",          "array-contains", keyword));
      if (book)               fallbackBase.push(where("bible_books",       "array-contains", book));
      if (isPrimary !== null) fallbackBase.push(where("is_primary_pastor", "==",             isPrimary));
      fallbackBase.push(limit(pageSize));
      if (lastDoc) fallbackBase.push(startAfter(lastDoc));
      const snap    = await getDocs(query(collection(db, "sermons"), ...fallbackBase));
      const sermons = snap.docs.map(d => ({ id: d.id, ...d.data() }));
      sermons.sort((a, b) => (a.title || "").localeCompare(b.title || ""));
      return { sermons, lastDoc: snap.docs[snap.docs.length - 1] || null, hasMore: snap.docs.length === pageSize };
    }
    throw err;
  }
}

export async function searchSermonsByTitle(titleQuery, pastorId = null) {
  const q   = titleQuery.toLowerCase();
  const end = q.slice(0, -1) + String.fromCharCode(q.charCodeAt(q.length - 1) + 1);

  // Try with pastor_id filter first (needs composite index)
  if (pastorId) {
    try {
      const snap = await getDocs(query(collection(db, "sermons"),
        where("pastor_id",   "==", pastorId),
        where("title_lower", ">=", q),
        where("title_lower", "<",  end),
        orderBy("title_lower"),
        limit(20),
      ));
      return snap.docs.map(d => ({ id: d.id, ...d.data() }));
    } catch (err) {
      if (!err.message?.includes("index") && err.code !== "failed-precondition") throw err;
      console.warn("Title search index missing, falling back to simple search");
    }
  }

  // Fallback: search without pastor_id (single-field range query, no index needed)
  try {
    const snap = await getDocs(query(collection(db, "sermons"),
      where("title_lower", ">=", q),
      where("title_lower", "<",  end),
      orderBy("title_lower"),
      limit(20),
    ));
    const results = snap.docs.map(d => ({ id: d.id, ...d.data() }));
    // Client-side filter by pastor if needed
    return pastorId ? results.filter(s => s.pastor_id === pastorId) : results;
  } catch (err) {
    console.warn("Title search failed:", err.message);
    return [];
  }
}
