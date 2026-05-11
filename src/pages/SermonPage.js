// src/pages/SermonPage.js
import React, { useState, useEffect, useRef } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { getSermon } from "../lib/firebase";
import { askSermon, getRelatedSermons } from "../lib/ai";
import SermonCard from "../components/SermonCard";
import "./SermonPage.css";

export default function SermonPage({ pastor }) {
  const { id } = useParams();
  const navigate = useNavigate();
  const [sermon,   setSermon]   = useState(null);
  const [related,  setRelated]  = useState([]);
  const [loading,  setLoading]  = useState(true);
  const [aiQ,      setAiQ]      = useState("");
  const [aiAnswer, setAiAnswer] = useState("");
  const [aiLoading,setAiLoading]= useState(false);
  const [printMode,setPrintMode]= useState(false);
  const printRef = useRef(null);

  useEffect(() => {
    setLoading(true);
    getSermon(id)
      .then((s) => {
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
    try {
      const answer = await askSermon(aiQ, sermon);
      setAiAnswer(answer);
    } catch (e) {
      setAiAnswer(`Error: ${e.message}`);
    } finally {
      setAiLoading(false);
    }
  };

  const handlePrint = () => {
    setPrintMode(true);
    setTimeout(() => { window.print(); setPrintMode(false); }, 100);
  };

  if (loading) return <div className="sermon-loading"><div className="spinner" /></div>;
  if (!sermon) return (
    <div className="sermon-not-found">
      <h2>Sermon not found</h2>
      <Link to="/library" className="btn btn-secondary">← Back to Library</Link>
    </div>
  );

  const refs = sermon.scripture_references || [];
  const text = sermon.full_text_clean || sermon.full_text_raw || "";

  return (
    <div className={`sermon-page ${printMode ? "print-mode" : ""}`} ref={printRef}>

      {/* Back nav */}
      <div className="sermon-nav no-print">
        <button className="btn btn-ghost" onClick={() => navigate(-1)}>
          ← Back
        </button>
        <div className="sermon-nav-actions">
          {sermon.web_url && (
            <a
              href={sermon.web_url}
              target="_blank"
              rel="noopener noreferrer"
              className="btn btn-secondary"
            >
              📄 Open Original
            </a>
          )}
          <button className="btn btn-secondary" onClick={handlePrint}>
            🖨️ Print
          </button>
        </div>
      </div>

      {/* Header */}
      <div className="sermon-header">
        <div className="sermon-eyebrow">
          <span className={`badge ${sermon.is_william_hawley ? "badge-hawley" : "badge-other"}`}>
            {sermon.author}
          </span>
          {sermon.folder && <span className="sermon-folder">{sermon.folder}</span>}
          {sermon.series_name && <span className="sermon-series">Series: {sermon.series_name}</span>}
        </div>

        <h1 className="sermon-title">{sermon.title || sermon.filename}</h1>

        <div className="sermon-meta">
          {sermon.date          && <MetaItem icon="📅" label="Date"  value={sermon.date} />}
          {sermon.main_theme    && <MetaItem icon="✦"  label="Theme" value={sermon.main_theme} />}
          {sermon.estimated_length && <MetaItem icon="⏱" label="Length" value={sermon.estimated_length} />}
          {sermon.word_count    && <MetaItem icon="📝" label="Words" value={sermon.word_count.toLocaleString()} />}
        </div>
      </div>

      <hr className="divider" />

      {/* Two-column layout */}
      <div className="sermon-body">

        {/* Main content */}
        <div className="sermon-main">

          {/* Summary */}
          {sermon.summary && (
            <section className="sermon-section">
              <h2 className="section-heading">Summary</h2>
              <p className="sermon-summary">{sermon.summary}</p>
            </section>
          )}

          {/* Full text */}
          {text && (
            <section className="sermon-section">
              <h2 className="section-heading">Sermon Text</h2>
              <div className="sermon-text">
                {text.split("\n\n").filter(Boolean).map((para, i) => (
                  <p key={i}>{para.trim()}</p>
                ))}
              </div>
            </section>
          )}

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
                <button
                  className="btn btn-gold"
                  onClick={handleAsk}
                  disabled={aiLoading || !aiQ.trim()}
                >
                  {aiLoading ? "Thinking…" : "Ask"}
                </button>
              </div>
              {aiAnswer && (
                <div className="ai-answer">
                  <div className="ai-answer-label">Answer</div>
                  <p>{aiAnswer}</p>
                </div>
              )}
            </div>
          </section>
        </div>

        {/* Sidebar */}
        <aside className="sermon-aside">

          {/* Scripture references */}
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

          {/* Keywords */}
          {(sermon.keywords || []).length > 0 && (
            <div className="aside-card">
              <h3 className="aside-heading">Keywords</h3>
              <div className="tag-cloud">
                {sermon.keywords.map(k => (
                  <Link key={k} to={`/library?keyword=${encodeURIComponent(k)}`} className="tag">
                    {k}
                  </Link>
                ))}
              </div>
            </div>
          )}

          {/* Related sermons */}
          {related.length > 0 && (
            <div className="aside-card no-print">
              <h3 className="aside-heading">Related Sermons</h3>
              <div className="related-list">
                {related.map(s => (
                  <SermonCard key={s.id} sermon={s} view="list" />
                ))}
              </div>
            </div>
          )}
        </aside>
      </div>

      {/* Print footer */}
      <div className="print-footer print-only" style={{ display: "none" }}>
        <hr style={{ margin: "2rem 0 1rem" }} />
        <p style={{ fontSize: "0.8rem", color: "#666", textAlign: "center" }}>
          {sermon.author} · {sermon.date || ""} · Hawley Sermon Library
        </p>
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
