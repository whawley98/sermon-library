// src/pages/LibraryPage.js
import React, { useState, useEffect, useRef } from "react";
import { getSermons, searchSermonsByTitle } from "../lib/firebase";
import Sidebar from "../components/Sidebar";
import SermonCard from "../components/SermonCard";
import "./LibraryPage.css";

const PAGE_SIZE = 24;

export default function LibraryPage({ pastor }) {
  const [sermons,     setSermons]     = useState([]);
  const [loading,     setLoading]     = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [lastDoc,     setLastDoc]     = useState(null);
  const [hasMore,     setHasMore]     = useState(false);
  const [error,       setError]       = useState(null);
  const [view,        setView]        = useState("grid");
  const [search,      setSearch]      = useState("");
  const [filters,     setFilters]     = useState({ author: null, book: null, keyword: null });
  const searchTimer = useRef(null);
  const prevFilters = useRef(filters);

  const load = async (reset = true) => {
    if (!pastor?.id) return;
    reset ? setLoading(true) : setLoadingMore(true);
    setError(null);

    try {
      let result;
      if (search.trim().length >= 2) {
        const found = await searchSermonsByTitle(search.trim(), pastor.id);
        result = { sermons: found, lastDoc: null, hasMore: false };
      } else {
        // Convert author filter to isPrimary boolean
        let isPrimary = null;
        if (filters.author === "hawley") isPrimary = true;
        if (filters.author === "other")  isPrimary = false;

        result = await getSermons({
          pastorId:  pastor.id,
          keyword:   filters.keyword || null,
          book:      filters.book    || null,
          isPrimary,
          pageSize:  PAGE_SIZE,
          lastDoc:   reset ? null : lastDoc,
        });
      }
      setSermons(prev => reset ? result.sermons : [...prev, ...result.sermons]);
      setLastDoc(result.lastDoc);
      setHasMore(result.hasMore);
    } catch (e) {
      console.error("Failed to load sermons:", e);
      setError(e.message);
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  };

  // Load when pastor changes
  useEffect(() => {
    load(true);
  // eslint-disable-next-line
  }, [pastor?.id]);

  // Load when filters change
  useEffect(() => {
    if (prevFilters.current !== filters) {
      prevFilters.current = filters;
      load(true);
    }
  // eslint-disable-next-line
  }, [filters]);

  // Debounce search
  useEffect(() => {
    clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => load(true), 400);
    return () => clearTimeout(searchTimer.current);
  // eslint-disable-next-line
  }, [search]);

  const handleFilterChange = (updates) => {
    setFilters(prev => ({ ...prev, ...updates }));
  };

  const activeFilterCount = Object.values(filters).filter(Boolean).length;

  return (
    <div className="library-layout">
      <Sidebar
        activePastor={pastor}
        filters={filters}
        onFilterChange={handleFilterChange}
      />

      <div className="library-content">
        {/* Toolbar */}
        <div className="toolbar">
          <div className="search-wrap">
            <span className="search-icon">⌕</span>
            <input
              className="input search-input"
              type="text"
              placeholder="Search by title…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              onKeyDown={e => e.key === "Escape" && setSearch("")}
            />
            {search && (
              <button className="search-clear" onClick={() => setSearch("")}>×</button>
            )}
          </div>

          <div className="toolbar-right">
            {activeFilterCount > 0 && (
              <button
                className="btn btn-ghost"
                onClick={() => setFilters({ author: null, book: null, keyword: null })}
              >
                ✕ Clear {activeFilterCount} filter{activeFilterCount > 1 ? "s" : ""}
              </button>
            )}
            <div className="view-toggle">
              <button className={`view-btn ${view === "grid" ? "active" : ""}`} onClick={() => setView("grid")}>⊞</button>
              <button className={`view-btn ${view === "list" ? "active" : ""}`} onClick={() => setView("list")}>☰</button>
            </div>
          </div>
        </div>

        {/* Active filter chips */}
        {activeFilterCount > 0 && (
          <div className="active-chips">
            {filters.keyword && <FilterChip label={`Topic: ${filters.keyword}`}  onRemove={() => handleFilterChange({ keyword: null })} />}
            {filters.book    && <FilterChip label={`Book: ${filters.book}`}      onRemove={() => handleFilterChange({ book: null })} />}
            {filters.author  && <FilterChip label={`Author: ${filters.author === "hawley" ? pastor?.name : "Other Preachers"}`} onRemove={() => handleFilterChange({ author: null })} />}
          </div>
        )}

        {!loading && !error && (
          <p className="result-count">
            {sermons.length > 0
              ? `${sermons.length}${hasMore ? "+" : ""} sermon${sermons.length !== 1 ? "s" : ""}`
              : "No sermons found"}
          </p>
        )}

        {loading ? (
          <div className="grid-loading">
            {Array.from({ length: 8 }).map((_, i) => <div key={i} className="skeleton-card" />)}
          </div>
        ) : error ? (
          <div className="error-state">
            ⚠️ {error}
            <br /><small>Check browser console for details.</small>
          </div>
        ) : sermons.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">🕊️</div>
            <h3>No sermons found</h3>
            <p>Try adjusting your search or filters.</p>
          </div>
        ) : (
          <>
            <div className={view === "grid" ? "sermon-grid" : "sermon-list"}>
              {sermons.map(s => <SermonCard key={s.id} sermon={s} view={view} />)}
            </div>
            {hasMore && (
              <div className="load-more">
                <button className="btn btn-secondary" onClick={() => load(false)} disabled={loadingMore}>
                  {loadingMore ? "Loading…" : "Load more sermons"}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function FilterChip({ label, onRemove }) {
  return (
    <div className="filter-chip">
      {label}
      <button onClick={onRemove}>×</button>
    </div>
  );
}
