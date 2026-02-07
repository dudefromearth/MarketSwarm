/**
 * Positions Endpoint
 *
 * CRUD operations for leg-based positions.
 */

import type { Position } from '@market-swarm/core';
import type { NetworkAdapter } from '../adapters/types.js';
import type {
  PositionsListResponse,
  PositionResponse,
  CreatePositionInput,
  UpdatePositionInput,
} from '../types.js';

export interface PositionsEndpoint {
  list(): Promise<Position[]>;
  get(id: string): Promise<Position>;
  create(input: CreatePositionInput): Promise<Position>;
  update(id: string, input: UpdatePositionInput): Promise<Position>;
  delete(id: string): Promise<void>;
  reorder(ids: string[]): Promise<void>;
}

export function createPositionsEndpoint(
  network: NetworkAdapter,
  baseUrl: string,
  getHeaders: () => Record<string, string>
): PositionsEndpoint {
  const endpoint = `${baseUrl}/api/positions`;

  return {
    async list(): Promise<Position[]> {
      const response = await network.request<PositionsListResponse>(endpoint, {
        headers: getHeaders(),
      });

      if (!response.ok || !response.data.success) {
        throw new Error(response.data.error ?? 'Failed to fetch positions');
      }

      return response.data.data ?? [];
    },

    async get(id: string): Promise<Position> {
      const response = await network.request<PositionResponse>(`${endpoint}/${id}`, {
        headers: getHeaders(),
      });

      if (!response.ok || !response.data.success || !response.data.data) {
        throw new Error(response.data.error ?? 'Position not found');
      }

      return response.data.data;
    },

    async create(input: CreatePositionInput): Promise<Position> {
      const response = await network.request<PositionResponse>(endpoint, {
        method: 'POST',
        headers: getHeaders(),
        body: input,
      });

      if (!response.ok || !response.data.success || !response.data.data) {
        throw new Error(response.data.error ?? 'Failed to create position');
      }

      return response.data.data;
    },

    async update(id: string, input: UpdatePositionInput): Promise<Position> {
      const response = await network.request<PositionResponse>(`${endpoint}/${id}`, {
        method: 'PATCH',
        headers: getHeaders(),
        body: input,
      });

      if (!response.ok || !response.data.success || !response.data.data) {
        throw new Error(response.data.error ?? 'Failed to update position');
      }

      return response.data.data;
    },

    async delete(id: string): Promise<void> {
      const response = await network.request<{ success: boolean }>(`${endpoint}/${id}`, {
        method: 'DELETE',
        headers: getHeaders(),
      });

      if (!response.ok || !response.data.success) {
        throw new Error('Failed to delete position');
      }
    },

    async reorder(ids: string[]): Promise<void> {
      const response = await network.request<{ success: boolean }>(`${endpoint}/reorder`, {
        method: 'POST',
        headers: getHeaders(),
        body: { ids },
      });

      if (!response.ok || !response.data.success) {
        throw new Error('Failed to reorder positions');
      }
    },
  };
}
