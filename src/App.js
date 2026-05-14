// src/App.js
import React, { useState, useEffect } from "react";
import { HashRouter, Routes, Route, Navigate } from "react-router-dom";
import { getPastors } from "./lib/firebase";
import { useTheme } from "./hooks/useTheme";
import Header from "./components/Header";
import LibraryPage from "./pages/LibraryPage";
import SermonPage from "./pages/SermonPage";
import AskPage from "./pages/AskPage";
import StatsPage from "./pages/StatsPage";
import "./styles/globals.css";
import "./App.css";

export default function App() {
  const [pastors,      setPastors]      = useState([]);
  const [activePastor, setActivePastor] = useState(null);
  const [loading,      setLoading]      = useState(true);
  const [error,        setError]        = useState(null);
  const { theme, setTheme, toggle }     = useTheme();

  useEffect(() => {
    getPastors()
      .then(list => { setPastors(list); setActivePastor(list[0] || null); })
      .catch(e  => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return (
    <div className="fullscreen-center">
      <div className="spinner" />
      <p style={{ marginTop: "1rem", fontFamily: "var(--font-serif)", color: "var(--color-text-muted)", fontSize: "1.1rem" }}>
        Loading the collection…
      </p>
    </div>
  );

  return (
    <HashRouter>
      <div className="app-shell">
        <Header
          pastors={pastors}
          activePastor={activePastor}
          onPastorChange={setActivePastor}
          theme={theme}
          setTheme={setTheme}
          onThemeToggle={toggle}
        />

        {error ? (
          <div className="fullscreen-center">
            <h2 style={{ fontFamily: "var(--font-serif)" }}>Connection Error</h2>
            <p style={{ color: "var(--color-text-muted)", marginTop: "0.5rem" }}>{error}</p>
          </div>
        ) : (
          <main className="app-main">
            <Routes>
              <Route path="/" element={
                pastors.length === 0
                  ? <EmptyState />
                  : <Navigate to="/library" replace />
              } />
              <Route path="/library"    element={<LibraryPage pastor={activePastor} />} />
              <Route path="/sermon/:id" element={<SermonPage  pastor={activePastor} />} />
              <Route path="/ask"        element={<AskPage     pastor={activePastor} />} />
              <Route path="/stats"      element={<StatsPage   pastor={activePastor} />} />
            </Routes>
          </main>
        )}
      </div>
    </HashRouter>
  );
}

function EmptyState() {
  return (
    <div className="fullscreen-center">
      <div style={{ textAlign: "center", maxWidth: 480 }}>
        <div style={{ fontSize: "3rem", marginBottom: "1rem" }}>📖</div>
        <h2 style={{ fontFamily: "var(--font-serif)", marginBottom: "0.75rem" }}>No Collections Yet</h2>
        <p style={{ color: "var(--color-text-muted)" }}>
          Run the Python ingestion script to load sermons into the database, then refresh this page.
        </p>
      </div>
    </div>
  );
}
