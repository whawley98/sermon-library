// src/pages/LibraryPage.js
import React, { useState, useEffect, useCallback, useRef } from "react";
import { getSermons, searchSermonsByTitle } from "../lib/firebase";
import Sidebar from "../components/Sidebar";
import SermonCard from "../components/SermonCard";
import "./LibraryPage.css";

const PAGE_SIZE = 24;

export default function LibraryPage({ pastor }) {
  const [sermons,    setSermons]    = useState([]);
  const [loading,    setLoading]    = useState(true);
  const [loadingMore,setLoadingMore]= useState(false);
  const [lastDoc,    setLastDoc]    = useState(null);
  const [hasMore,    setHasMore]    = useState(false);
  const [view,       setView]       = useState("grid");
  const [sort,       setSort]       = useState("title");
  const [search,     setSearch]     = useState("");
  const [filters,    setFilters]    = useState({ author: null, book: null, keyword: null });
  const searchTimer = useRef(null);

  const load = useCallback(async (reset = true) => {
    if (!pastor?.id) return;
    reset ? setLoading(true) : setLoadingMore(true);

    try {
      const params = {
        pastorId:   pastor.id,
        keyword:    filters.keyword,
        book:       filters.book,
        authorName: filters.author === "hawley" ? pastor.name : filters.author === "other" ? "__other__" : null,
        pageSize:   PAGE_SIZE,
        lastDoc:    reset ? null : lastDoc,
      };

      let result;
      if (search.trim().length >= 2) {
        const found = await searchSermonsByTitle(search.trim(), pastor.id);
        result = { sermons: found, lastDoc: null, hasMore: false };
      } else {
        result = await getSermons(params);
      }

      setSermons(prev => reset ? result.sermons : [...prev, ...result.sermons]);
      setLastDoc(result.lastDoc);
      setHasMore(result.hasMore);
    } catch (e) {
      console.error("Failed to load sermons:", e);
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [pastor?.id, pastor?.name, filters, search, lastDoc]);

  // Reload when pastor or filters change
  useEffect(() => { load(true); }, [pastor?.id, filters]);

  // Debounce search
  useEffect(() => {
    clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => load(true), 350);
    return () => clearTimeout(searchTimer.current);
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
              placeholder="Search by title…  (press / to focus)"
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

            <select
              className="input sort-select"
              value={sort}
              onChange={e => setSort(e.target.value)}
            >
              <option value="title">A – Z</option>
              <option value="title_desc">Z – A</option>
              <option value="date">Date</option>
            </select>

            <div className="view-toggle">
              <button
                className={`view-btn ${view === "grid" ? "active" : ""}`}
                onClick={() => setView("grid")}
                title="Grid view"
              >⊞</button>
              <button
                className={`view-btn ${view === "list" ? "active" : ""}`}
                onClick={() => setView("list")}
                title="List view"
              >☰</button>
            </div>
          </div>
        </div>

        {/* Active filter chips */}
        {activeFilterCount > 0 && (
          <div className="active-chips">
            {filters.keyword && (
              <FilterChip label={`Topic: ${filters.keyword}`} onRemove={() => handleFilterChange({ keyword: null })} />
            )}
            {filters.book && (
              <FilterChip label={`Book: ${filters.book}`} onRemove={() => handleFilterChange({ book: null })} />
            )}
            {filters.author && (
              <FilterChip label={`Author: ${filters.author === "hawley" ? pastor?.name : "Other Preachers"}`} onRemove={() => handleFilterChange({ author: null })} />
            )}
          </div>
        )}

        {/* Results count */}
        {!loading && (
          <p className="result-count">
            {sermons.length > 0
              ? `${sermons.length}${hasMore ? "+" : ""} sermon${sermons.length !== 1 ? "s" : ""}`
              : "No sermons found"}
          </p>
        )}

        {/* Grid / List */}
        {loading ? (
          <div className="grid-loading">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="skeleton-card" />
            ))}
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
              {sermons.map(s => (
                <SermonCard key={s.id} sermon={s} view={view} />
              ))}
            </div>

            {hasMore && (
              <div className="load-more">
                <button
                  className="btn btn-secondary"
                  onClick={() => load(false)}
                  disabled={loadingMore}
                >
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
