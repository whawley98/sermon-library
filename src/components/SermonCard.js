// src/components/SermonCard.js
import React from "react";
import { useNavigate } from "react-router-dom";
import "./SermonCard.css";

export default function SermonCard({ sermon, view = "grid" }) {
  const navigate = useNavigate();
  const refs = (sermon.scripture_references || []).slice(0, 3).map(r => r.reference).join(" · ");

  if (view === "list") {
    return (
      <div className="sermon-list-card" onClick={() => navigate(`/sermon/${sermon.id}`)}>
        <div className="slc-left">
          <h4 className="slc-title">{sermon.title || sermon.filename}</h4>
          <p className="slc-meta">
            {sermon.main_theme && <span>{sermon.main_theme}</span>}
            {refs && <span>{refs}</span>}
          </p>
        </div>
        <div className="slc-right">
          <span className={`badge ${sermon.is_william_hawley ? "badge-hawley" : "badge-other"}`}>
            {sermon.is_william_hawley ? "W. Hawley" : shortAuthor(sermon.author)}
          </span>
          {sermon.date && <span className="slc-date">{sermon.date}</span>}
        </div>
      </div>
    );
  }

  return (
    <div className="sermon-card" onClick={() => navigate(`/sermon/${sermon.id}`)}>
      <div className="sc-header">
        <h4 className="sc-title">{sermon.title || sermon.filename}</h4>
        <span className={`badge ${sermon.is_william_hawley ? "badge-hawley" : "badge-other"}`}>
          {sermon.is_william_hawley ? "W. Hawley" : shortAuthor(sermon.author)}
        </span>
      </div>

      {sermon.main_theme && (
        <p className="sc-theme">✦ {sermon.main_theme}</p>
      )}

      {sermon.summary && (
        <p className="sc-summary truncate-3">{sermon.summary}</p>
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

function shortAuthor(name) {
  if (!name) return "Unknown";
  const parts = name.trim().split(" ");
  return parts.length > 1 ? parts[parts.length - 1] : name.substring(0, 14);
}
