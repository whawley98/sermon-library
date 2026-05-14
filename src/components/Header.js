// src/components/Header.js
// Platform header with multi-pastor support, 4-theme selector, and nav.

import React, { useState } from "react";
import { NavLink } from "react-router-dom";
import "./Header.css";

const THEME_OPTIONS = [
  { value: "light",    label: "Light",         icon: "☀️" },
  { value: "dark",     label: "Dark",          icon: "🌙" },
  { value: "warm",     label: "Warm",          icon: "🕯️" },
  { value: "contrast", label: "High Contrast", icon: "◑"  },
];

export default function Header({
  pastors      = [],
  activePastor = null,
  onPastorChange,
  theme        = "light",
  setTheme,
  onThemeToggle,   // legacy support
}) {
  const [themeMenuOpen, setThemeMenuOpen] = useState(false);

  const handleThemeSelect = (t) => {
    if (setTheme) setTheme(t);
    else if (onThemeToggle) onThemeToggle();
    setThemeMenuOpen(false);
  };

  const currentTheme = THEME_OPTIONS.find(t => t.value === theme) || THEME_OPTIONS[0];

  return (
    <header className="header no-print">
      {/* Brand */}
      <div className="header-brand">
        <span className="brand-mark" aria-hidden="true">✦</span>
        <div className="brand-text">
          <span className="brand-name">Sermon Library</span>
          {activePastor && (
            <span className="brand-pastor">{activePastor.name}</span>
          )}
        </div>
      </div>

      {/* Nav */}
      <nav className="header-nav" aria-label="Main navigation">
        <NavLink
          to="/library"
          className={({ isActive }) => `nav-link${isActive ? " nav-link--active" : ""}`}
        >
          Library
        </NavLink>
        <NavLink
          to="/ask"
          className={({ isActive }) => `nav-link${isActive ? " nav-link--active" : ""}`}
        >
          Ask
        </NavLink>
        <NavLink
          to="/stats"
          className={({ isActive }) => `nav-link${isActive ? " nav-link--active" : ""}`}
        >
          Insights
        </NavLink>
      </nav>

      {/* Right controls */}
      <div className="header-controls">
        {/* Pastor selector — only shown when multiple pastors exist */}
        {pastors.length > 1 && (
          <select
            className="pastor-select"
            value={activePastor?.id || ""}
            onChange={(e) => {
              const p = pastors.find(x => x.id === e.target.value);
              if (p && onPastorChange) onPastorChange(p);
            }}
            aria-label="Select pastor collection"
          >
            {pastors.map(p => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        )}

        {/* Theme selector */}
        <div className="theme-menu-wrap">
          <button
            className="theme-btn"
            onClick={() => setThemeMenuOpen(v => !v)}
            aria-label="Change theme"
            aria-expanded={themeMenuOpen}
          >
            <span className="theme-btn-icon">{currentTheme.icon}</span>
          </button>

          {themeMenuOpen && (
            <>
              {/* Backdrop */}
              <div
                className="theme-backdrop"
                onClick={() => setThemeMenuOpen(false)}
              />
              <div className="theme-menu" role="menu">
                <div className="theme-menu-label">Theme</div>
                {THEME_OPTIONS.map(opt => (
                  <button
                    key={opt.value}
                    className={`theme-option${theme === opt.value ? " theme-option--active" : ""}`}
                    onClick={() => handleThemeSelect(opt.value)}
                    role="menuitem"
                  >
                    <span className="theme-option-icon">{opt.icon}</span>
                    <span className="theme-option-label">{opt.label}</span>
                    {theme === opt.value && <span className="theme-option-check">✓</span>}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
