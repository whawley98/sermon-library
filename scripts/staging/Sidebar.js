// src/components/Sidebar.js
import React, { useState, useEffect } from "react";
import { getStats } from "../lib/firebase";
import "./Sidebar.css";

export default function Sidebar({ activePastor, onFilterChange, filters = {} }) {
  const [stats,        setStats]        = useState(null);
  const [showAllBooks, setShowAllBooks] = useState(false);

  useEffect(() => {
    if (!activePastor?.id) return;
    getStats(activePastor.id).then(setStats).catch(() => {});
  }, [activePastor?.id]);

  const allBooks     = stats?.top_bible_books || [];
  const topKeywords  = stats?.top_keywords?.slice(0, 30) || [];
  const visibleBooks = showAllBooks ? allBooks : allBooks.slice(0, 15);
  const max          = topKeywords[0]?.count || 1;

  return (
    <aside className="sidebar no-print">
      <div className="sidebar-inner">

        {/* Author */}
        <section className="sidebar-section">
          <h3 className="sidebar-label">Author</h3>
          <div className="pill-group">
            {[
              { v: null,     label: "All Authors" },
              { v: "hawley", label: activePastor?.name?.split(" ").pop() || "Primary" },
              { v: "other",  label: "Other Preachers" },
            ].map(({ v, label }) => (
              <button
                key={label}
                className={`pill ${(filters.author ?? null) === v ? "pill-active" : ""}`}
                onClick={() => onFilterChange?.({ author: v })}
              >
                {label}
              </button>
            ))}
          </div>
        </section>

        {/* Bible Books — all books, scrollable */}
        {allBooks.length > 0 && (
          <section className="sidebar-section">
            <h3 className="sidebar-label">Bible Book</h3>
            <div className={`book-list ${showAllBooks ? "book-list-expanded" : ""}`}>
              {visibleBooks.map(({ book, count }) => (
                <button
                  key={book}
                  className={`book-row ${filters.book === book ? "book-row-active" : ""}`}
                  onClick={() => onFilterChange?.({ book: filters.book === book ? null : book })}
                >
                  <span>{book}</span>
                  <span className="book-count">{count}</span>
                </button>
              ))}
            </div>
            {allBooks.length > 15 && (
              <button
                className="show-more-btn"
                onClick={() => setShowAllBooks(v => !v)}
              >
                {showAllBooks
                  ? "▲ Show less"
                  : `▼ Show all ${allBooks.length} books`}
              </button>
            )}
          </section>
        )}

        {/* Topics */}
        {topKeywords.length > 0 && (
          <section className="sidebar-section">
            <h3 className="sidebar-label">Topics</h3>
            <div className="keyword-cloud">
              {topKeywords.map(({ word, count }) => {
                const size     = 0.78 + (count / max) * 0.42;
                const isActive = filters.keyword === word;
                return (
                  <button
                    key={word}
                    className={`kw-btn ${isActive ? "kw-btn-active" : ""}`}
                    style={{ fontSize: `${size}rem` }}
                    onClick={() => onFilterChange?.({ keyword: filters.keyword === word ? null : word })}
                  >
                    {word}
                  </button>
                );
              })}
            </div>
          </section>
        )}

        {/* Clear filters */}
        {(filters.author || filters.book || filters.keyword) && (
          <section className="sidebar-section">
            <button
              className="clear-btn"
              onClick={() => onFilterChange?.({ author: null, book: null, keyword: null })}
            >
              ✕ Clear all filters
            </button>
          </section>
        )}

      </div>
    </aside>
  );
}
