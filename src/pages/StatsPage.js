// src/pages/StatsPage.js
// Ministry insights page showing stats, top Bible books, top verses,
// decade timeline, top keywords, and AI-generated ministry summary.

import React, { useState, useEffect } from "react";
import { getStats, getPastor } from "../lib/firebase";
import { generateMinistrySummary } from "../lib/ai";
import "./StatsPage.css";

export default function StatsPage({ pastor }) {
  const [stats,    setStats]    = useState(null);
  const [loading,  setLoading]  = useState(true);
  const [summary,  setSummary]  = useState("");
  const [sumLoading, setSumLoading] = useState(false);
  const [sumError,   setSumError]   = useState("");

  useEffect(() => {
    if (!pastor?.id) return;
    setLoading(true);
    getStats(pastor.id)
      .then(setStats)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [pastor?.id]);

  const handleGenerateSummary = async () => {
    if (!pastor || !stats) return;
    setSumLoading(true);
    setSumError("");
    setSummary("");
    try {
      const text = await generateMinistrySummary(pastor, stats);
      setSummary(text);
    } catch (err) {
      setSumError(err.message || "Failed to generate summary.");
    } finally {
      setSumLoading(false);
    }
  };

  if (loading) return (
    <div className="stats-loading">
      <div className="spinner" />
      <p>Loading insights…</p>
    </div>
  );

  if (!stats) return (
    <div className="stats-empty">
      <p>No stats available yet. Run the ingestion pipeline first.</p>
    </div>
  );

  const topBooks    = stats.top_bible_books  || [];
  const topKeywords = stats.top_keywords     || [];
  const topVerses   = stats.top_verses       || [];
  const decades     = stats.sermons_by_decade || {};
  const maxBooks    = topBooks[0]?.count  || 1;
  const maxKw       = topKeywords[0]?.count || 1;
  const maxDecade   = Math.max(...Object.values(decades), 1);

  const decadesSorted = Object.entries(decades)
    .sort(([a], [b]) => a.localeCompare(b));

  return (
    <div className="stats-page">
      <div className="stats-inner">

        {/* ── Hero ───────────────────────────────────────────────────── */}
        <header className="stats-hero">
          <div className="stats-hero-label">Ministry Archive</div>
          <h1 className="stats-hero-name">{pastor?.name}</h1>
          {pastor?.description && (
            <p className="stats-hero-desc">{pastor.description}</p>
          )}
          <div className="stats-hero-numbers">
            <div className="hero-stat">
              <span className="hero-num">{stats.total_sermons?.toLocaleString()}</span>
              <span className="hero-label">Sermons</span>
            </div>
            <div className="hero-stat-divider" />
            <div className="hero-stat">
              <span className="hero-num">{stats.total_references?.toLocaleString()}</span>
              <span className="hero-label">Scripture References</span>
            </div>
            <div className="hero-stat-divider" />
            <div className="hero-stat">
              <span className="hero-num">{Object.keys(decades).length}</span>
              <span className="hero-label">Decades</span>
            </div>
            <div className="hero-stat-divider" />
            <div className="hero-stat">
              <span className="hero-num">{topBooks.length}</span>
              <span className="hero-label">Bible Books</span>
            </div>
          </div>
        </header>

        {/* ── Decade timeline ────────────────────────────────────────── */}
        {decadesSorted.length > 0 && (
          <section className="stats-section">
            <h2 className="stats-section-title">Sermons by Decade</h2>
            <div className="decade-chart">
              {decadesSorted.map(([decade, count]) => (
                <div key={decade} className="decade-bar-wrap">
                  <div className="decade-bar-outer">
                    <div
                      className="decade-bar-inner"
                      style={{ height: `${(count / maxDecade) * 100}%` }}
                    />
                  </div>
                  <div className="decade-count">{count}</div>
                  <div className="decade-label">{decade}</div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* ── Bible books ────────────────────────────────────────────── */}
        {topBooks.length > 0 && (
          <section className="stats-section">
            <h2 className="stats-section-title">
              Bible Books Preached
              <span className="stats-section-count">{topBooks.length} books</span>
            </h2>
            <div className="books-grid">
              {topBooks.map(({ book, count }) => (
                <div key={book} className="book-bar-row">
                  <span className="book-bar-name">{book}</span>
                  <div className="book-bar-track">
                    <div
                      className="book-bar-fill"
                      style={{ width: `${(count / maxBooks) * 100}%` }}
                    />
                  </div>
                  <span className="book-bar-count">{count}</span>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* ── Top verses ─────────────────────────────────────────────── */}
        {topVerses.length > 0 && (
          <section className="stats-section">
            <h2 className="stats-section-title">Most Referenced Verses</h2>
            <div className="verses-list">
              {topVerses.map(({ reference, count }, i) => (
                <div key={reference} className="verse-row">
                  <span className="verse-rank">{i + 1}</span>
                  <span className="verse-ref">{reference}</span>
                  <span className="verse-count">{count}×</span>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* ── Keywords ───────────────────────────────────────────────── */}
        {topKeywords.length > 0 && (
          <section className="stats-section">
            <h2 className="stats-section-title">Top Themes & Keywords</h2>
            <div className="kw-grid">
              {topKeywords.map(({ word, count }) => {
                const scale = 0.8 + (count / maxKw) * 0.7;
                return (
                  <span
                    key={word}
                    className="kw-cloud-word"
                    style={{ fontSize: `${scale}rem` }}
                    title={`${count} sermons`}
                  >
                    {word}
                  </span>
                );
              })}
            </div>
          </section>
        )}

        {/* ── AI Ministry Summary ─────────────────────────────────────── */}
        <section className="stats-section stats-summary-section">
          <h2 className="stats-section-title">Ministry Summary</h2>
          <p className="stats-summary-intro">
            Generate an AI-written tribute to {pastor?.name?.split(" ")[0]}'s ministry
            based on the complete sermon collection.
          </p>

          {!summary && (
            <button
              className="btn btn-gold stats-summary-btn"
              onClick={handleGenerateSummary}
              disabled={sumLoading}
            >
              {sumLoading
                ? <><span className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} /> Generating…</>
                : "✦ Generate Ministry Tribute"}
            </button>
          )}

          {sumError && (
            <div className="stats-error">{sumError}</div>
          )}

          {summary && (
            <div className="stats-summary-text">
              <div
                className="markdown"
                dangerouslySetInnerHTML={{ __html: markdownToHtml(summary) }}
              />
              <button
                className="btn btn-ghost stats-regen-btn"
                onClick={handleGenerateSummary}
                disabled={sumLoading}
              >
                ↻ Regenerate
              </button>
            </div>
          )}
        </section>

      </div>
    </div>
  );
}

function markdownToHtml(text) {
  return text
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/\n\n/g, "</p><p>")
    .replace(/^(?!<)(.+)$/gm, (m) => m.startsWith("<") ? m : `<p>${m}</p>`);
}
