// src/App.js
import React, { useState, useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { getPastors } from "./lib/firebase";
import { useTheme } from "./hooks/useTheme";
import Header from "./components/Header";
import Sidebar from "./components/Sidebar";
import LibraryPage from "./pages/LibraryPage";
import SermonPage from "./pages/SermonPage";
import AskPage from "./pages/AskPage";
import StatsPage from "./pages/StatsPage";
import "./styles/globals.css";
import "./App.css";

export default function App() {
  const [pastors, setPastors]           = useState([]);
  const [activePastor, setActivePastor] = useState(null);
  const [sidebarOpen, setSidebarOpen]   = useState(false);
  const [loading, setLoading]           = useState(true);
  const [error, setError]               = useState(null);
  const { theme, toggle: toggleTheme }  = useTheme();

  useEffect(() => {
    getPastors()
      .then((list) => {
        setPastors(list);
        setActivePastor(list[0] || null);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  // Always render the shell so header + toggle are always visible
  return (
    <BrowserRouter>
      <div className="app-shell">
        <Header
          pastors={pastors}
          activePastor={activePastor}
          onPastorChange={setActivePastor}
          onMenuToggle={() => setSidebarOpen(o => !o)}
          theme={theme}
          onThemeToggle={toggleTheme}
        />

        {loading ? (
          <div className="fullscreen-center">
            <div className="spinner" />
            <p style={{ marginTop: "1rem", fontFamily: "var(--font-serif)", fontSize: "1.2rem", color: "var(--color-text-muted)" }}>
              Loading the collection…
            </p>
          </div>

        ) : error ? (
          <div className="fullscreen-center">
            <div style={{ textAlign: "center", maxWidth: 400 }}>
              <h2 style={{ marginBottom: "0.5rem" }}>Connection Error</h2>
              <p>{error}</p>
              <p style={{ marginTop: "1rem", fontSize: "0.9rem", color: "var(--color-text-muted)" }}>
                Check your Firebase configuration and internet connection.
              </p>
            </div>
          </div>

        ) : !pastors.length ? (
          <div className="fullscreen-center">
            <div style={{ textAlign: "center", maxWidth: 500 }}>
              <div style={{ fontSize: "3rem", marginBottom: "1rem" }}>📖</div>
              <h2 style={{ marginBottom: "0.5rem" }}>No Collections Yet</h2>
              <p>Run the Python ingestion script to load sermons into the database, then refresh this page.</p>
            </div>
          </div>

        ) : (
          <div className="app-body">
            <Sidebar
              open={sidebarOpen}
              onClose={() => setSidebarOpen(false)}
              activePastor={activePastor}
            />
            <main className="app-main">
              <Routes>
                <Route path="/"           element={<Navigate to="/library" replace />} />
                <Route path="/library"    element={<LibraryPage pastor={activePastor} />} />
                <Route path="/sermon/:id" element={<SermonPage pastor={activePastor} />} />
                <Route path="/ask"        element={<AskPage pastor={activePastor} />} />
                <Route path="/stats"      element={<StatsPage pastor={activePastor} />} />
              </Routes>
            </main>
          </div>
        )}
      </div>
    </BrowserRouter>
  );
}
