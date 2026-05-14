// src/pages/AskPage.js
// Collection-level AI Q&A page with markdown rendering,
// source citations, and suggested questions.

import React, { useState } from "react";
import { askCollection } from "../lib/ai";
import { useNavigate } from "react-router-dom";
import "./AskPage.css";

const SUGGESTED_QUESTIONS = [
  "What Bible books did he preach from most often?",
  "What were his most common sermon themes?",
  "How did his preaching evolve over the decades?",
  "Which scripture verses did he reference most frequently?",
  "What did he teach about prayer?",
  "Find sermons about salvation and the gospel",
  "What series did he preach on the tabernacle?",
  "What did he emphasize about the Christian life?",
];

export default function AskPage({ pastor }) {
  const navigate = useNavigate();
  const [question,  setQuestion]  = useState("");
  const [answer,    setAnswer]    = useState(null);
  const [loading,   setLoading]   = useState(false);
  const [error,     setError]     = useState("");
  const [history,   setHistory]   = useState([]);

  const handleAsk = async (q) => {
    const text = (q || question).trim();
    if (!text || !pastor) return;

    setLoading(true);
    setError("");
    setAnswer(null);

    try {
      const result = await askCollection(text, pastor, pastor.id);
      const entry  = { question: text, answer: result.answer, sources: result.sourcedFrom };
      setAnswer(entry);
      setHistory(prev => [entry, ...prev].slice(0, 10));
      setQuestion("");
    } catch (err) {
      setError(err.message || "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleSuggestion = (q) => {
    setQuestion(q);
    handleAsk(q);
  };

  return (
    <div className="ask-page">
      <div className="ask-inner">

        {/* Header */}
        <header className="ask-header">
          <div className="ask-header-label">AI Assistant</div>
          <h1 className="ask-title">Ask about the Collection</h1>
          <p className="ask-subtitle">
            Ask anything about {pastor?.name || "this pastor"}'s sermons — themes, scripture,
            patterns across decades, or specific topics.
          </p>
        </header>

        {/* Input */}
        <div className="ask-input-section">
          <div className="ask-input-wrap">
            <textarea
              className="ask-textarea"
              placeholder="What would you like to know about this sermon collection?"
              value={question}
              onChange={e => setQuestion(e.target.value)}
              onKeyDown={e => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleAsk();
                }
              }}
              rows={3}
              disabled={loading}
            />
            <button
              className="btn btn-gold ask-submit-btn"
              onClick={() => handleAsk()}
              disabled={loading || !question.trim()}
            >
              {loading
                ? <span className="spinner" style={{ width: 18, height: 18, borderWidth: 2 }} />
                : "Ask ✦"}
            </button>
          </div>
          <p className="ask-hint">Press Enter to submit · Shift+Enter for new line</p>
        </div>

        {/* Error */}
        {error && (
          <div className="ask-error">{error}</div>
        )}

        {/* Answer */}
        {answer && (
          <div className="ask-answer-card">
            <div className="ask-answer-question">"{answer.question}"</div>
            <div
              className="markdown ask-answer-body"
              dangerouslySetInnerHTML={{ __html: markdownToHtml(answer.answer) }}
            />

            {/* Sources */}
            {answer.sources && answer.sources.length > 0 && (
              <div className="ask-sources">
                <div className="ask-sources-label">Sources used</div>
                <div className="ask-sources-list">
                  {answer.sources.map(s => (
                    <button
                      key={s.id}
                      className="ask-source-chip"
                      onClick={() => navigate(`/sermon/${s.id}`)}
                      title="Open sermon"
                    >
                      📖 {s.title}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Suggested questions */}
        {!answer && !loading && (
          <div className="ask-suggestions">
            <div className="ask-suggestions-label">Suggested questions</div>
            <div className="ask-suggestions-grid">
              {SUGGESTED_QUESTIONS.map(q => (
                <button
                  key={q}
                  className="ask-suggestion-btn"
                  onClick={() => handleSuggestion(q)}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* History */}
        {history.length > 1 && (
          <div className="ask-history">
            <div className="ask-history-label">Previous questions</div>
            {history.slice(1).map((entry, i) => (
              <button
                key={i}
                className="ask-history-item"
                onClick={() => setAnswer(entry)}
              >
                {entry.question}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function markdownToHtml(text) {
  return text
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/^### (.+)$/gm, "<h3>$1</h3>")
    .replace(/^## (.+)$/gm, "<h2>$1</h2>")
    .replace(/^# (.+)$/gm, "<h1>$1</h1>")
    .replace(/^\- (.+)$/gm, "<li>$1</li>")
    .replace(/(<li>[\s\S]+?<\/li>)/g, "<ul>$1</ul>")
    .replace(/\n\n/g, "</p><p>")
    .replace(/^(?!<[hul])(.+)$/gm, m => m.startsWith("<") ? m : `<p>${m}</p>`);
}
