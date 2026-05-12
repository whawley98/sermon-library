// src/components/SermonCard.js
import React from "react";
import { useNavigate } from "react-router-dom";
import "./SermonCard.css";

export default function SermonCard({ sermon, view = "grid" }) {
  const navigate = useNavigate();
  const refs     = (sermon.scripture_references || []).slice(0, 3).map(r => r.reference).join(" · ");
  const hasSummary = sermon.summary && sermon.summary.length > 10;

  const handleClick = () => navigate(`/sermon/${sermon.id}`);

  if (view === "list") {
    return (
      <div className="sermon-list-card" onClick={handleClick}>
        <div className="slc-left">
          <h4 className="slc-title">{sermon.title || sermon.filename}</h4>
          <p className="slc-meta">
            {sermon.main_theme && <span>{sermon.main_theme}</span>}
            {refs && <span>{refs}</span>}
          </p>
        </div>
        <div className="slc-right">
          <span className={`badge ${sermon.is_primary_pastor ? "badge-hawley" : "badge-other"}`}>
            {sermon.is_primary_pastor ? shortName(sermon.author) : shortName(sermon.author)}
          </span>
          {sermon.date && <span className="slc-date">{sermon.date}</span>}
        </div>
      </div>
    );
  }

  return (
    <div className="sermon-card" onClick={handleClick}>
      <div className="sc-header">
        <h4 className="sc-title">{sermon.title || sermon.filename}</h4>
        <span className={`badge ${sermon.is_primary_pastor ? "badge-hawley" : "badge-other"}`}>
          {shortName(sermon.author)}
        </span>
      </div>

      {sermon.main_theme && (
        <p className="sc-theme">✦ {sermon.main_theme}</p>
      )}

      {hasSummary ? (
        <p className="sc-summary truncate-3">{sermon.summary}</p>
      ) : (
        <p className="sc-no-summary">
          {sermon.web_url ? "Click to open original sermon" : "Summary not yet available"}
        </p>
      )}

      <div className="sc-footer">
        {refs && <span className="sc-refs">📖 {refs}</span>}
        <div className="sc-tags">
          {(sermon.keywords || []).slice(0, 3).map(k => (
            <span key={k} className="tag">{k}</span>
          ))}
        </div>
      </div>
    </div>
  );
}

function shortName(name) {
  if (!name) return "Unknown";
  const parts = name.trim().split(" ");
  if (parts.length >= 2) return parts[parts.length - 1];
  return name.length > 16 ? name.substring(0, 14) + "…" : name;
}
