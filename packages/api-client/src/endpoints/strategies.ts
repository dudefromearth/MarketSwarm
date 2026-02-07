/**
 * Strategies Endpoint
 *
 * CRUD operations for legacy strategies.
 */

import type { NetworkAdapter } from '../adapters/types.js';
import type {
  Strategy,
  StrategiesListResponse,
  StrategyResponse,
  CreateStrategyInput,
  UpdateStrategyInput,
} from '../types.js';

export interface StrategiesEndpoint {
  list(): Promise<Strategy[]>;
  get(id: string): Promise<Strategy>;
  create(input: CreateStrategyInput): Promise<Strategy>;
  update(id: string, input: UpdateStrategyInput): Promise<Strategy>;
  delete(id: string): Promise<void>;
  reorder(ids: string[]): Promise<void>;
}

export function createStrategiesEndpoint(
  network: NetworkAdapter,
  baseUrl: string,
  getHeaders: () => Record<string, string>
): StrategiesEndpoint {
  const endpoint = `${baseUrl}/api/risk-graph/strategies`;

  return {
    async list(): Promise<Strategy[]> {
      const response = await network.request<StrategiesListResponse>(endpoint, {
        headers: getHeaders(),
      });

      if (!response.ok || !response.data.success) {
        throw new Error(response.data.error ?? 'Failed to fetch strategies');
      }

      return response.data.data ?? [];
    },

    async get(id: string): Promise<Strategy> {
      const response = await network.request<StrategyResponse>(`${endpoint}/${id}`, {
        headers: getHeaders(),
      });

      if (!response.ok || !response.data.success || !response.data.data) {
        throw new Error(response.data.error ?? 'Strategy not found');
      }

      return response.data.data;
    },

    async create(input: CreateStrategyInput): Promise<Strategy> {
      const response = await network.request<StrategyResponse>(endpoint, {
        method: 'POST',
        headers: getHeaders(),
        body: input,
      });

      if (!response.ok || !response.data.success || !response.data.data) {
        throw new Error(response.data.error ?? 'Failed to create strategy');
      }

      return response.data.data;
    },

    async update(id: string, input: UpdateStrategyInput): Promise<Strategy> {
      const response = await network.request<StrategyResponse>(`${endpoint}/${id}`, {
        method: 'PATCH',
        headers: getHeaders(),
        body: input,
      });

      if (!response.ok || !response.data.success || !response.data.data) {
        throw new Error(response.data.error ?? 'Failed to update strategy');
      }

      return response.data.data;
    },

    async delete(id: string): Promise<void> {
      const response = await network.request<{ success: boolean }>(`${endpoint}/${id}`, {
        method: 'DELETE',
        headers: getHeaders(),
      });

      if (!response.ok || !response.data.success) {
        throw new Error('Failed to delete strategy');
      }
    },

    async reorder(ids: string[]): Promise<void> {
      const response = await network.request<{ success: boolean }>(`${endpoint}/reorder`, {
        method: 'POST',
        headers: getHeaders(),
        body: { ids },
      });

      if (!response.ok || !response.data.success) {
        throw new Error('Failed to reorder strategies');
      }
    },
  };
}
