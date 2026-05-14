// src/components/SermonTextRenderer.js
// Intelligent sermon text renderer.
// Detects outline structure (I., II., A., B., 1., 2., INTRO:, CONCLUSION:)
// and renders with visual hierarchy. Falls back gracefully for unstructured text.

import React, { useMemo } from "react";
import "./SermonTextRenderer.css";

// ── Pattern detection ──────────────────────────────────────────────────────

const PATTERNS = {
  // Roman numerals: I. II. III. IV. V. etc (standalone at start of line)
  roman:       /^(I{1,4}|II{1,3}|IV|V|VI{0,3}|VII|VIII|IX|X{1,3})\.\s+(.+)/i,
  // Alpha: A. B. C. etc
  alpha:       /^([A-Z])\.\s+(.+)/,
  // Numeric: 1. 2. 3. etc
  numeric:     /^(\d+)\.\s+(.+)/,
  // Labels: INTRO, INTRODUCTION, CONCLUSION, TEXT, APPLICATION, ILLUSTRATION
  label:       /^(INTRO(?:DUCTION)?|CONCL(?:USION)?|TEXT|APPLICATION|ILLUSTRATION|INVITATION|SUMMARY|BACKGROUND|CONTEXT|TRANSITION|REVIEW)\s*:?\s*(.*)/i,
  // Scripture quote detection: starts with verse reference pattern
  scripture:   /^([1-3]?\s?[A-Za-z]+\.?\s+\d+:\d+[\d,\-–\s]*)\s*[-–]\s*(.+)/,
};

function classifyLine(line) {
  const trimmed = line.trim();
  if (!trimmed) return { type: "blank", text: "" };

  for (const [type, pattern] of Object.entries(PATTERNS)) {
    const m = trimmed.match(pattern);
    if (m) {
      if (type === "roman")    return { type: "roman",     marker: m[1], text: m[2] };
      if (type === "alpha")    return { type: "alpha",     marker: m[1], text: m[2] };
      if (type === "numeric")  return { type: "numeric",   marker: m[1], text: m[2] };
      if (type === "label")    return { type: "label",     marker: m[1], text: m[2] };
      if (type === "scripture") return { type: "scripture", ref: m[1],   text: m[2] };
    }
  }

  // All-caps line (short enough to be a heading)
  if (trimmed === trimmed.toUpperCase() && trimmed.length < 80 && /[A-Z]/.test(trimmed)) {
    return { type: "allcaps", text: trimmed };
  }

  return { type: "paragraph", text: trimmed };
}

// ── Detect if text has any structure ───────────────────────────────────────
function hasStructure(text) {
  const lines = text.split("\n").map(l => l.trim()).filter(Boolean);
  let structured = 0;
  for (const line of lines.slice(0, 50)) {
    const { type } = classifyLine(line);
    if (["roman", "alpha", "label", "allcaps"].includes(type)) structured++;
  }
  return structured >= 2;
}

// ── Render a single classified line ────────────────────────────────────────
function renderLine(classified, idx, onRefClick) {
  const { type, marker, text, ref } = classified;

  switch (type) {
    case "blank":
      return <div key={idx} className="str-spacer" />;

    case "roman":
      return (
        <div key={idx} className="str-roman">
          <span className="str-roman-marker">{marker}.</span>
          <span className="str-roman-text">{text}</span>
        </div>
      );

    case "alpha":
      return (
        <div key={idx} className="str-alpha">
          <span className="str-alpha-marker">{marker}.</span>
          <span className="str-alpha-text">{text}</span>
        </div>
      );

    case "numeric":
      return (
        <div key={idx} className="str-numeric">
          <span className="str-numeric-marker">{marker}.</span>
          <span className="str-numeric-text">{text}</span>
        </div>
      );

    case "label":
      return (
        <div key={idx} className="str-label-block">
          <span className="str-label">{marker.toUpperCase()}</span>
          {text && <span className="str-label-text"> — {text}</span>}
        </div>
      );

    case "allcaps":
      return (
        <div key={idx} className="str-allcaps">{text}</div>
      );

    case "scripture":
      return (
        <div key={idx} className="verse-block">
          <span className="verse-reference">{ref}</span>
          <span className="verse-text">{text}</span>
        </div>
      );

    case "paragraph":
    default:
      return (
        <p key={idx} className="str-paragraph">
          {inlineScriptureRefs(text, onRefClick)}
        </p>
      );
  }
}

// ── Inline scripture reference detection & clickable links ─────────────────
const INLINE_REF = /\b([1-3]?\s?[A-Za-z]+\.?\s+\d+:\d+(?:[-–]\d+)?)\b/g;

function inlineScriptureRefs(text, onRefClick) {
  if (!onRefClick) return text;

  const parts  = [];
  let   lastIdx = 0;
  let   match;

  INLINE_REF.lastIndex = 0;
  while ((match = INLINE_REF.exec(text)) !== null) {
    if (match.index > lastIdx) {
      parts.push(text.slice(lastIdx, match.index));
    }
    const ref = match[1].trim();
    parts.push(
      <button
        key={match.index}
        className="inline-ref"
        onClick={(e) => { e.stopPropagation(); onRefClick(ref); }}
        title={`Open ${ref} in KJV panel`}
      >
        {ref}
      </button>
    );
    lastIdx = match.index + match[0].length;
  }
  if (lastIdx < text.length) parts.push(text.slice(lastIdx));

  return parts.length > 0 ? parts : text;
}

// ── Main component ─────────────────────────────────────────────────────────

export default function SermonTextRenderer({ text, onRefClick }) {
  const rendered = useMemo(() => {
    if (!text || text.trim().length === 0) return null;

    const lines      = text.split("\n");
    const structured = hasStructure(text);

    if (!structured) {
      // Unstructured: group into paragraphs by blank lines
      const paragraphs = [];
      let   current    = [];
      for (const line of lines) {
        if (!line.trim()) {
          if (current.length > 0) {
            paragraphs.push(current.join(" ").trim());
            current = [];
          }
        } else {
          current.push(line.trim());
        }
      }
      if (current.length > 0) paragraphs.push(current.join(" ").trim());

      return paragraphs.map((para, i) => (
        <p key={i} className="str-paragraph">
          {inlineScriptureRefs(para, onRefClick)}
        </p>
      ));
    }

    // Structured: classify and render each line
    return lines.map((line, i) => {
      const classified = classifyLine(line);
      return renderLine(classified, i, onRefClick);
    });
  }, [text, onRefClick]);

  if (!rendered) return <p className="str-empty">No text available for this sermon.</p>;

  return (
    <div className="sermon-text-renderer">
      {rendered}
    </div>
  );
}
