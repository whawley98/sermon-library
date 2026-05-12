// src/pages/SermonPage.js
import React, { useState, useEffect } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { getSermon } from "../lib/firebase";
import { askSermon, getRelatedSermons } from "../lib/ai";
import SermonCard from "../components/SermonCard";
import "./SermonPage.css";

export default function SermonPage({ pastor }) {
  const { id } = useParams();
  const navigate = useNavigate();
  const [sermon,    setSermon]    = useState(null);
  const [related,   setRelated]   = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [aiQ,       setAiQ]       = useState("");
  const [aiAnswer,  setAiAnswer]  = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError,   setAiError]   = useState(null);

  useEffect(() => {
    setLoading(true);
    getSermon(id)
      .then(s => {
        setSermon(s);
        if (s && pastor?.id) {
          getRelatedSermons(s, pastor.id).then(setRelated).catch(() => {});
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [id, pastor?.id]);

  const handleAsk = async () => {
    if (!aiQ.trim() || !sermon) return;
    setAiLoading(true);
    setAiAnswer("");
    setAiError(null);
    try {
      const answer = await askSermon(aiQ, sermon);
      setAiAnswer(answer);
    } catch (e) {
      setAiError(e.message);
    } finally {
      setAiLoading(false);
    }
  };

  if (loading) return (
    <div className="sermon-page-wrap">
      <div className="page-loading"><div className="spinner" /></div>
    </div>
  );

  if (!sermon) return (
    <div className="sermon-page-wrap">
      <div className="not-found">
        <h2>Sermon not found</h2>
        <button className="btn btn-secondary" onClick={() => navigate(-1)}>← Back</button>
      </div>
    </div>
  );

  const refs       = sermon.scripture_references || [];
  const keywords   = sermon.keywords || [];
  const hasGoodText = sermon.extraction_quality === "high" &&
                      sermon.full_text_raw &&
                      sermon.full_text_raw.length > 200 &&
                      !sermon.full_text_raw.startsWith("W Y V") &&
                      !sermon.full_text_raw.match(/^[^a-zA-Z]{20}/);

  return (
    <div className="sermon-page-wrap">
      <div className="sermon-page">

        {/* Nav */}
        <div className="sermon-nav no-print">
          <button className="btn btn-ghost" onClick={() => navigate(-1)}>← Back</button>
          <div className="sermon-nav-right">
            {sermon.web_url && (
              <a href={sermon.web_url} target="_blank" rel="noopener noreferrer" className="btn btn-secondary">
                📄 Open Original File
              </a>
            )}
            <button className="btn btn-secondary" onClick={() => window.print()}>🖨️ Print</button>
          </div>
        </div>

        {/* Header */}
        <div className="sermon-header">
          <div className="sermon-eyebrow">
            <span className={`badge ${sermon.is_primary_pastor ? "badge-hawley" : "badge-other"}`}>
              {sermon.author}
            </span>
            {sermon.folder && <span className="sermon-folder">{sermon.folder}</span>}
            {sermon.series_name && <span className="sermon-series">Series: {sermon.series_name}</span>}
          </div>
          <h1 className="sermon-title">{sermon.title || sermon.filename}</h1>
          <div className="sermon-meta">
            {sermon.date           && <MetaItem icon="📅" label="Date"   value={sermon.date} />}
            {sermon.main_theme     && <MetaItem icon="✦"  label="Theme"  value={sermon.main_theme} />}
            {sermon.estimated_length && <MetaItem icon="⏱" label="Length" value={sermon.estimated_length} />}
            {sermon.word_count > 0 && <MetaItem icon="📝" label="Words"  value={sermon.word_count.toLocaleString()} />}
          </div>
        </div>

        <hr className="divider" />

        <div className="sermon-body">
          {/* Main content */}
          <div className="sermon-main">

            {/* Summary — always show prominently */}
            {sermon.summary ? (
              <section className="sermon-section">
                <h2 className="section-heading">Summary</h2>
                <p className="sermon-summary">{sermon.summary}</p>
              </section>
            ) : (
              <section className="sermon-section">
                <div className="no-summary-notice">
                  <p>Summary not available for this sermon.</p>
                  {sermon.web_url && (
                    <a href={sermon.web_url} target="_blank" rel="noopener noreferrer" className="btn btn-primary" style={{ marginTop: "0.75rem", display: "inline-flex" }}>
                      📄 Open Original File to Read
                    </a>
                  )}
                </div>
              </section>
            )}

            {/* Sermon structure if available */}
            {sermon.structure?.main_points?.length > 0 && (
              <section className="sermon-section">
                <h2 className="section-heading">Outline</h2>
                <ol className="sermon-outline">
                  {sermon.structure.main_points.map((point, i) => (
                    <li key={i}>{point}</li>
                  ))}
                </ol>
              </section>
            )}

            {/* Full text — only render if it's actually readable */}
            {hasGoodText ? (
              <section className="sermon-section">
                <h2 className="section-heading">Sermon Text</h2>
                <div className="sermon-text">
                  {sermon.full_text_raw
                    .split(/\n{2,}/)
                    .filter(p => p.trim().length > 20)
                    .map((para, i) => (
                      <p key={i}>{para.trim()}</p>
                    ))}
                </div>
              </section>
            ) : sermon.web_url ? (
              <section className="sermon-section">
                <h2 className="section-heading">Full Sermon</h2>
                <div className="open-original-card">
                  <div className="open-original-icon">📄</div>
                  <div>
                    <p className="open-original-title">Read the complete sermon</p>
                    <p className="open-original-sub">
                      This sermon is best read in its original format.
                    </p>
                    <a href={sermon.web_url} target="_blank" rel="noopener noreferrer" className="btn btn-primary" style={{ marginTop: "0.75rem", display: "inline-flex" }}>
                      Open in OneDrive
                    </a>
                  </div>
                </div>
              </section>
            ) : null}

            {/* AI Q&A */}
            <section className="sermon-section no-print">
              <h2 className="section-heading">Ask About This Sermon</h2>
              <div className="ai-qa">
                <div className="ai-input-row">
                  <input
                    className="input"
                    type="text"
                    placeholder="e.g. What is the main point? What application does he give?"
                    value={aiQ}
                    onChange={e => setAiQ(e.target.value)}
                    onKeyDown={e => e.key === "Enter" && handleAsk()}
                  />
                  <button className="btn btn-gold" onClick={handleAsk} disabled={aiLoading || !aiQ.trim()}>
                    {aiLoading ? "Thinking…" : "Ask"}
                  </button>
                </div>
                {aiError && (
                  <div className="ai-error">⚠️ {aiError}</div>
                )}
                {aiAnswer && (
                  <div className="ai-answer">
                    <div className="ai-answer-label">Answer</div>
                    <p>{aiAnswer}</p>
                  </div>
                )}
              </div>
            </section>
          </div>

          {/* Aside */}
          <aside className="sermon-aside">
            {refs.length > 0 && (
              <div className="aside-card">
                <h3 className="aside-heading">Scripture ({refs.length})</h3>
                <ul className="verse-list">
                  {refs.map((r, i) => (
                    <li key={i} className="verse-item">
                      <span className="verse-ref">{r.reference}</span>
                      {r.context && <span className="verse-ctx">{r.context}</span>}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {keywords.length > 0 && (
              <div className="aside-card">
                <h3 className="aside-heading">Keywords</h3>
                <div className="tag-cloud">
                  {keywords.map(k => (
                    <Link key={k} to={`/library?keyword=${encodeURIComponent(k)}`} className="tag">{k}</Link>
                  ))}
                </div>
              </div>
            )}

            {sermon.notes && (
              <div className="aside-card">
                <h3 className="aside-heading">Notes</h3>
                <p style={{ fontSize: "0.85rem", color: "var(--color-text-muted)", fontStyle: "italic" }}>
                  {sermon.notes}
                </p>
              </div>
            )}

            {related.length > 0 && (
              <div className="aside-card no-print">
                <h3 className="aside-heading">Related Sermons</h3>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                  {related.map(s => <SermonCard key={s.id} sermon={s} view="list" />)}
                </div>
              </div>
            )}
          </aside>
        </div>
      </div>
    </div>
  );
}

function MetaItem({ icon, label, value }) {
  return (
    <div className="meta-item">
      <span className="meta-icon">{icon}</span>
      <span className="meta-label">{label}:</span>
      <span className="meta-value">{value}</span>
    </div>
  );
}
