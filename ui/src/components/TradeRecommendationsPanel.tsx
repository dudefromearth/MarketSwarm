// ui/src/components/TradeRecommendationsPanel.tsx
// Trade recommendations display with score breakdowns

import { useState, useCallback } from 'react';
import type { TradeRecommendation, TradeSelectorModel, VixRegime } from '../types/tradeSelector';

interface ScoreBarProps {
  label: string;
  value: number;
  color?: string;
}

function ScoreBar({ label, value, color = '#3b82f6' }: ScoreBarProps) {
  return (
    <div className="score-bar">
      <div className="score-bar-label">{label}</div>
      <div className="score-bar-track">
        <div
          className="score-bar-fill"
          style={{
            width: `${Math.min(100, Math.max(0, value))}%`,
            backgroundColor: color,
          }}
        />
      </div>
      <div className="score-bar-value">{Math.round(value)}</div>
    </div>
  );
}

interface RecommendationCardProps {
  rec: TradeRecommendation;
  expanded: boolean;
  onToggle: () => void;
  onSelect: (rec: TradeRecommendation) => void;
}

function RecommendationCard({ rec, expanded, onToggle, onSelect }: RecommendationCardProps) {
  const handleClick = () => {
    onSelect(rec);
  };

  const handleExpandClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    onToggle();
  };

  // Color based on composite score
  const getScoreColor = (score: number): string => {
    if (score >= 75) return '#22c55e'; // Green
    if (score >= 50) return '#eab308'; // Yellow
    return '#ef4444'; // Red
  };

  // Rank badge color
  const getRankBadgeClass = (rank: number): string => {
    if (rank === 1) return 'rank-badge rank-1';
    if (rank === 2) return 'rank-badge rank-2';
    if (rank === 3) return 'rank-badge rank-3';
    return 'rank-badge';
  };

  return (
    <div className="recommendation-card" onClick={handleClick}>
      <div className="rec-card-main">
        <div className={getRankBadgeClass(rec.rank)}>{rec.rank}</div>

        <div className="rec-strategy-info">
          <div className="rec-strategy-desc">
            <span className={`side-badge ${rec.side}`}>{rec.side.toUpperCase()}</span>
            <span className="rec-width">{rec.width}w</span>
            <span className="rec-strike">@ {rec.strike}</span>
          </div>
          <div className="rec-meta">
            <span className="rec-debit">${rec.debit.toFixed(2)}</span>
            <span className="rec-r2r">{rec.r2r_ratio.toFixed(1)}:1</span>
            <span className="rec-distance">
              {rec.distance_to_spot > 0 ? '+' : ''}{rec.distance_to_spot.toFixed(0)} pts
            </span>
          </div>
        </div>

        <div
          className="rec-score"
          style={{ color: getScoreColor(rec.score.composite) }}
        >
          {Math.round(rec.score.composite)}
        </div>

        <button
          className="rec-expand-btn"
          onClick={handleExpandClick}
          aria-label={expanded ? 'Collapse' : 'Expand'}
        >
          {expanded ? '−' : '+'}
        </button>
      </div>

      {expanded && (
        <div className="rec-card-details">
          <div className="score-breakdown">
            <ScoreBar
              label="R:R"
              value={rec.score.components.r2r}
              color="#3b82f6"
            />
            <ScoreBar
              label="Convexity"
              value={rec.score.components.convexity}
              color="#8b5cf6"
            />
            <ScoreBar
              label="Width Fit"
              value={rec.score.components.width_fit}
              color="#06b6d4"
            />
            <ScoreBar
              label="Gamma"
              value={rec.score.components.gamma_alignment}
              color="#f59e0b"
            />
          </div>
          <div className="rec-extra-info">
            <div className="rec-profit-loss">
              <span className="profit">+${rec.max_profit.toFixed(2)}</span>
              <span className="separator">/</span>
              <span className="loss">-${rec.max_loss.toFixed(2)}</span>
            </div>
            {rec.distance_to_gamma_magnet !== null && (
              <div className="rec-gamma-distance">
                {Math.abs(rec.distance_to_gamma_magnet).toFixed(0)} pts to magnet
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

interface TradeRecommendationsPanelProps {
  model: TradeSelectorModel | null;
  onSelectTrade: (rec: TradeRecommendation) => void;
  maxVisible?: number;
}

export default function TradeRecommendationsPanel({
  model,
  onSelectTrade,
  maxVisible = 5,
}: TradeRecommendationsPanelProps) {
  const [expandedRank, setExpandedRank] = useState<number | null>(null);
  const [showAll, setShowAll] = useState(false);

  const handleToggleExpand = useCallback((rank: number) => {
    setExpandedRank(prev => prev === rank ? null : rank);
  }, []);

  const getRegimeBadgeClass = (regime: VixRegime): string => {
    switch (regime) {
      case 'chaos': return 'regime-badge regime-chaos';
      case 'goldilocks': return 'regime-badge regime-goldilocks';
      case 'zombieland': return 'regime-badge regime-zombieland';
      default: return 'regime-badge';
    }
  };

  const getRegimeLabel = (regime: VixRegime): string => {
    switch (regime) {
      case 'chaos': return 'Chaos';
      case 'goldilocks': return 'Goldilocks';
      case 'zombieland': return 'ZombieLand';
      default: return regime;
    }
  };

  if (!model) {
    return (
      <div className="trade-recommendations-panel">
        <div className="recommendations-header">
          <h3>Trade Ideas</h3>
        </div>
        <div className="recommendations-loading">
          Loading recommendations...
        </div>
      </div>
    );
  }

  const visibleRecs = showAll
    ? model.recommendations
    : model.recommendations.slice(0, maxVisible);

  const hasMore = model.recommendations.length > maxVisible;

  return (
    <div className="trade-recommendations-panel">
      <div className="recommendations-header">
        <h3>Trade Ideas</h3>
        <div className="header-meta">
          <span className={getRegimeBadgeClass(model.vix_regime)}>
            {getRegimeLabel(model.vix_regime)}
          </span>
          {model.vix_special && (
            <span className="special-badge">
              {model.vix_special === 'timewarp' && '⏰ TIMEWARP'}
              {model.vix_special === 'gamma_scalp' && '⚡ GAMMA SCALP'}
              {model.vix_special === 'batman' && '🦇 BATMAN'}
            </span>
          )}
          <span className="vix-value">VIX: {model.vix.toFixed(1)}</span>
        </div>
      </div>

      <div className="recommendations-list">
        {visibleRecs.length === 0 ? (
          <div className="no-recommendations">
            No recommendations available
          </div>
        ) : (
          visibleRecs.map(rec => (
            <RecommendationCard
              key={rec.tile_key}
              rec={rec}
              expanded={expandedRank === rec.rank}
              onToggle={() => handleToggleExpand(rec.rank)}
              onSelect={onSelectTrade}
            />
          ))
        )}
      </div>

      {hasMore && (
        <button
          className="show-more-btn"
          onClick={() => setShowAll(prev => !prev)}
        >
          {showAll ? 'Show Less' : `Show ${model.recommendations.length - maxVisible} More`}
        </button>
      )}

      <div className="recommendations-footer">
        <span className="scored-count">
          {model.total_scored} tiles scored
        </span>
        {model.gamma_magnet && (
          <span className="gamma-magnet">
            Magnet: {model.gamma_magnet}
          </span>
        )}
      </div>
    </div>
  );
}
