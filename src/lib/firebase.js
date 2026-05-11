// src/lib/firebase.js
// ─────────────────────────────────────────────────────────────
// Firebase initialization for Sermon Library
// Config is safe to be public (Firestore rules control access)
// ─────────────────────────────────────────────────────────────

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
  collectionGroup,
} from "firebase/firestore";

const firebaseConfig = {
  apiKey: "AIzaSyBlrNposSO9q-fRORmmG6a_0bLy3TkXqgc",
  authDomain: "sermon-library-89f46.firebaseapp.com",
  projectId: "sermon-library-89f46",
  storageBucket: "sermon-library-89f46.firebasestorage.app",
  messagingSenderId: "375159141051",
  appId: "1:375159141051:web:337cc6aee9c01c8f12af9e",
};

const app = initializeApp(firebaseConfig);
export const db = getFirestore(app);

// ── Collection references ──────────────────────────────────────
export const pastorsRef    = () => collection(db, "pastors");
export const sermonsRef    = () => collection(db, "sermons");
export const pastorRef     = (id) => doc(db, "pastors", id);
export const sermonRef     = (id) => doc(db, "sermons", id);

// ── Queries ────────────────────────────────────────────────────

export async function getPastors() {
  const snap = await getDocs(pastorsRef());
  return snap.docs.map((d) => ({ id: d.id, ...d.data() }));
}

export async function getPastor(id) {
  const snap = await getDoc(pastorRef(id));
  return snap.exists() ? { id: snap.id, ...snap.data() } : null;
}

export async function getSermon(id) {
  const snap = await getDoc(sermonRef(id));
  return snap.exists() ? { id: snap.id, ...snap.data() } : null;
}

export async function getSermons({
  pastorId   = null,
  keyword    = null,
  book       = null,
  authorName = null,
  seriesName = null,
  pageSize   = 24,
  lastDoc    = null,
} = {}) {
  const constraints = [];
  if (pastorId)   constraints.push(where("pastor_id",    "==", pastorId));
  if (keyword)    constraints.push(where("keywords",     "array-contains", keyword));
  if (book)       constraints.push(where("bible_books",  "array-contains", book));
  if (authorName) constraints.push(where("author",       "==", authorName));
  if (seriesName) constraints.push(where("series_name",  "==", seriesName));

  constraints.push(orderBy("title"));
  constraints.push(limit(pageSize));
  if (lastDoc) constraints.push(startAfter(lastDoc));

  const q = query(sermonsRef(), ...constraints);
  const snap = await getDocs(q);
  return {
    sermons: snap.docs.map((d) => ({ id: d.id, ...d.data() })),
    lastDoc: snap.docs[snap.docs.length - 1] || null,
    hasMore: snap.docs.length === pageSize,
  };
}

export async function searchSermonsByTitle(titleQuery, pastorId = null) {
  // Firestore prefix search using >= and <= trick
  const end = titleQuery.slice(0, -1) +
    String.fromCharCode(titleQuery.charCodeAt(titleQuery.length - 1) + 1);
  const constraints = [
    where("title_lower", ">=", titleQuery.toLowerCase()),
    where("title_lower", "<",  end.toLowerCase()),
    orderBy("title_lower"),
    limit(20),
  ];
  if (pastorId) constraints.unshift(where("pastor_id", "==", pastorId));
  const q = query(sermonsRef(), ...constraints);
  const snap = await getDocs(q);
  return snap.docs.map((d) => ({ id: d.id, ...d.data() }));
}

export async function getStats(pastorId = null) {
  // Returns aggregated stats — pulled from a pre-computed stats doc
  const id = pastorId || "global";
  const snap = await getDoc(doc(db, "stats", id));
  return snap.exists() ? snap.data() : null;
}

export { query, where, orderBy, limit, startAfter, getDocs, collection };
