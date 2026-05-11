// src/pages/AskPage.js
import React, { useState, useRef } from "react";
import { Link } from "react-router-dom";
import { askCollection, generateMinistrySummary } from "../lib/ai";
import { getStats } from "../lib/firebase";
import "./AskPage.css";

const SUGGESTIONS = [
  "What did he preach about most often?",
  "Find sermons about grief and loss",
  "Did he ever preach a series on prayer?",
  "What Bible books did he reference most?",
  "Find sermons about the Holy Spirit",
  "What were his favorite illustrations?",
];

export default function AskPage({ pastor }) {
  const [messages,  setMessages]  = useState([]);
  const [input,     setInput]     = useState("");
  const [loading,   setLoading]   = useState(false);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const bottomRef = useRef(null);

  const sendMessage = async (text) => {
    const question = text || input.trim();
    if (!question || loading) return;
    setInput("");

    const userMsg = { role: "user", content: question };
    setMessages(prev => [...prev, userMsg]);
    setLoading(true);

    try {
      const { answer, sourcedFrom } = await askCollection(question, pastor, pastor?.id);
      setMessages(prev => [...prev, {
        role: "assistant",
        content: answer,
        sources: sourcedFrom,
      }]);
    } catch (e) {
      setMessages(prev => [...prev, {
        role: "assistant",
        content: `Sorry, I ran into an error: ${e.message}`,
        error: true,
      }]);
    } finally {
      setLoading(false);
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 100);
    }
  };

  const generateSummary = async () => {
    setSummaryLoading(true);
    try {
      const stats = await getStats(pastor?.id);
      const summary = await generateMinistrySummary(pastor, stats);
      setMessages(prev => [...prev, {
        role: "assistant",
        content: summary,
        label: "Ministry Summary",
      }]);
    } catch (e) {
      alert("Could not generate summary: " + e.message);
    } finally {
      setSummaryLoading(false);
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 100);
    }
  };

  return (
    <div className="ask-page">
      <div className="page-header">
        <h1>Ask the Collection</h1>
        <p>
          Ask questions about {pastor?.name || "the pastor"}'s sermons —
          powered by AI with answers grounded in the actual text.
        </p>
      </div>

      {/* Special actions */}
      <div className="ask-actions">
        <button
          className="btn btn-secondary"
          onClick={generateSummary}
          disabled={summaryLoading}
        >
          {summaryLoading ? "Generating…" : "✦ Generate Ministry Summary"}
        </button>
      </div>

      {/* Conversation */}
      <div className="conversation">
        {messages.length === 0 && (
          <div className="ask-empty">
            <div className="ask-empty-icon">💬</div>
            <h3>Ask anything about the sermon collection</h3>
            <p>Try one of these:</p>
            <div className="suggestion-grid">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  className="suggestion-btn"
                  onClick={() => sendMessage(s)}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`message message-${msg.role} ${msg.error ? "message-error" : ""}`}>
            {msg.label && <div className="message-label">{msg.label}</div>}
            <div className="message-content">
              {msg.content.split("\n").map((line, j) => (
                <p key={j}>{line}</p>
              ))}
            </div>
            {msg.sources?.length > 0 && (
              <div className="message-sources">
                <span className="sources-label">Based on:</span>
                {msg.sources.map((s) => (
                  <Link key={s.id} to={`/sermon/${s.id}`} className="source-link">
                    {s.title}
                  </Link>
                ))}
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="message message-assistant">
            <div className="thinking">
              <span /><span /><span />
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="ask-input-bar">
        <input
          className="input ask-input"
          type="text"
          placeholder={`Ask about ${pastor?.name || "the collection"}…`}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === "Enter" && sendMessage()}
          disabled={loading}
        />
        <button
          className="btn btn-gold"
          onClick={() => sendMessage()}
          disabled={loading || !input.trim()}
        >
          Ask
        </button>
      </div>
    </div>
  );
}
