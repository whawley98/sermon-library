// src/components/Header.js
import React from "react";
import { NavLink } from "react-router-dom";
import "./Header.css";

export default function Header({ pastors, activePastor, onPastorChange, theme, onThemeToggle }) {
  return (
    <header className="header no-print">
      <div className="header-left">
        <div className="header-brand">
          <span className="brand-icon">✦</span>
          <div>
            <div className="brand-title">Sermon Library</div>
            {activePastor && <div className="brand-sub">{activePastor.name}</div>}
          </div>
        </div>
      </div>

      <nav className="header-nav">
        <NavLink to="/library" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
          📚 Library
        </NavLink>
        <NavLink to="/ask" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
          💬 Ask
        </NavLink>
        <NavLink to="/stats" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
          📊 Insights
        </NavLink>
      </nav>

      <div className="header-right">
        {pastors.length > 1 && (
          <select
            className="pastor-select"
            value={activePastor?.id || ""}
            onChange={(e) => {
              const p = pastors.find((x) => x.id === e.target.value);
              if (p) onPastorChange(p);
            }}
          >
            {pastors.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        )}
        <button
          className="theme-btn"
          onClick={onThemeToggle}
          aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          title={theme === "dark" ? "Light mode" : "Dark mode"}
        >
          {theme === "dark" ? "☀️" : "🌙"}
        </button>
      </div>
    </header>
  );
}
