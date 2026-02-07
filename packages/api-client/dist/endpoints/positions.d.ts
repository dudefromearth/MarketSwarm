/**
 * Positions Endpoint
 *
 * CRUD operations for leg-based positions.
 */
import type { Position } from '@market-swarm/core';
import type { NetworkAdapter } from '../adapters/types.js';
import type { CreatePositionInput, UpdatePositionInput } from '../types.js';
export interface PositionsEndpoint {
    list(): Promise<Position[]>;
    get(id: string): Promise<Position>;
    create(input: CreatePositionInput): Promise<Position>;
    update(id: string, input: UpdatePositionInput): Promise<Position>;
    delete(id: string): Promise<void>;
    reorder(ids: string[]): Promise<void>;
}
export declare function createPositionsEndpoint(network: NetworkAdapter, baseUrl: string, getHeaders: () => Record<string, string>): PositionsEndpoint;
//# sourceMappingURL=positions.d.ts.map