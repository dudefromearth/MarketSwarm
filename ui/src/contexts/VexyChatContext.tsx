/**
 * VexyChatContext - State management for Vexy Chat
 *
 * Provides:
 * - Chat open/close state
 * - User tier and configuration
 * - Message history management
 * - Integration with PathContext
 */

import {
  createContext,
  useContext,
  useState,
  useCallback,
  type ReactNode,
} from 'react';

import type { UserTier } from '../components/VexyChat/TierBadge';

// Re-export UserTier for convenience
export type { UserTier };

interface VexyChatState {
  isOpen: boolean;
  userTier: UserTier;
}

interface VexyChatContextValue extends VexyChatState {
  openChat: () => void;
  closeChat: () => void;
  toggleChat: () => void;
  setUserTier: (tier: UserTier) => void;
}

const VexyChatContext = createContext<VexyChatContextValue | null>(null);

interface VexyChatProviderProps {
  children: ReactNode;
  initialTier?: UserTier;
}

/**
 * Determine user tier from WordPress roles
 */
export function getTierFromRoles(roles?: string[]): UserTier {
  if (!roles || !Array.isArray(roles)) return 'observer';

  // Check in priority order (highest tier first)
  if (roles.includes('administrator') || roles.includes('admin')) {
    return 'administrator';
  }
  if (roles.includes('coaching') || roles.includes('fotw_coaching')) {
    return 'coaching';
  }
  if (roles.includes('navigator') || roles.includes('fotw_navigator')) {
    return 'navigator';
  }
  if (roles.includes('activator') || roles.includes('fotw_activator')) {
    return 'activator';
  }
  // NOTE: "subscriber" is WordPress's default role shared by observers AND activators.
  // Without an explicit subscription_tier, default to "observer" (mirrors tierFromRoles in tierGates.js).

  // Default to observer for any authenticated user
  return 'observer';
}

export function VexyChatProvider({ children, initialTier = 'observer' }: VexyChatProviderProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [userTier, setUserTierState] = useState<UserTier>(initialTier);

  const openChat = useCallback(() => {
    setIsOpen(true);
  }, []);

  const closeChat = useCallback(() => {
    setIsOpen(false);
  }, []);

  const toggleChat = useCallback(() => {
    setIsOpen(prev => !prev);
  }, []);

  const setUserTier = useCallback((tier: UserTier) => {
    setUserTierState(tier);
  }, []);

  const value: VexyChatContextValue = {
    isOpen,
    userTier,
    openChat,
    closeChat,
    toggleChat,
    setUserTier,
  };

  return (
    <VexyChatContext.Provider value={value}>
      {children}
    </VexyChatContext.Provider>
  );
}

/**
 * Hook to use VexyChat context
 */
export function useVexyChatContext(): VexyChatContextValue {
  const context = useContext(VexyChatContext);
  if (!context) {
    throw new Error('useVexyChatContext must be used within a VexyChatProvider');
  }
  return context;
}
