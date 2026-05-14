// src/components/Sidebar.js
// Filterable sidebar: author pills, Bible books (all, scrollable), keyword cloud.

import React, { useState, useEffect } from "react";
import { getStats } from "../lib/firebase";
import "./Sidebar.css";

export default function Sidebar({ activePastor, filters = {}, onFilterChange }) {
  const [stats,        setStats]        = useState(null);
  const [showAllBooks, setShowAllBooks] = useState(false);

  useEffect(() => {
    if (!activePastor?.id) return;
    getStats(activePastor.id)
      .then(setStats)
      .catch(() => {});
  }, [activePastor?.id]);

  const allBooks    = stats?.top_bible_books || [];
  const keywords    = stats?.top_keywords    || [];
  const maxKw       = keywords[0]?.count || 1;
  const visibleBooks = showAllBooks ? allBooks : allBooks.slice(0, 15);

  const setFilter = (updates) => {
    if (onFilterChange) onFilterChange(updates);
  };

  const clearFilter = (key) => setFilter({ [key]: null });

  return (
    <aside className="sidebar no-print">
      <div className="sidebar-inner">

        {/* ── Author ──────────────────────────────────────────────────── */}
        <section className="sidebar-section">
          <h3 className="sidebar-label">Author</h3>
          <div className="author-pills">
            {[
              { value: null,     label: "All Authors" },
              { value: true,     label: activePastor?.name?.split(" ").slice(-1)[0] || "Primary" },
              { value: false,    label: "Guest Preachers" },
            ].map(({ value, label }) => (
              <button
                key={String(value)}
                className={`author-pill${(filters.isPrimary ?? null) === value ? " author-pill--active" : ""}`}
                onClick={() => setFilter({ isPrimary: value })}
              >
                {label}
              </button>
            ))}
          </div>
        </section>

        {/* ── Bible Books ──────────────────────────────────────────────── */}
        {allBooks.length > 0 && (
          <section className="sidebar-section">
            <h3 className="sidebar-label">
              Bible Book
              {filters.book && (
                <button className="clear-chip" onClick={() => clearFilter("book")}>
                  ✕ {filters.book}
                </button>
              )}
            </h3>
            <div className="book-list">
              {visibleBooks.map(({ book, count }) => (
                <button
                  key={book}
                  className={`book-row${filters.book === book ? " book-row--active" : ""}`}
                  onClick={() => setFilter({ book: filters.book === book ? null : book })}
                >
                  <span className="book-name">{book}</span>
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
                  ? `▲ Show fewer`
                  : `▼ Show all ${allBooks.length} books`}
              </button>
            )}
          </section>
        )}

        {/* ── Topics / Keywords ────────────────────────────────────────── */}
        {keywords.length > 0 && (
          <section className="sidebar-section">
            <h3 className="sidebar-label">
              Topics
              {filters.keyword && (
                <button className="clear-chip" onClick={() => clearFilter("keyword")}>
                  ✕ {filters.keyword}
                </button>
              )}
            </h3>
            <div className="keyword-cloud">
              {keywords.slice(0, 30).map(({ word, count }) => {
                const scale    = 0.78 + (count / maxKw) * 0.5;
                const isActive = filters.keyword === word;
                return (
                  <button
                    key={word}
                    className={`kw-tag${isActive ? " kw-tag--active" : ""}`}
                    style={{ fontSize: `${scale}rem` }}
                    onClick={() => setFilter({ keyword: isActive ? null : word })}
                  >
                    {word}
                  </button>
                );
              })}
            </div>
          </section>
        )}

        {/* ── Clear all ────────────────────────────────────────────────── */}
        {(filters.isPrimary !== null && filters.isPrimary !== undefined ||
          filters.book || filters.keyword) && (
          <section className="sidebar-section">
            <button
              className="clear-all-btn"
              onClick={() => setFilter({ isPrimary: null, book: null, keyword: null })}
            >
              ✕ Clear all filters
            </button>
          </section>
        )}

      </div>
    </aside>
  );
}
