// src/App.js
import React, { useState, useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { getPastors } from "./lib/firebase";
import Header from "./components/Header";
import Sidebar from "./components/Sidebar";
import LibraryPage from "./pages/LibraryPage";
import SermonPage from "./pages/SermonPage";
import AskPage from "./pages/AskPage";
import StatsPage from "./pages/StatsPage";
import "./styles/globals.css";
import "./App.css";

export default function App() {
  const [pastors, setPastors]         = useState([]);
  const [activePastor, setActivePastor] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [loading, setLoading]         = useState(true);
  const [error, setError]             = useState(null);

  useEffect(() => {
    getPastors()
      .then((list) => {
        setPastors(list);
        setActivePastor(list[0] || null);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingScreen />;
  if (error)   return <ErrorScreen message={error} />;
  if (!pastors.length) return <EmptyScreen />;

  return (
    <BrowserRouter>
      <div className="app-shell">
        <Header
          pastors={pastors}
          activePastor={activePastor}
          onPastorChange={setActivePastor}
          onMenuToggle={() => setSidebarOpen(o => !o)}
        />
        <div className="app-body">
          <Sidebar
            open={sidebarOpen}
            onClose={() => setSidebarOpen(false)}
            activePastor={activePastor}
          />
          <main className="app-main">
            <Routes>
              <Route path="/"         element={<Navigate to="/library" replace />} />
              <Route path="/library"  element={<LibraryPage pastor={activePastor} />} />
              <Route path="/sermon/:id" element={<SermonPage pastor={activePastor} />} />
              <Route path="/ask"      element={<AskPage pastor={activePastor} />} />
              <Route path="/stats"    element={<StatsPage pastor={activePastor} />} />
            </Routes>
          </main>
        </div>
      </div>
    </BrowserRouter>
  );
}

function LoadingScreen() {
  return (
    <div className="fullscreen-center">
      <div className="spinner" />
      <p style={{ marginTop: "1rem", fontFamily: "var(--font-serif)", fontSize: "1.2rem", color: "var(--muted)" }}>
        Loading the collection…
      </p>
    </div>
  );
}

function ErrorScreen({ message }) {
  return (
    <div className="fullscreen-center">
      <div style={{ textAlign: "center", maxWidth: 400 }}>
        <h2 style={{ fontFamily: "var(--font-serif)", marginBottom: "0.5rem" }}>Connection Error</h2>
        <p style={{ color: "var(--muted)" }}>{message}</p>
        <p style={{ marginTop: "1rem", fontSize: "0.9rem", color: "var(--muted)" }}>
          Check your Firebase configuration and internet connection.
        </p>
      </div>
    </div>
  );
}

function EmptyScreen() {
  return (
    <div className="fullscreen-center">
      <div style={{ textAlign: "center", maxWidth: 500 }}>
        <div style={{ fontSize: "3rem", marginBottom: "1rem" }}>📖</div>
        <h2 style={{ fontFamily: "var(--font-serif)", marginBottom: "0.5rem" }}>No Collections Yet</h2>
        <p style={{ color: "var(--muted)" }}>
          Run the Python ingestion script to load sermons into the database,
          then refresh this page.
        </p>
      </div>
    </div>
  );
}
