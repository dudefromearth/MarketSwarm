/**
 * PathIndicator - FOTW Butterfly Avatar with Vexy Chat
 *
 * A quiet, ambient presence in the bottom-right corner.
 * ~0.5" diameter stylized butterfly bubble.
 *
 * Behavior:
 * - Dim when idle (~0.35 opacity)
 * - Brightens when mouse gets close (~0.7)
 * - Full opacity on hover (1.0)
 * - Click to open Vexy Chat panel
 *
 * After welcome modal:
 * - Fades in gently after a pause
 * - No motion, no greeting
 * - The silence is the point
 */

import { useState } from 'react';
import { usePath } from '../contexts/PathContext';
import { useAuth } from '../AuthWrapper';
import VexyChat from './VexyChat';
import { getTierFromRoles, type UserTier } from '../contexts/VexyChatContext';
import { useVexyContext, type VexyMarketContext } from '../hooks/useVexyContext';

interface UserProfile {
  display_name?: string;
  is_admin?: boolean;
}

interface PathIndicatorProps {
  marketContext?: VexyMarketContext;
  positions?: any[];
  trades?: any[];
  openTrades?: any[];
  closedTrades?: any[];
  riskStrategies?: any[];
  userProfile?: UserProfile | null;
}

export default function PathIndicator({
  marketContext,
  positions,
  trades,
  openTrades,
  closedTrades,
  riskStrategies,
  userProfile,
}: PathIndicatorProps) {
  const {
    indicatorVisible,
    transitionPhase,
  } = usePath();
  const { user, isAdmin } = useAuth();
  const [chatOpen, setChatOpen] = useState(false);

  // Gather comprehensive context for Vexy
  const vexyContext = useVexyContext({
    marketContext,
    positions,
    trades,
    openTrades,
    closedTrades,
    riskStrategies,
  });

  // Don't render until indicator should be visible
  if (!indicatorVisible) {
    return null;
  }

  // Determine user tier from roles
  const userTier: UserTier = isAdmin
    ? 'administrator'
    : getTierFromRoles(user?.wp?.roles);

  // Toggle chat panel
  const handleClick = () => {
    setChatOpen(prev => !prev);
  };

  // Close chat panel
  const handleClose = () => {
    setChatOpen(false);
  };

  // Determine fade-in class
  const fadeClass = transitionPhase === 'fading-in' ? ' fading-in' : '';

  return (
    <>
      {/* Butterfly avatar bubble */}
      <div
        className={`path-avatar${fadeClass}${chatOpen ? ' chat-open' : ''}`}
        onClick={handleClick}
      >
        <svg
          viewBox="0 0 48 48"
          className="path-avatar-svg"
          aria-label="Vexy chat"
        >
          {/* Stylized butterfly - abstract, geometric */}
          <g className="butterfly-shape">
            {/* Left wing */}
            <ellipse
              className="wing"
              cx="18"
              cy="24"
              rx="10"
              ry="14"
              fill="currentColor"
              opacity="0.6"
            />
            {/* Right wing */}
            <ellipse
              className="wing"
              cx="30"
              cy="24"
              rx="10"
              ry="14"
              fill="currentColor"
              opacity="0.6"
            />
            {/* Body */}
            <ellipse
              className="body"
              cx="24"
              cy="24"
              rx="3"
              ry="12"
              fill="currentColor"
              opacity="0.9"
            />
            {/* Wing details - subtle curves */}
            <ellipse
              className="wing-detail"
              cx="16"
              cy="20"
              rx="4"
              ry="5"
              fill="currentColor"
              opacity="0.3"
            />
            <ellipse
              className="wing-detail"
              cx="32"
              cy="20"
              rx="4"
              ry="5"
              fill="currentColor"
              opacity="0.3"
            />
            <ellipse
              className="wing-detail"
              cx="16"
              cy="28"
              rx="3"
              ry="4"
              fill="currentColor"
              opacity="0.25"
            />
            <ellipse
              className="wing-detail"
              cx="32"
              cy="28"
              rx="3"
              ry="4"
              fill="currentColor"
              opacity="0.25"
            />
          </g>
        </svg>
      </div>

      {/* Vexy Chat Panel */}
      <VexyChat
        isOpen={chatOpen}
        onClose={handleClose}
        userTier={userTier}
        context={vexyContext}
        userProfile={userProfile ? {
          display_name: userProfile.display_name,
          is_admin: userProfile.is_admin || isAdmin,
        } : undefined}
      />
    </>
  );
}
