// src/pages/StatsPage.js
import React, { useState, useEffect } from "react";
import { getStats } from "../lib/firebase";
import "./StatsPage.css";

export default function StatsPage({ pastor }) {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!pastor?.id) return;
    getStats(pastor.id)
      .then(setStats)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [pastor?.id]);

  if (loading) return <div className="stats-page-wrap"><div className="stats-loading"><div className="spinner" /></div></div>;
  if (!stats)  return <div className="stats-page-wrap"><div className="stats-empty"><p>No statistics available yet.</p></div></div>;

  const topKw    = stats.top_keywords    || [];
  const topBooks = stats.top_bible_books || [];
  const maxKw    = topKw[0]?.count    || 1;
  const maxBook  = topBooks[0]?.count || 1;

  return (
    <div className="stats-page-wrap">
    <div className="stats-page">
      <div className="page-header">
        <h1>Collection Insights</h1>
        <p>{pastor?.name} · {pastor?.description}</p>
      </div>

      {/* Summary cards */}
      <div className="stat-cards">
        <StatCard icon="📚" value={stats.total_sermons?.toLocaleString()} label="Total Sermons" />
        <StatCard icon="✝️" value={stats.william_hawley_count?.toLocaleString()} label={`By ${pastor?.name?.split(" ").pop()}`} />
        <StatCard icon="👥" value={stats.other_preachers_count?.toLocaleString()} label="Other Preachers" />
        <StatCard icon="📖" value={topBooks.length} label="Bible Books Referenced" />
      </div>

      <div className="stats-grid">

        {/* Top keywords */}
        <div className="stats-panel">
          <h2 className="stats-panel-title">Top Topics & Keywords</h2>
          <div className="bar-chart">
            {topKw.slice(0, 20).map(({ word, count }) => (
              <div key={word} className="bar-row">
                <span className="bar-label">{word}</span>
                <div className="bar-track">
                  <div
                    className="bar-fill"
                    style={{ width: `${(count / maxKw) * 100}%` }}
                  />
                </div>
                <span className="bar-count">{count}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Top Bible books */}
        <div className="stats-panel">
          <h2 className="stats-panel-title">Most Referenced Bible Books</h2>
          <div className="bar-chart">
            {topBooks.slice(0, 20).map(({ book, count }) => (
              <div key={book} className="bar-row">
                <span className="bar-label">{book}</span>
                <div className="bar-track">
                  <div
                    className="bar-fill bar-fill-rust"
                    style={{ width: `${(count / maxBook) * 100}%` }}
                  />
                </div>
                <span className="bar-count">{count}</span>
              </div>
            ))}
          </div>
        </div>

      </div>
    </div>
  );
}

function StatCard({ icon, value, label }) {
  return (
    <div className="stat-card">
      <span className="stat-card-icon">{icon}</span>
      <span className="stat-card-value">{value ?? "—"}</span>
      <span className="stat-card-label">{label}</span>
    </div>
  );
}
