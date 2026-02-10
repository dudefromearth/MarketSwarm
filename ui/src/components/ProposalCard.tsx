/**
 * ProposalCard — Renders a single algo alert proposal with approve/reject.
 */

import { useState, useEffect } from 'react';
import type { AlgoProposal } from '../types/algoAlerts';
import { PROPOSAL_TYPE_STYLES } from '../types/algoAlerts';

interface ProposalCardProps {
  proposal: AlgoProposal;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
}

export default function ProposalCard({ proposal, onApprove, onReject }: ProposalCardProps) {
  const [timeLeft, setTimeLeft] = useState('');
  const [expired, setExpired] = useState(false);

  // Expiration countdown
  useEffect(() => {
    const update = () => {
      const now = Date.now();
      const expires = new Date(proposal.expiresAt).getTime();
      const diff = expires - now;

      if (diff <= 0) {
        setTimeLeft('Expired');
        setExpired(true);
        return;
      }

      const minutes = Math.floor(diff / 60000);
      const seconds = Math.floor((diff % 60000) / 1000);
      setTimeLeft(`${minutes}:${seconds.toString().padStart(2, '0')}`);
    };

    update();
    const interval = setInterval(update, 1000);
    return () => clearInterval(interval);
  }, [proposal.expiresAt]);

  const typeStyle = PROPOSAL_TYPE_STYLES[proposal.type] || PROPOSAL_TYPE_STYLES.hold;
  const pos = proposal.suggestedPosition;
  const alignmentScore = proposal.structuralAlignmentScore;
  const alignmentColor = alignmentScore >= 80 ? '#22c55e' : alignmentScore >= 50 ? '#f59e0b' : '#ef4444';

  if (expired || proposal.status !== 'pending') return null;

  return (
    <div className="proposal-card">
      <div className="proposal-card-header">
        <span
          className="proposal-type-badge"
          style={{ color: typeStyle.color, background: typeStyle.bgColor }}
        >
          {typeStyle.label}
        </span>
        <span className="proposal-expiry">{timeLeft}</span>
      </div>

      {pos && (
        <div className="proposal-position-detail">
          {pos.strategyType} {pos.side?.toUpperCase()} {pos.strike}/{pos.width}w
          {pos.dte !== undefined && ` ${pos.dte}DTE`}
          {pos.estimatedDebit > 0 && ` ~$${pos.estimatedDebit.toFixed(0)}`}
        </div>
      )}

      <div className="proposal-reasoning">{proposal.reasoning}</div>

      <div className="proposal-alignment">
        <span className="proposal-alignment-label" title="Reflects structural alignment, not direction or outcome probability">
          Alignment
        </span>
        <div className="proposal-alignment-bar">
          <div
            className="proposal-alignment-fill"
            style={{
              width: `${Math.min(100, Math.max(0, alignmentScore))}%`,
              background: alignmentColor,
            }}
          />
        </div>
        <span>{alignmentScore.toFixed(0)}%</span>
      </div>

      <div className="proposal-actions">
        <button className="btn-approve" onClick={() => onApprove(proposal.id)}>
          Approve
        </button>
        <button className="btn-reject" onClick={() => onReject(proposal.id)}>
          Reject
        </button>
      </div>
    </div>
  );
}
