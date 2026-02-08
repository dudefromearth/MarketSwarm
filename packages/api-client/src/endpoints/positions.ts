/**
 * Positions Endpoint
 *
 * CRUD operations for leg-based positions.
 * Returns ApiResponse wrappers for consistent error handling.
 */

import type { Position } from '@market-swarm/core';
import type { NetworkAdapter } from '../adapters/types.js';
import type {
  ApiResponse,
  PositionsListResponse,
  PositionResponse,
  CreatePositionInput,
  UpdatePositionInput,
} from '../types.js';

export interface BatchCreateResponse {
  created: number;
  ids: string[];
  errors?: Array<{ index: number; error: string }>;
}

export interface PositionsEndpoint {
  list(): Promise<ApiResponse<Position[]>>;
  get(id: string): Promise<ApiResponse<Position>>;
  create(input: CreatePositionInput): Promise<ApiResponse<Position>>;
  update(id: string, input: UpdatePositionInput): Promise<ApiResponse<Position>>;
  delete(id: string): Promise<ApiResponse<void>>;
  createBatch(inputs: CreatePositionInput[]): Promise<ApiResponse<BatchCreateResponse>>;
  reorder(order: Array<{ id: string; sortOrder: number }>): Promise<ApiResponse<void>>;
}

export function createPositionsEndpoint(
  network: NetworkAdapter,
  baseUrl: string,
  getHeaders: () => Record<string, string>
): PositionsEndpoint {
  const endpoint = `${baseUrl}/api/positions`;

  return {
    async list(): Promise<ApiResponse<Position[]>> {
      try {
        const response = await network.request<PositionsListResponse>(endpoint, {
          headers: getHeaders(),
        });

        if (!response.ok || !response.data.success) {
          return {
            success: false,
            error: response.data.error ?? 'Failed to fetch positions',
          };
        }

        return {
          success: true,
          data: response.data.data ?? [],
        };
      } catch (err) {
        return {
          success: false,
          error: err instanceof Error ? err.message : 'Network error',
        };
      }
    },

    async get(id: string): Promise<ApiResponse<Position>> {
      try {
        const response = await network.request<PositionResponse>(`${endpoint}/${id}`, {
          headers: getHeaders(),
        });

        if (!response.ok || !response.data.success || !response.data.data) {
          return {
            success: false,
            error: response.data.error ?? 'Position not found',
          };
        }

        return {
          success: true,
          data: response.data.data,
        };
      } catch (err) {
        return {
          success: false,
          error: err instanceof Error ? err.message : 'Network error',
        };
      }
    },

    async create(input: CreatePositionInput): Promise<ApiResponse<Position>> {
      console.log('[positions.create] Called with:', input);
      console.log('[positions.create] Endpoint:', endpoint);
      try {
        console.log('[positions.create] Making request...');
        const response = await network.request<PositionResponse>(endpoint, {
          method: 'POST',
          headers: getHeaders(),
          body: input,
        });

        console.log('[positions.create] Response:', response);

        if (!response.ok || !response.data.success || !response.data.data) {
          console.error('[positions.create] Request failed:', response.data.error);
          return {
            success: false,
            error: response.data.error ?? 'Failed to create position',
          };
        }

        console.log('[positions.create] Success:', response.data.data);
        return {
          success: true,
          data: response.data.data,
        };
      } catch (err) {
        console.error('[positions.create] Exception:', err);
        return {
          success: false,
          error: err instanceof Error ? err.message : 'Network error',
        };
      }
    },

    async update(id: string, input: UpdatePositionInput): Promise<ApiResponse<Position>> {
      try {
        const response = await network.request<PositionResponse>(`${endpoint}/${id}`, {
          method: 'PATCH',
          headers: getHeaders(),
          body: input,
        });

        if (!response.ok || !response.data.success || !response.data.data) {
          return {
            success: false,
            error: response.data.error ?? 'Failed to update position',
          };
        }

        return {
          success: true,
          data: response.data.data,
        };
      } catch (err) {
        return {
          success: false,
          error: err instanceof Error ? err.message : 'Network error',
        };
      }
    },

    async delete(id: string): Promise<ApiResponse<void>> {
      try {
        const response = await network.request<{ success: boolean }>(`${endpoint}/${id}`, {
          method: 'DELETE',
          headers: getHeaders(),
        });

        if (!response.ok || !response.data.success) {
          return {
            success: false,
            error: 'Failed to delete position',
          };
        }

        return { success: true };
      } catch (err) {
        return {
          success: false,
          error: err instanceof Error ? err.message : 'Network error',
        };
      }
    },

    async createBatch(inputs: CreatePositionInput[]): Promise<ApiResponse<BatchCreateResponse>> {
      try {
        const response = await network.request<{
          success: boolean;
          data?: BatchCreateResponse;
          error?: string;
        }>(`${endpoint}/batch`, {
          method: 'POST',
          headers: getHeaders(),
          body: { positions: inputs },
        });

        if (!response.ok || !response.data.success) {
          return {
            success: false,
            error: response.data.error ?? 'Failed to create positions',
          };
        }

        return {
          success: true,
          data: response.data.data ?? { created: 0, ids: [] },
        };
      } catch (err) {
        return {
          success: false,
          error: err instanceof Error ? err.message : 'Network error',
        };
      }
    },

    async reorder(order: Array<{ id: string; sortOrder: number }>): Promise<ApiResponse<void>> {
      try {
        const response = await network.request<{ success: boolean }>(`${endpoint}/reorder`, {
          method: 'PATCH',
          headers: getHeaders(),
          body: { order },
        });

        if (!response.ok || !response.data.success) {
          return {
            success: false,
            error: 'Failed to reorder positions',
          };
        }

        return { success: true };
      } catch (err) {
        return {
          success: false,
          error: err instanceof Error ? err.message : 'Network error',
        };
      }
    },
  };
}
