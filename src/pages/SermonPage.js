// src/pages/SermonPage.js
// Full sermon detail page with:
// - Summary prominent at top
// - Full text rendered with structure detection
// - Scripture references rail
// - Hover tooltip for KJV verse
// - Click to open full KJV chapter panel (40% width, independent scroll)
// - Ask AI about this sermon
// - Open original document link

import React, { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getSermon, getScriptureRefs, getKJVVerse } from "../lib/firebase";
import { askSermon, getRelatedSermons } from "../lib/ai";
import SermonTextRenderer from "../components/SermonTextRenderer";
import KJVPanel from "../components/KJVPanel";
import "./SermonPage.css";

export default function SermonPage({ pastor }) {
  const { id }      = useParams();
  const navigate    = useNavigate();

  const [sermon,       setSermon]       = useState(null);
  const [refs,         setRefs]         = useState([]);
  const [related,      setRelated]      = useState([]);
  const [loading,      setLoading]      = useState(true);
  const [error,        setError]        = useState(null);

  // KJV panel state
  const [kjvOsisRef,   setKjvOsisRef]   = useState(null);
  const [kjvLabel,     setKjvLabel]     = useState("");
  const [kjvOpen,      setKjvOpen]      = useState(false);

  // KJV tooltip (hover)
  const [tooltip,      setTooltip]      = useState(null);  // { text, ref, x, y }
  const tooltipTimer   = useRef(null);

  // AI Q&A
  const [question,     setQuestion]     = useState("");
  const [aiAnswer,     setAiAnswer]     = useState("");
  const [aiLoading,    setAiLoading]    = useState(false);
  const [aiError,      setAiError]      = useState("");

  // ── Load sermon ──────────────────────────────────────────────────────────
  useEffect(() => {
    if (!id) return;
    setLoading(true);
    setError(null);
    Promise.all([getSermon(id), getScriptureRefs(id)])
      .then(([s, r]) => {
        if (!s) { setError("Sermon not found."); return; }
        setSermon(s);
        setRefs(r);
        if (pastor?.id) {
          getRelatedSermons(s, pastor.id).then(setRelated).catch(() => {});
        }
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [id, pastor?.id]);

  // ── Handle reference click (open KJV panel) ───────────────────────────────
  const handleRefClick = useCallback((referenceStr) => {
    // Find OSIS ref from our refs list or parse from string
    const found = refs.find(r =>
      r.reference === referenceStr ||
      referenceStr.includes(r.book)
    );
    if (found?.osis_ref) {
      setKjvOsisRef(found.osis_ref);
      setKjvLabel(found.reference);
    } else {
      // Try to parse a human-readable ref
      const m = referenceStr.match(/^([1-3]?\s?[A-Za-z\s]+?)\s+(\d+):(\d+)/);
      if (m) {
        const book = m[1].trim();
        const osisMap = { "John":"John","Romans":"Rom","Genesis":"Gen","Psalms":"Ps",
          "Matthew":"Matt","Luke":"Luke","Acts":"Acts","Revelation":"Rev",
          "Isaiah":"Isa","Jeremiah":"Jer","Ephesians":"Eph","Philippians":"Phil",
        };
        const osisBook = osisMap[book] || book;
        setKjvOsisRef(`${osisBook}.${m[2]}.${m[3]}`);
        setKjvLabel(referenceStr);
      }
    }
    setKjvOpen(true);
    setTooltip(null);
  }, [refs]);

  // ── Handle reference rail click ──────────────────────────────────────────
  const handleRailRefClick = (ref) => {
    setKjvOsisRef(ref.osis_ref);
    setKjvLabel(ref.reference);
    setKjvOpen(true);
  };

  // ── Hover tooltip ─────────────────────────────────────────────────────────
  const handleRefHover = useCallback(async (osisRef, referenceStr, e) => {
    clearTimeout(tooltipTimer.current);
    const rect = e.target.getBoundingClientRect();
    tooltipTimer.current = setTimeout(async () => {
      try {
        const verse = await getKJVVerse(osisRef);
        if (verse) {
          setTooltip({
            text:      verse.text,
            reference: referenceStr,
            top:       rect.bottom + window.scrollY + 8,
            left:      rect.left + window.scrollX,
          });
        }
      } catch (_) {}
    }, 400);
  }, []);

  const handleRefLeave = useCallback(() => {
    clearTimeout(tooltipTimer.current);
    setTimeout(() => setTooltip(null), 200);
  }, []);

  // ── AI Q&A ───────────────────────────────────────────────────────────────
  const handleAsk = async (e) => {
    e.preventDefault();
    if (!question.trim() || !sermon) return;
    setAiLoading(true);
    setAiError("");
    setAiAnswer("");
    try {
      const answer = await askSermon(question, sermon, refs);
      setAiAnswer(answer);
    } catch (err) {
      setAiError(err.message || "Something went wrong.");
    } finally {
      setAiLoading(false);
    }
  };

  // ── Loading / error states ────────────────────────────────────────────────
  if (loading) return (
    <div className="sermon-page-loading">
      <div className="spinner" />
      <p>Loading sermon…</p>
    </div>
  );

  if (error || !sermon) return (
    <div className="sermon-page-error">
      <h2>Sermon not found</h2>
      <p>{error}</p>
      <button className="btn btn-secondary" onClick={() => navigate(-1)}>← Back</button>
    </div>
  );

  const hasText = sermon.full_text_raw && sermon.full_text_raw.trim().length > 100;

  return (
    <div className={`sermon-page-layout${kjvOpen ? " kjv-open" : ""}`}>
      {/* ── Main sermon content ─────────────────────────────────────────── */}
      <div className="sermon-content">

        {/* Back button */}
        <button className="sp-back-btn" onClick={() => navigate(-1)}>
          ← Back to Library
        </button>

        {/* Title block */}
        <header className="sp-header">
          <div className="sp-meta-row">
            <span className={`badge ${sermon.is_primary_pastor ? "badge-hawley" : "badge-other"}`}>
              {sermon.author || "Unknown"}
            </span>
            {sermon.date && <span className="sp-date">{formatDate(sermon.date)}</span>}
            {sermon.estimated_length && (
              <span className="sp-length">{sermon.estimated_length} read</span>
            )}
          </div>

          <h1 className="sp-title">{sermon.title}</h1>

          {sermon.main_theme && (
            <p className="sp-theme">✦ {sermon.main_theme}</p>
          )}
        </header>

        {/* Summary */}
        {sermon.summary && (
          <div className="sp-summary">
            <div className="sp-summary-label">Summary</div>
            <p>{sermon.summary}</p>
          </div>
        )}

        {/* Keywords */}
        {(sermon.keywords || []).length > 0 && (
          <div className="sp-keywords">
            {sermon.keywords.map(k => (
              <span key={k} className="tag">{k}</span>
            ))}
          </div>
        )}

        {/* Scripture references rail */}
        {refs.length > 0 && (
          <div className="sp-refs-section">
            <div className="sp-section-label">Scripture References</div>
            <div className="sp-refs-rail">
              {refs.map(r => (
                <button
                  key={r.id}
                  className="sp-ref-btn"
                  onClick={() => handleRailRefClick(r)}
                  onMouseEnter={e => handleRefHover(r.osis_ref, r.reference, e)}
                  onMouseLeave={handleRefLeave}
                  title={`Open ${r.reference} in KJV`}
                >
                  <span className="sp-ref-text">{r.reference}</span>
                  {r.context && <span className="sp-ref-context">{r.context}</span>}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="sp-divider" />

        {/* Full text or fallback */}
        {hasText ? (
          <div className="sp-text-section">
            <div className="sp-section-label">Full Sermon</div>
            <SermonTextRenderer
              text={sermon.full_text_raw}
              onRefClick={handleRefClick}
            />
          </div>
        ) : (
          <div className="sp-no-text">
            <p>Full text not available in the app.</p>
            {sermon.web_url && (
              <a href={sermon.web_url} target="_blank" rel="noopener noreferrer"
                className="btn btn-secondary">
                📄 Open Original Document
              </a>
            )}
          </div>
        )}

        {/* Open original link (always show if available) */}
        {hasText && sermon.web_url && (
          <div className="sp-open-original">
            <a href={sermon.web_url} target="_blank" rel="noopener noreferrer"
              className="btn btn-ghost sp-original-btn">
              📄 Open Original Document ↗
            </a>
          </div>
        )}

        {/* Ask AI */}
        <div className="sp-ask-section">
          <div className="sp-section-label">Ask about this sermon</div>
          <form className="sp-ask-form" onSubmit={handleAsk}>
            <input
              className="input sp-ask-input"
              type="text"
              placeholder="What is the main point? What does this teach about prayer?"
              value={question}
              onChange={e => setQuestion(e.target.value)}
              disabled={aiLoading}
            />
            <button
              type="submit"
              className="btn btn-gold"
              disabled={aiLoading || !question.trim()}
            >
              {aiLoading ? <span className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} /> : "Ask"}
            </button>
          </form>

          {aiError && (
            <div className="sp-ai-error">{aiError}</div>
          )}

          {aiAnswer && (
            <div className="sp-ai-answer">
              <div className="sp-ai-answer-label">Answer</div>
              <div className="markdown" dangerouslySetInnerHTML={{ __html: markdownToHtml(aiAnswer) }} />
            </div>
          )}
        </div>

        {/* Related sermons */}
        {related.length > 0 && (
          <div className="sp-related">
            <div className="sp-section-label">Related Sermons</div>
            <div className="sp-related-list">
              {related.map(s => (
                <button
                  key={s.id}
                  className="sp-related-card"
                  onClick={() => navigate(`/sermon/${s.id}`)}
                >
                  <div className="sp-related-title">{s.title}</div>
                  {s.main_theme && <div className="sp-related-theme">{s.main_theme}</div>}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ── KJV Panel ───────────────────────────────────────────────────── */}
      {kjvOpen && (
        <div className="kjv-panel-wrap">
          <KJVPanel
            osisRef={kjvOsisRef}
            referenceLabel={kjvLabel}
            onClose={() => setKjvOpen(false)}
          />
        </div>
      )}

      {/* ── Hover tooltip ───────────────────────────────────────────────── */}
      {tooltip && (
        <div
          className="kjv-tooltip"
          style={{ top: tooltip.top, left: tooltip.left }}
          onMouseEnter={() => clearTimeout(tooltipTimer.current)}
          onMouseLeave={() => setTooltip(null)}
        >
          <div className="kjv-tooltip-ref">{tooltip.reference}</div>
          <div className="kjv-tooltip-text">{tooltip.text}</div>
        </div>
      )}
    </div>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────
function formatDate(dateStr) {
  if (!dateStr) return "";
  try {
    const d = new Date(dateStr + "T00:00:00");
    return d.toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
  } catch { return dateStr; }
}

// Minimal markdown → HTML for AI responses
function markdownToHtml(text) {
  return text
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/^### (.+)$/gm, "<h3>$1</h3>")
    .replace(/^## (.+)$/gm, "<h2>$1</h2>")
    .replace(/^# (.+)$/gm, "<h1>$1</h1>")
    .replace(/^\- (.+)$/gm, "<li>$1</li>")
    .replace(/(<li>.+<\/li>)/gs, "<ul>$1</ul>")
    .replace(/\n\n/g, "</p><p>")
    .replace(/^(?!<[hul])(.+)$/gm, (m) => m.startsWith("<") ? m : `<p>${m}</p>`);
}
