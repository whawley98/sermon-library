// src/components/SermonCard.js
// Displays a sermon in grid or list view.
// Handles missing summaries gracefully.

import React from "react";
import { useNavigate } from "react-router-dom";
import "./SermonCard.css";

export default function SermonCard({ sermon, view = "grid" }) {
  const navigate = useNavigate();

  const topRefs = (sermon.bible_books || []).slice(0, 3);
  const topKw   = (sermon.keywords    || []).slice(0, 3);
  const hasSummary = sermon.summary && sermon.summary.length > 10;

  const handleClick = () => navigate(`/sermon/${sermon.id}`);

  if (view === "list") {
    return (
      <div className="sermon-list-card" onClick={handleClick} role="button" tabIndex={0}
        onKeyDown={e => e.key === "Enter" && handleClick()}>
        <div className="slc-body">
          <div className="slc-title-row">
            <h4 className="slc-title">{sermon.title || sermon.filename}</h4>
            <span className={`badge ${sermon.is_primary_pastor ? "badge-hawley" : "badge-other"}`}>
              {shortLastName(sermon.author)}
            </span>
          </div>
          {sermon.main_theme && (
            <p className="slc-theme">{sermon.main_theme}</p>
          )}
          <div className="slc-meta">
            {sermon.date   && <span className="slc-date">{formatDate(sermon.date)}</span>}
            {topRefs.length > 0 && <span className="slc-refs">📖 {topRefs.join(" · ")}</span>}
          </div>
        </div>
        <div className="slc-arrow">›</div>
      </div>
    );
  }

  // Grid view
  return (
    <div className="sermon-card" onClick={handleClick} role="button" tabIndex={0}
      onKeyDown={e => e.key === "Enter" && handleClick()}>

      {/* Header row */}
      <div className="sc-header">
        <span className={`badge ${sermon.is_primary_pastor ? "badge-hawley" : "badge-other"}`}>
          {shortLastName(sermon.author)}
        </span>
        {sermon.date && <span className="sc-date">{formatDate(sermon.date)}</span>}
      </div>

      {/* Title */}
      <h4 className="sc-title">{sermon.title || sermon.filename}</h4>

      {/* Theme */}
      {sermon.main_theme && (
        <p className="sc-theme">✦ {sermon.main_theme}</p>
      )}

      {/* Summary or fallback */}
      {hasSummary ? (
        <p className="sc-summary truncate-3">{sermon.summary}</p>
      ) : (
        <p className="sc-no-summary">
          {sermon.web_url ? "Tap to view sermon" : "Summary not yet available"}
        </p>
      )}

      {/* Footer */}
      <div className="sc-footer">
        {topRefs.length > 0 && (
          <div className="sc-books">
            {topRefs.map(b => (
              <span key={b} className="sc-book-tag">{b}</span>
            ))}
          </div>
        )}
        {topKw.length > 0 && (
          <div className="sc-keywords">
            {topKw.map(k => (
              <span key={k} className="tag">{k}</span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function shortLastName(name) {
  if (!name) return "Unknown";
  const parts = name.trim().split(/\s+/);
  return parts[parts.length - 1] || name;
}

function formatDate(dateStr) {
  if (!dateStr) return "";
  try {
    const d = new Date(dateStr + "T00:00:00");
    return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
  } catch {
    return dateStr;
  }
}
