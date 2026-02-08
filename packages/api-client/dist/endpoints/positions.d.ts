/**
 * Positions Endpoint
 *
 * CRUD operations for leg-based positions.
 * Returns ApiResponse wrappers for consistent error handling.
 */
import type { Position } from '@market-swarm/core';
import type { NetworkAdapter } from '../adapters/types.js';
import type { ApiResponse, CreatePositionInput, UpdatePositionInput } from '../types.js';
export interface BatchCreateResponse {
    created: number;
    ids: string[];
    errors?: Array<{
        index: number;
        error: string;
    }>;
}
export interface PositionsEndpoint {
    list(): Promise<ApiResponse<Position[]>>;
    get(id: string): Promise<ApiResponse<Position>>;
    create(input: CreatePositionInput): Promise<ApiResponse<Position>>;
    update(id: string, input: UpdatePositionInput): Promise<ApiResponse<Position>>;
    delete(id: string): Promise<ApiResponse<void>>;
    createBatch(inputs: CreatePositionInput[]): Promise<ApiResponse<BatchCreateResponse>>;
    reorder(order: Array<{
        id: string;
        sortOrder: number;
    }>): Promise<ApiResponse<void>>;
}
export declare function createPositionsEndpoint(network: NetworkAdapter, baseUrl: string, getHeaders: () => Record<string, string>): PositionsEndpoint;
//# sourceMappingURL=positions.d.ts.map