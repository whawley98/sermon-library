// src/components/KJVPanel.js
// Full Bible study panel — slides in from right when a scripture ref is clicked.
// Shows the full chapter with the referenced verse highlighted.
// Includes search, book/chapter navigation, and independent scrolling.

import React, { useState, useEffect, useRef, useCallback } from "react";
import { getKJVChapter, getKJVVerse, parseOsisRef, osisToFullName } from "../lib/firebase";
import "./KJVPanel.css";

// Ordered list of Bible books for navigation
const BIBLE_BOOKS = [
  "Genesis","Exodus","Leviticus","Numbers","Deuteronomy","Joshua","Judges","Ruth",
  "1 Samuel","2 Samuel","1 Kings","2 Kings","1 Chronicles","2 Chronicles","Ezra",
  "Nehemiah","Esther","Job","Psalms","Proverbs","Ecclesiastes","Song of Solomon",
  "Isaiah","Jeremiah","Lamentations","Ezekiel","Daniel","Hosea","Joel","Amos",
  "Obadiah","Jonah","Micah","Nahum","Habakkuk","Zephaniah","Haggai","Zechariah",
  "Malachi","Matthew","Mark","Luke","John","Acts","Romans","1 Corinthians",
  "2 Corinthians","Galatians","Ephesians","Philippians","Colossians",
  "1 Thessalonians","2 Thessalonians","1 Timothy","2 Timothy","Titus","Philemon",
  "Hebrews","James","1 Peter","2 Peter","1 John","2 John","3 John","Jude","Revelation",
];

// OSIS book name map for fetching from Firestore
const BOOK_TO_OSIS = {
  "Genesis":"Gen","Exodus":"Exod","Leviticus":"Lev","Numbers":"Num",
  "Deuteronomy":"Deut","Joshua":"Josh","Judges":"Judg","Ruth":"Ruth",
  "1 Samuel":"1Sam","2 Samuel":"2Sam","1 Kings":"1Kgs","2 Kings":"2Kgs",
  "1 Chronicles":"1Chr","2 Chronicles":"2Chr","Ezra":"Ezra","Nehemiah":"Neh",
  "Esther":"Esth","Job":"Job","Psalms":"Ps","Proverbs":"Prov",
  "Ecclesiastes":"Eccl","Song of Solomon":"Song","Isaiah":"Isa",
  "Jeremiah":"Jer","Lamentations":"Lam","Ezekiel":"Ezek","Daniel":"Dan",
  "Hosea":"Hos","Joel":"Joel","Amos":"Amos","Obadiah":"Obad","Jonah":"Jonah",
  "Micah":"Mic","Nahum":"Nah","Habakkuk":"Hab","Zephaniah":"Zeph",
  "Haggai":"Hag","Zechariah":"Zech","Malachi":"Mal",
  "Matthew":"Matt","Mark":"Mark","Luke":"Luke","John":"John","Acts":"Acts",
  "Romans":"Rom","1 Corinthians":"1Cor","2 Corinthians":"2Cor",
  "Galatians":"Gal","Ephesians":"Eph","Philippians":"Phil",
  "Colossians":"Col","1 Thessalonians":"1Thess","2 Thessalonians":"2Thess",
  "1 Timothy":"1Tim","2 Timothy":"2Tim","Titus":"Titus","Philemon":"Phlm",
  "Hebrews":"Heb","James":"Jas","1 Peter":"1Pet","2 Peter":"2Pet",
  "1 John":"1John","2 John":"2John","3 John":"3John","Jude":"Jude",
  "Revelation":"Rev",
};

// Parse a human-readable reference like "John 3:16" into components
function parseHumanRef(ref) {
  if (!ref) return null;
  const m = ref.match(/^([1-3]?\s?[A-Za-z\s]+?)\s+(\d+):(\d+)/);
  if (!m) return null;
  return {
    book:    m[1].trim(),
    chapter: parseInt(m[2], 10),
    verse:   parseInt(m[3], 10),
  };
}

function getOsisBook(bookName) {
  return BOOK_TO_OSIS[bookName] || bookName.replace(/\s+/g, "");
}

export default function KJVPanel({ osisRef, referenceLabel, onClose }) {
  const [verses,       setVerses]       = useState([]);
  const [loading,      setLoading]      = useState(false);
  const [currentBook,  setCurrentBook]  = useState("");
  const [currentChap,  setCurrentChap]  = useState(1);
  const [targetVerse,  setTargetVerse]  = useState(null);
  const [searchText,   setSearchText]   = useState("");
  const [chapterCount, setChapterCount] = useState(150); // safe default
  const verseRef       = useRef(null);
  const panelBodyRef   = useRef(null);

  // ── Load chapter ─────────────────────────────────────────────────────────
  const loadChapter = useCallback(async (osisBook, chapter, highlightVerse = null) => {
    setLoading(true);
    try {
      const data = await getKJVChapter(osisBook, chapter);
      setVerses(data);
      if (highlightVerse) setTargetVerse(highlightVerse);
    } catch (err) {
      console.error("KJV load failed:", err);
      setVerses([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // ── Initialize from osisRef ──────────────────────────────────────────────
  useEffect(() => {
    if (!osisRef) return;
    const parsed = parseOsisRef(osisRef);
    if (!parsed) return;
    // Convert OSIS abbreviation to full book name for Firestore queries
    const fullName = osisToFullName(parsed.book);
    setCurrentBook(fullName);
    setCurrentChap(parsed.chapter);
    setTargetVerse(parsed.verse);
    loadChapter(fullName, parsed.chapter, parsed.verse);
  }, [osisRef, loadChapter]);

  // ── Scroll to highlighted verse ──────────────────────────────────────────
  useEffect(() => {
    if (targetVerse && verseRef.current) {
      setTimeout(() => {
        verseRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
      }, 100);
    }
  }, [verses, targetVerse]);

  // ── Navigation ───────────────────────────────────────────────────────────
  const goToBook = (book) => {
    // book is already the full name from the BIBLE_BOOKS dropdown
    setCurrentBook(book);
    setCurrentChap(1);
    setTargetVerse(null);
    loadChapter(book, 1, null);
  };

  const goToChapter = (chapter) => {
    setCurrentChap(chapter);
    setTargetVerse(null);
    loadChapter(currentBook, chapter, null);
  };

  const prevChapter = () => { if (currentChap > 1) goToChapter(currentChap - 1); };
  const nextChapter = () => goToChapter(currentChap + 1);

  // ── Search / jump to reference ───────────────────────────────────────────
  const handleSearch = (e) => {
    e.preventDefault();
    const parsed = parseHumanRef(searchText);
    if (!parsed) return;
    const osisBook = getOsisBook(parsed.book);
    setCurrentBook(osisBook);
    setCurrentChap(parsed.chapter);
    setTargetVerse(parsed.verse);
    loadChapter(osisBook, parsed.chapter, parsed.verse);
    setSearchText("");
  };

  // ── Current display name ─────────────────────────────────────────────────
  const bookDisplayName = currentBook;

  return (
    <div className="kjv-panel">
      {/* Header */}
      <div className="kjv-header">
        <div className="kjv-header-top">
          <div className="kjv-title-area">
            <span className="kjv-logo">✦</span>
            <div>
              <div className="kjv-title">King James Bible</div>
              {referenceLabel && (
                <div className="kjv-subtitle">{referenceLabel}</div>
              )}
            </div>
          </div>
          <button className="kjv-close" onClick={onClose} aria-label="Close Bible panel">✕</button>
        </div>

        {/* Search bar */}
        <form className="kjv-search-form" onSubmit={handleSearch}>
          <input
            className="kjv-search-input"
            type="text"
            placeholder="Jump to reference… e.g. John 3:16"
            value={searchText}
            onChange={e => setSearchText(e.target.value)}
            aria-label="Jump to Bible reference"
          />
          <button type="submit" className="kjv-search-btn">→</button>
        </form>

        {/* Book selector */}
        <div className="kjv-nav">
          <select
            className="kjv-book-select"
            value={bookDisplayName}
            onChange={e => goToBook(e.target.value)}
            aria-label="Select Bible book"
          >
            {BIBLE_BOOKS.map(b => (
              <option key={b} value={b}>{b}</option>
            ))}
          </select>

          <div className="kjv-chapter-nav">
            <button className="kjv-nav-btn" onClick={prevChapter} disabled={currentChap <= 1} aria-label="Previous chapter">‹</button>
            <span className="kjv-chapter-label">Ch. {currentChap}</span>
            <button className="kjv-nav-btn" onClick={nextChapter} aria-label="Next chapter">›</button>
          </div>
        </div>
      </div>

      {/* Body */}
      <div className="kjv-body" ref={panelBodyRef}>
        {loading ? (
          <div className="kjv-loading">
            <div className="spinner" />
            <span>Loading…</span>
          </div>
        ) : verses.length === 0 ? (
          <div className="kjv-empty">
            <p>No text found. Try searching for a reference above.</p>
          </div>
        ) : (
          <div className="kjv-chapter">
            <h2 className="kjv-chapter-heading">
              {bookDisplayName} {currentChap}
            </h2>
            {verses.map(v => (
              <div
                key={v.verse}
                ref={v.verse === targetVerse ? verseRef : null}
                className={`kjv-verse${v.verse === targetVerse ? " kjv-verse--highlighted" : ""}`}
              >
                <span className="kjv-verse-num">{v.verse}</span>
                <span className="kjv-verse-text">{v.text}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
