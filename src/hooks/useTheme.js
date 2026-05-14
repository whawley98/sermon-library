// src/hooks/useTheme.js
// Manages 4 themes: light, dark, warm, contrast
// Persists choice in localStorage, applies data-theme attribute to <html>

import { useState, useEffect } from "react";

const THEMES      = ["light", "dark", "warm", "contrast"];
const STORAGE_KEY = "sermon-library-theme";
const DEFAULT     = "light";

export function useTheme() {
  const [theme, setTheme] = useState(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    return THEMES.includes(saved) ? saved : DEFAULT;
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem(STORAGE_KEY, theme);
  }, [theme]);

  const setThemeSafe = (t) => {
    if (THEMES.includes(t)) setTheme(t);
  };

  // Legacy toggle support (light ↔ dark) for any code using the old API
  const toggle = () => {
    setTheme(prev => prev === "dark" ? "light" : "dark");
  };

  return { theme, setTheme: setThemeSafe, toggle, themes: THEMES };
}
