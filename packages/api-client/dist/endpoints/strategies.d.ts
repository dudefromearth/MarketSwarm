/**
 * Strategies Endpoint
 *
 * CRUD operations for legacy strategies.
 */
import type { NetworkAdapter } from '../adapters/types.js';
import type { Strategy, CreateStrategyInput, UpdateStrategyInput } from '../types.js';
export interface StrategiesEndpoint {
    list(): Promise<Strategy[]>;
    get(id: string): Promise<Strategy>;
    create(input: CreateStrategyInput): Promise<Strategy>;
    update(id: string, input: UpdateStrategyInput): Promise<Strategy>;
    delete(id: string): Promise<void>;
    reorder(ids: string[]): Promise<void>;
}
export declare function createStrategiesEndpoint(network: NetworkAdapter, baseUrl: string, getHeaders: () => Record<string, string>): StrategiesEndpoint;
//# sourceMappingURL=strategies.d.ts.map