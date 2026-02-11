// ui/src/pages/AdminRSSIntel.tsx
// Admin page for browsing enriched RSS articles from intel-redis

import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";

interface Article {
  uid: string;
  title: string;
  url: string | null;
  source: string | null;
  category: string | null;
  summary: string | null;
  sentiment: string | null;
  quality_score: number;
  relevance: number;
  urgency: number;
  total_score: number;
  impact: string;
  entities: string[] | null;
  tickers: string[] | null;
  takeaways: string[] | null;
  enriched_ts: number;
  published_ts: number;
  age_minutes: number | null;
}

type SortKey = "total_score" | "relevance" | "urgency" | "quality_score" | "age_minutes";
type SortDir = "asc" | "desc";

const CATEGORY_COLORS: Record<string, { bg: string; color: string }> = {
  macro: { bg: "rgba(59, 130, 246, 0.15)", color: "#60a5fa" },
  earnings: { bg: "rgba(34, 197, 94, 0.15)", color: "#22c55e" },
  fed: { bg: "rgba(249, 115, 22, 0.15)", color: "#f97316" },
  geopolitical: { bg: "rgba(239, 68, 68, 0.15)", color: "#ef4444" },
  crypto: { bg: "rgba(168, 85, 247, 0.15)", color: "#c084fc" },
  commodities: { bg: "rgba(234, 179, 8, 0.15)", color: "#eab308" },
  tech: { bg: "rgba(34, 211, 238, 0.15)", color: "#22d3ee" },
  bonds: { bg: "rgba(156, 163, 175, 0.15)", color: "#9ca3af" },
  options: { bg: "rgba(124, 58, 237, 0.15)", color: "#a78bfa" },
  volatility: { bg: "rgba(244, 63, 94, 0.15)", color: "#fb7185" },
};

function getCategoryStyle(category: string | null) {
  if (!category) return { bg: "rgba(156, 163, 175, 0.15)", color: "#9ca3af" };
  return CATEGORY_COLORS[category.toLowerCase()] || { bg: "rgba(156, 163, 175, 0.15)", color: "#9ca3af" };
}

function formatAge(minutes: number | null): string {
  if (minutes === null) return "—";
  if (minutes < 60) return `${minutes}m`;
  if (minutes < 1440) return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
  return `${Math.floor(minutes / 1440)}d ${Math.floor((minutes % 1440) / 60)}h`;
}

function sentimentColor(sentiment: string | null): string {
  if (!sentiment) return "var(--text-secondary)";
  const s = sentiment.toLowerCase();
  if (s === "bullish" || s === "positive") return "#22c55e";
  if (s === "bearish" || s === "negative") return "#ef4444";
  return "var(--text-secondary)";
}

export default function AdminRSSIntelPage() {
  const navigate = useNavigate();
  const [articles, setArticles] = useState<Article[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedUid, setExpandedUid] = useState<string | null>(null);
  const [hours, setHours] = useState(24);
  const [sortKey, setSortKey] = useState<SortKey>("total_score");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const fetchArticles = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/admin/rss-articles?hours=${hours}&limit=200`, {
        credentials: "include",
      });
      if (!res.ok) throw new Error("Failed to load articles");
      const data = await res.json();
      setArticles(data.articles || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [hours]);

  useEffect(() => {
    fetchArticles();
  }, [fetchArticles]);

  const toggleExpand = (uid: string) => {
    setExpandedUid((prev) => (prev === uid ? null : uid));
  };

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  const sortedArticles = [...articles].sort((a, b) => {
    const av = a[sortKey] ?? 0;
    const bv = b[sortKey] ?? 0;
    return sortDir === "desc" ? (bv as number) - (av as number) : (av as number) - (bv as number);
  });

  if (loading) {
    return (
      <div className="admin-page">
        <div className="admin-loading">Loading...</div>
        <style>{styles}</style>
      </div>
    );
  }

  if (error) {
    return (
      <div className="admin-page">
        <div className="admin-error">
          <h2>Error</h2>
          <p>{error}</p>
          <button onClick={() => navigate("/admin")}>Back to Admin</button>
        </div>
        <style>{styles}</style>
      </div>
    );
  }

  return (
    <div className="admin-page">
      <div className="admin-container">
        {/* Header */}
        <div className="admin-header">
          <div className="header-left">
            <button className="back-btn" onClick={() => navigate("/admin")}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M19 12H5M12 19l-7-7 7-7" />
              </svg>
              Admin
            </button>
            <h1>RSS Intel Review</h1>
            <span className="article-count">{articles.length} articles in last {hours}h</span>
          </div>
          <div className="header-controls">
            <select
              className="hours-select"
              value={hours}
              onChange={(e) => setHours(Number(e.target.value))}
            >
              <option value={6}>6 hours</option>
              <option value={12}>12 hours</option>
              <option value={24}>24 hours</option>
              <option value={48}>48 hours</option>
              <option value={72}>72 hours</option>
            </select>
            <button className="refresh-btn" onClick={fetchArticles}>Refresh</button>
          </div>
        </div>

        {/* Table */}
        <div className="rss-table-container">
          <table className="rss-table">
            <thead>
              <tr>
                <th style={{ width: "60px" }}>Age</th>
                <th style={{ width: "90px" }}>Category</th>
                <th className="sortable-th" style={{ width: "40px" }} onClick={() => toggleSort("relevance")}>
                  Rel{sortKey === "relevance" ? (sortDir === "desc" ? " ▼" : " ▲") : ""}
                </th>
                <th className="sortable-th" style={{ width: "40px" }} onClick={() => toggleSort("urgency")}>
                  Urg{sortKey === "urgency" ? (sortDir === "desc" ? " ▼" : " ▲") : ""}
                </th>
                <th className="sortable-th" style={{ width: "40px" }} onClick={() => toggleSort("total_score")}>
                  Tot{sortKey === "total_score" ? (sortDir === "desc" ? " ▼" : " ▲") : ""}
                </th>
                <th style={{ width: "72px" }}>Impact</th>
                <th className="sortable-th" style={{ width: "50px" }} onClick={() => toggleSort("quality_score")}>
                  Qual{sortKey === "quality_score" ? (sortDir === "desc" ? " ▼" : " ▲") : ""}
                </th>
                <th style={{ width: "80px" }}>Sentiment</th>
                <th>Title</th>
                <th style={{ width: "120px" }}>Entities</th>
                <th style={{ width: "80px" }}>Tickers</th>
              </tr>
            </thead>
            <tbody>
              {sortedArticles.map((article) => {
                const catStyle = getCategoryStyle(article.category);
                const isExpanded = expandedUid === article.uid;
                return (
                  <tr key={article.uid} className="article-row-group">
                    <td colSpan={11} style={{ padding: 0, border: "none" }}>
                      <div
                        className={`article-row ${isExpanded ? "expanded" : ""}`}
                        onClick={() => toggleExpand(article.uid)}
                      >
                        <div className="cell cell-age">{formatAge(article.age_minutes)}</div>
                        <div className="cell cell-category">
                          <span
                            className="category-badge"
                            style={{ background: catStyle.bg, color: catStyle.color }}
                          >
                            {article.category || "unknown"}
                          </span>
                        </div>
                        <div className="cell cell-score">
                          <span className={`score-num ${article.relevance >= 4 ? "high" : article.relevance >= 2 ? "mid" : "low"}`}>
                            {article.relevance}
                          </span>
                        </div>
                        <div className="cell cell-score">
                          <span className={`score-num ${article.urgency >= 4 ? "high" : article.urgency >= 2 ? "mid" : "low"}`}>
                            {article.urgency}
                          </span>
                        </div>
                        <div className="cell cell-score">
                          <span className={`score-num total ${article.total_score >= 7 ? "high" : article.total_score >= 4 ? "mid" : "low"}`}>
                            {article.total_score}
                          </span>
                        </div>
                        <div className="cell cell-impact">
                          <span className={`impact-badge impact-${article.impact}`}>
                            {article.impact}
                          </span>
                        </div>
                        <div className="cell cell-quality">
                          <span className={`quality-num ${article.quality_score >= 0.6 ? "high" : article.quality_score >= 0.4 ? "mid" : "low"}`}>
                            {article.quality_score.toFixed(1)}
                          </span>
                        </div>
                        <div className="cell cell-sentiment">
                          <span style={{ color: sentimentColor(article.sentiment) }}>
                            {article.sentiment || "—"}
                          </span>
                        </div>
                        <div className="cell cell-title">
                          {article.title}
                          {article.source && (
                            <span className="source-tag">{article.source}</span>
                          )}
                        </div>
                        <div className="cell cell-entities">
                          {article.entities?.slice(0, 2).map((e, i) => (
                            <span key={i} className="entity-tag">{e}</span>
                          ))}
                          {(article.entities?.length || 0) > 2 && (
                            <span className="entity-more">+{article.entities!.length - 2}</span>
                          )}
                        </div>
                        <div className="cell cell-tickers">
                          {article.tickers?.map((t, i) => (
                            <span key={i} className="ticker-tag">{t}</span>
                          ))}
                        </div>
                      </div>

                      {/* Expanded detail */}
                      {isExpanded && (
                        <div className="article-detail">
                          {article.summary && (
                            <div className="detail-block">
                              <div className="detail-label">Summary</div>
                              <div className="detail-text">{article.summary}</div>
                            </div>
                          )}
                          {article.takeaways && article.takeaways.length > 0 && (
                            <div className="detail-block">
                              <div className="detail-label">Takeaways</div>
                              <ul className="takeaway-list">
                                {article.takeaways.map((t, i) => (
                                  <li key={i}>{t}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                          {article.entities && article.entities.length > 0 && (
                            <div className="detail-block">
                              <div className="detail-label">All Entities</div>
                              <div className="detail-tags">
                                {article.entities.map((e, i) => (
                                  <span key={i} className="entity-tag">{e}</span>
                                ))}
                              </div>
                            </div>
                          )}
                          <div className="detail-meta">
                            {article.url && (
                              <a
                                href={article.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="article-link"
                                onClick={(e) => e.stopPropagation()}
                              >
                                Open Article
                              </a>
                            )}
                            <span className="meta-item">
                              Published: {article.published_ts ? new Date(article.published_ts).toLocaleString() : "—"}
                            </span>
                            <span className="meta-item">
                              Enriched: {article.enriched_ts ? new Date(article.enriched_ts).toLocaleString() : "—"}
                            </span>
                          </div>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
              {articles.length === 0 && (
                <tr>
                  <td colSpan={11} className="empty-state">
                    No enriched articles found in the last {hours} hours
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <style>{styles}</style>
    </div>
  );
}

const styles = `
  .admin-page {
    min-height: 100vh;
    background: var(--bg-base);
    color: var(--text-primary);
    padding: 1.5rem;
  }

  .admin-container {
    max-width: 1400px;
    margin: 0 auto;
  }

  .admin-loading,
  .admin-error {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 50vh;
    text-align: center;
  }

  .admin-error h2 { color: #f87171; margin-bottom: 0.5rem; }
  .admin-error button {
    margin-top: 1rem;
    padding: 0.5rem 1rem;
    background: #3b82f6;
    border: none;
    border-radius: 0.5rem;
    color: white;
    cursor: pointer;
  }

  .admin-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: 1.5rem;
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 1rem;
  }

  .admin-header h1 {
    font-size: 1.5rem;
    font-weight: 600;
    margin: 0;
    background: linear-gradient(135deg, #f97316, #ef4444);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }

  .article-count {
    font-size: 0.875rem;
    color: var(--text-secondary);
  }

  .header-controls {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .hours-select {
    padding: 0.5rem 0.75rem;
    background: var(--bg-input);
    border: 1px solid var(--border-default);
    border-radius: 0.5rem;
    color: var(--text-primary);
    font-size: 0.875rem;
    cursor: pointer;
  }

  .refresh-btn {
    padding: 0.5rem 1rem;
    background: rgba(249, 115, 22, 0.15);
    border: 1px solid rgba(249, 115, 22, 0.3);
    border-radius: 0.5rem;
    color: #fb923c;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
  }

  .refresh-btn:hover {
    background: rgba(249, 115, 22, 0.25);
    color: #fdba74;
  }

  .back-btn {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.5rem 0.875rem;
    background: var(--bg-hover);
    border: 1px solid var(--border-default);
    border-radius: 0.5rem;
    color: var(--text-secondary);
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
  }

  .back-btn:hover { background: var(--bg-hover); color: var(--text-bright); }
  .back-btn svg { width: 1rem; height: 1rem; }

  /* Table */
  .rss-table-container {
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: 0.75rem;
    overflow: hidden;
  }

  .rss-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.875rem;
  }

  .rss-table thead th {
    text-align: left;
    padding: 0.875rem 0.75rem;
    background: var(--bg-surface-alt);
    color: var(--text-secondary);
    font-weight: 500;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    border-bottom: 1px solid var(--border-subtle);
  }

  .rss-table tbody td {
    padding: 0;
  }

  .article-row-group {
    border-bottom: 1px solid var(--border-subtle);
  }

  .article-row {
    display: grid;
    grid-template-columns: 60px 90px 40px 40px 40px 72px 50px 80px 1fr 120px 80px;
    align-items: center;
    padding: 0.625rem 0.75rem;
    cursor: pointer;
    transition: background 0.15s;
  }

  .article-row:hover {
    background: var(--bg-hover);
  }

  .article-row.expanded {
    background: rgba(249, 115, 22, 0.05);
  }

  .cell { overflow: hidden; }

  .cell-age {
    font-family: 'SF Mono', monospace;
    font-size: 0.8125rem;
    color: var(--text-secondary);
  }

  .category-badge {
    display: inline-block;
    padding: 0.125rem 0.5rem;
    border-radius: 0.25rem;
    font-size: 0.6875rem;
    font-weight: 500;
    text-transform: capitalize;
  }

  .quality-num {
    font-family: 'SF Mono', monospace;
    font-size: 0.8125rem;
    font-weight: 600;
  }

  .quality-num.high { color: #22c55e; }
  .quality-num.mid { color: #eab308; }
  .quality-num.low { color: #9ca3af; }

  .sortable-th {
    cursor: pointer;
    user-select: none;
    white-space: nowrap;
  }
  .sortable-th:hover { color: var(--text-primary); }

  .cell-score {
    text-align: center;
  }

  .score-num {
    font-family: 'SF Mono', monospace;
    font-size: 0.8125rem;
    font-weight: 600;
  }
  .score-num.high { color: #22c55e; }
  .score-num.mid { color: #eab308; }
  .score-num.low { color: #6b7280; }
  .score-num.total { font-weight: 700; }

  .cell-impact { text-align: center; }

  .impact-badge {
    display: inline-block;
    padding: 0.0625rem 0.375rem;
    border-radius: 0.25rem;
    font-size: 0.6875rem;
    font-weight: 600;
    text-transform: capitalize;
  }
  .impact-shock { background: rgba(239, 68, 68, 0.2); color: #f87171; }
  .impact-structural { background: rgba(249, 115, 22, 0.2); color: #fb923c; }
  .impact-mild { background: rgba(234, 179, 8, 0.2); color: #facc15; }
  .impact-none { background: rgba(107, 114, 128, 0.15); color: #6b7280; }

  .cell-sentiment {
    font-size: 0.8125rem;
    font-weight: 500;
    text-transform: capitalize;
  }

  .cell-title {
    font-weight: 500;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    padding-right: 0.5rem;
  }

  .source-tag {
    margin-left: 0.5rem;
    font-size: 0.6875rem;
    font-weight: 400;
    color: var(--text-muted);
  }

  .cell-entities,
  .cell-tickers {
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem;
  }

  .entity-tag {
    display: inline-block;
    padding: 0.0625rem 0.375rem;
    background: var(--bg-hover);
    border-radius: 0.25rem;
    font-size: 0.6875rem;
    color: var(--text-secondary);
    white-space: nowrap;
  }

  .entity-more {
    font-size: 0.6875rem;
    color: var(--text-muted);
    padding: 0.0625rem 0.25rem;
  }

  .ticker-tag {
    display: inline-block;
    padding: 0.0625rem 0.375rem;
    background: rgba(59, 130, 246, 0.15);
    border-radius: 0.25rem;
    font-size: 0.6875rem;
    font-weight: 600;
    color: #60a5fa;
    white-space: nowrap;
  }

  /* Expanded Detail */
  .article-detail {
    padding: 1rem 1.5rem 1.25rem;
    background: rgba(249, 115, 22, 0.03);
    border-top: 1px solid var(--border-subtle);
  }

  .detail-block {
    margin-bottom: 1rem;
  }

  .detail-label {
    font-size: 0.6875rem;
    font-weight: 500;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.375rem;
  }

  .detail-text {
    font-size: 0.875rem;
    color: var(--text-primary);
    line-height: 1.5;
  }

  .takeaway-list {
    margin: 0;
    padding-left: 1.25rem;
    font-size: 0.875rem;
    color: var(--text-primary);
    line-height: 1.6;
  }

  .detail-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 0.375rem;
  }

  .detail-meta {
    display: flex;
    align-items: center;
    gap: 1.5rem;
    margin-top: 0.75rem;
    padding-top: 0.75rem;
    border-top: 1px solid var(--border-subtle);
  }

  .article-link {
    font-size: 0.8125rem;
    color: #60a5fa;
    text-decoration: none;
  }

  .article-link:hover {
    text-decoration: underline;
  }

  .meta-item {
    font-size: 0.75rem;
    color: var(--text-muted);
  }

  .empty-state {
    text-align: center;
    padding: 3rem 1rem !important;
    color: var(--text-secondary);
    font-size: 0.875rem;
  }
`;
