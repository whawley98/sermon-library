// src/components/Sidebar.js
import React, { useState, useEffect } from "react";
import { getStats } from "../lib/firebase";
import "./Sidebar.css";

export default function Sidebar({ open, onClose, activePastor, onFilterChange, filters = {} }) {
  const [stats, setStats] = useState(null);

  useEffect(() => {
    if (!activePastor?.id) return;
    getStats(activePastor.id).then(setStats).catch(() => {});
  }, [activePastor?.id]);

  const topKeywords  = stats?.top_keywords?.slice(0, 25)  || [];
  const topBooks     = stats?.top_bible_books?.slice(0, 15) || [];
  const max = topKeywords[0]?.count || 1;

  return (
    <>
      {/* Overlay for mobile */}
      {open && <div className="sidebar-overlay" onClick={onClose} />}

      <aside className={`sidebar no-print ${open ? "sidebar-open" : ""}`}>
        <div className="sidebar-inner">

          {/* Author filter */}
          <section className="sidebar-section">
            <h3 className="sidebar-label">Author</h3>
            <div className="pill-group">
              {["all", "hawley", "other"].map((v) => (
                <button
                  key={v}
                  className={`pill ${(filters.author || "all") === v ? "pill-active" : ""}`}
                  onClick={() => onFilterChange?.({ author: v === "all" ? null : v })}
                >
                  {v === "all" ? "All Authors" : v === "hawley" ? `${activePastor?.name?.split(" ").pop() || "Primary"}` : "Other Preachers"}
                </button>
              ))}
            </div>
          </section>

          {/* Bible book filter */}
          {topBooks.length > 0 && (
            <section className="sidebar-section">
              <h3 className="sidebar-label">Bible Book</h3>
              <div className="book-list">
                {topBooks.map(({ book, count }) => (
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
            </section>
          )}

          {/* Keyword cloud */}
          {topKeywords.length > 0 && (
            <section className="sidebar-section">
              <h3 className="sidebar-label">Topics</h3>
              <div className="keyword-cloud">
                {topKeywords.map(({ word, count }) => {
                  const size  = 0.78 + (count / max) * 0.42;
                  const alpha = 0.4  + (count / max) * 0.5;
                  const isActive = filters.keyword === word;
                  return (
                    <button
                      key={word}
                      className={`kw-btn ${isActive ? "kw-btn-active" : ""}`}
                      style={{ fontSize: `${size}rem`, opacity: isActive ? 1 : alpha + 0.2 }}
                      onClick={() => onFilterChange?.({ keyword: filters.keyword === word ? null : word })}
                    >
                      {word}
                    </button>
                  );
                })}
              </div>
            </section>
          )}

          {/* Active filter summary */}
          {(filters.author || filters.book || filters.keyword) && (
            <section className="sidebar-section">
              <h3 className="sidebar-label">Active Filters</h3>
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
    </>
  );
}
