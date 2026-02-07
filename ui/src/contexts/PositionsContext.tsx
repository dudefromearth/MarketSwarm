// contexts/PositionsContext.tsx
// React context for leg-based positions with offline support
//
// This context provides the new leg-based position model,
// replacing the legacy strategy model for Risk Graph.

import {
  createContext,
  useContext,
  type ReactNode,
} from 'react';
import {
  usePositions,
  type UsePositionsResult,
  type CreatePositionInput,
  type UpdatePositionInput,
  type Position,
  type PositionLeg,
  type PositionType,
  type PositionDirection,
  type CostBasisType,
} from '../hooks/usePositions';

// Re-export types for consumers
export type {
  Position,
  PositionLeg,
  PositionType,
  PositionDirection,
  CostBasisType,
  CreatePositionInput,
  UpdatePositionInput,
};

// Context type is the hook result
type PositionsContextValue = UsePositionsResult;

const PositionsContext = createContext<PositionsContextValue | null>(null);

interface PositionsProviderProps {
  children: ReactNode;
}

/**
 * Provider for leg-based positions with offline support.
 *
 * Must be wrapped in ApiClientProvider.
 *
 * Usage:
 * ```tsx
 * <ApiClientProvider>
 *   <PositionsProvider>
 *     <App />
 *   </PositionsProvider>
 * </ApiClientProvider>
 * ```
 */
export function PositionsProvider({ children }: PositionsProviderProps) {
  const positionsHook = usePositions();

  return (
    <PositionsContext.Provider value={positionsHook}>
      {children}
    </PositionsContext.Provider>
  );
}

/**
 * Hook for accessing leg-based positions.
 *
 * Provides:
 * - positions: Current positions list
 * - loading: Whether initial fetch is in progress
 * - connected: Whether SSE is connected
 * - CRUD operations with optimistic updates
 *
 * Example:
 * ```tsx
 * function PositionsList() {
 *   const { positions, addPosition, removePosition } = usePositionsContext();
 *
 *   const handleAdd = async () => {
 *     await addPosition({
 *       positionType: 'butterfly',
 *       direction: 'long',
 *       legs: [
 *         { strike: 5880, expiration: '2024-03-15', right: 'call', quantity: 1 },
 *         { strike: 5900, expiration: '2024-03-15', right: 'call', quantity: -2 },
 *         { strike: 5920, expiration: '2024-03-15', right: 'call', quantity: 1 },
 *       ],
 *       costBasis: 2.50,
 *       costBasisType: 'debit',
 *     });
 *   };
 *
 *   return (
 *     <ul>
 *       {positions.map(pos => (
 *         <li key={pos.id}>
 *           {pos.positionType} - {pos.legs.length} legs
 *           <button onClick={() => removePosition(pos.id)}>Remove</button>
 *         </li>
 *       ))}
 *     </ul>
 *   );
 * }
 * ```
 */
export function usePositionsContext(): PositionsContextValue {
  const context = useContext(PositionsContext);
  if (!context) {
    throw new Error('usePositionsContext must be used within a PositionsProvider');
  }
  return context;
}

/**
 * Convenience hook that only returns visible positions.
 */
export function useVisiblePositions(): Position[] {
  const { getVisiblePositions } = usePositionsContext();
  return getVisiblePositions();
}

/**
 * Convenience hook for a single position by ID.
 */
export function usePosition(id: string): Position | undefined {
  const { getPosition } = usePositionsContext();
  return getPosition(id);
}
