// src/pages/LibraryPage.js
// Main sermon browsing page with Algolia search, sidebar filters,
// grid/list toggle, pagination, and result counts.

import React, { useState, useEffect, useCallback, useRef } from "react";
import Sidebar from "../components/Sidebar";
import SermonCard from "../components/SermonCard";
import { getSermons, searchSermons } from "../lib/firebase";
import "./LibraryPage.css";

const PAGE_SIZE = 24;

export default function LibraryPage({ pastor }) {
  const [sermons,    setSermons]    = useState([]);
  const [loading,    setLoading]    = useState(true);
  const [loadingMore,setLoadingMore]= useState(false);
  const [hasMore,    setHasMore]    = useState(false);
  const [lastDoc,    setLastDoc]    = useState(null);
  const [total,      setTotal]      = useState(null);
  const [view,       setView]       = useState("grid"); // "grid" | "list"
  const [searchText, setSearchText] = useState("");
  const [isSearching,setIsSearching]= useState(false);
  const [filters,    setFilters]    = useState({
    isPrimary: null,
    book:      null,
    keyword:   null,
  });

  const searchTimer  = useRef(null);
  const isFiltered   = filters.isPrimary !== null || filters.book || filters.keyword;
  const isSearchMode = searchText.trim().length >= 2;

  // ── Fetch sermons ────────────────────────────────────────────────────────
  const fetchSermons = useCallback(async (reset = true) => {
    if (!pastor?.id) return;

    if (reset) setLoading(true);
    else       setLoadingMore(true);

    try {
      const result = await getSermons({
        pastorId:  pastor.id,
        keyword:   filters.keyword,
        book:      filters.book,
        isPrimary: filters.isPrimary,
        pageSize:  PAGE_SIZE,
        lastDoc:   reset ? null : lastDoc,
      });

      if (reset) {
        setSermons(result.sermons);
        setLastDoc(result.lastDoc);
      } else {
        setSermons(prev => [...prev, ...result.sermons]);
        setLastDoc(result.lastDoc);
      }
      setHasMore(result.hasMore);
    } catch (err) {
      console.error("Failed to load sermons:", err);
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [pastor?.id, filters, lastDoc]);

  // ── Search ───────────────────────────────────────────────────────────────
  const doSearch = useCallback(async (text) => {
    if (!pastor?.id || text.trim().length < 2) return;
    setIsSearching(true);
    try {
      const results = await searchSermons(text, pastor.id, 50);
      setSermons(results);
      setTotal(results.length);
      setHasMore(false);
    } catch (err) {
      console.error("Search failed:", err);
    } finally {
      setIsSearching(false);
    }
  }, [pastor?.id]);

  // ── Effects ──────────────────────────────────────────────────────────────
  // Load on mount and filter changes
  useEffect(() => {
    if (!isSearchMode) {
      fetchSermons(true);
      setTotal(null);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pastor?.id, filters]);

  // Debounced search
  useEffect(() => {
    if (searchText.trim().length < 2) {
      if (searchText.trim().length === 0) {
        fetchSermons(true);
        setTotal(null);
      }
      return;
    }
    clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => doSearch(searchText), 350);
    return () => clearTimeout(searchTimer.current);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchText]);

  // ── Handlers ─────────────────────────────────────────────────────────────
  const handleFilterChange = (updates) => {
    setFilters(prev => ({ ...prev, ...updates }));
    setSearchText("");
  };

  const handleLoadMore = () => {
    if (!loadingMore && hasMore) fetchSermons(false);
  };

  // ── Render ────────────────────────────────────────────────────────────────
  const resultCount = total ?? sermons.length;
  const showCount   = !loading && sermons.length > 0;

  return (
    <div className="library-layout">
      <Sidebar
        activePastor={pastor}
        filters={filters}
        onFilterChange={handleFilterChange}
      />

      <div className="library-main">
        {/* Toolbar */}
        <div className="library-toolbar">
          <div className="search-wrap">
            <span className="search-icon">🔍</span>
            <input
              className="search-input"
              type="search"
              placeholder="Search sermons…"
              value={searchText}
              onChange={e => setSearchText(e.target.value)}
              aria-label="Search sermons"
            />
            {(isSearching) && <span className="search-spinner" />}
          </div>

          <div className="toolbar-right">
            {showCount && (
              <span className="result-count">
                {isSearchMode
                  ? `${resultCount} result${resultCount !== 1 ? "s" : ""}`
                  : isFiltered
                    ? `${sermons.length} shown`
                    : `${sermons.length} sermons`}
              </span>
            )}

            <div className="view-toggle" role="group" aria-label="View mode">
              <button
                className={`view-btn${view === "grid" ? " view-btn--active" : ""}`}
                onClick={() => setView("grid")}
                aria-label="Grid view"
              >
                ⊞
              </button>
              <button
                className={`view-btn${view === "list" ? " view-btn--active" : ""}`}
                onClick={() => setView("list")}
                aria-label="List view"
              >
                ☰
              </button>
            </div>
          </div>
        </div>

        {/* Active filter chips */}
        {(isFiltered || isSearchMode) && (
          <div className="active-filters">
            {isSearchMode && (
              <span className="filter-chip filter-chip--search">
                🔍 "{searchText}"
                <button onClick={() => setSearchText("")}>✕</button>
              </span>
            )}
            {filters.book && (
              <span className="filter-chip">
                📖 {filters.book}
                <button onClick={() => handleFilterChange({ book: null })}>✕</button>
              </span>
            )}
            {filters.keyword && (
              <span className="filter-chip">
                🏷 {filters.keyword}
                <button onClick={() => handleFilterChange({ keyword: null })}>✕</button>
              </span>
            )}
            {filters.isPrimary !== null && (
              <span className="filter-chip">
                👤 {filters.isPrimary ? "Primary pastor" : "Guest preachers"}
                <button onClick={() => handleFilterChange({ isPrimary: null })}>✕</button>
              </span>
            )}
          </div>
        )}

        {/* Content */}
        {loading ? (
          <div className="library-loading">
            {[...Array(8)].map((_, i) => (
              <div key={i} className="skeleton" style={{ height: view === "grid" ? 220 : 72, borderRadius: 12 }} />
            ))}
          </div>
        ) : sermons.length === 0 ? (
          <div className="library-empty">
            <div className="empty-icon">📭</div>
            <h3>No sermons found</h3>
            <p>
              {isSearchMode
                ? `No results for "${searchText}". Try different keywords.`
                : "Try adjusting your filters."}
            </p>
          </div>
        ) : (
          <>
            <div className={view === "grid" ? "sermon-grid" : "sermon-list"}>
              {sermons.map(s => (
                <SermonCard key={s.id} sermon={s} view={view} />
              ))}
            </div>

            {/* Load more */}
            {hasMore && !isSearchMode && (
              <div className="load-more-wrap">
                <button
                  className="btn btn-secondary load-more-btn"
                  onClick={handleLoadMore}
                  disabled={loadingMore}
                >
                  {loadingMore ? (
                    <><span className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} /> Loading…</>
                  ) : "Load more sermons"}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
