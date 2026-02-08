/**
 * Positions Endpoint
 *
 * CRUD operations for leg-based positions.
 * Returns ApiResponse wrappers for consistent error handling.
 */
export function createPositionsEndpoint(network, baseUrl, getHeaders) {
    const endpoint = `${baseUrl}/api/positions`;
    return {
        async list() {
            try {
                const response = await network.request(endpoint, {
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
            }
            catch (err) {
                return {
                    success: false,
                    error: err instanceof Error ? err.message : 'Network error',
                };
            }
        },
        async get(id) {
            try {
                const response = await network.request(`${endpoint}/${id}`, {
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
            }
            catch (err) {
                return {
                    success: false,
                    error: err instanceof Error ? err.message : 'Network error',
                };
            }
        },
        async create(input) {
            try {
                const response = await network.request(endpoint, {
                    method: 'POST',
                    headers: getHeaders(),
                    body: input,
                });
                if (!response.ok || !response.data.success || !response.data.data) {
                    return {
                        success: false,
                        error: response.data.error ?? 'Failed to create position',
                    };
                }
                return {
                    success: true,
                    data: response.data.data,
                };
            }
            catch (err) {
                return {
                    success: false,
                    error: err instanceof Error ? err.message : 'Network error',
                };
            }
        },
        async update(id, input) {
            try {
                const response = await network.request(`${endpoint}/${id}`, {
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
            }
            catch (err) {
                return {
                    success: false,
                    error: err instanceof Error ? err.message : 'Network error',
                };
            }
        },
        async delete(id) {
            try {
                const response = await network.request(`${endpoint}/${id}`, {
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
            }
            catch (err) {
                return {
                    success: false,
                    error: err instanceof Error ? err.message : 'Network error',
                };
            }
        },
        async createBatch(inputs) {
            try {
                const response = await network.request(`${endpoint}/batch`, {
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
            }
            catch (err) {
                return {
                    success: false,
                    error: err instanceof Error ? err.message : 'Network error',
                };
            }
        },
        async reorder(order) {
            try {
                const response = await network.request(`${endpoint}/reorder`, {
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
            }
            catch (err) {
                return {
                    success: false,
                    error: err instanceof Error ? err.message : 'Network error',
                };
            }
        },
    };
}
//# sourceMappingURL=positions.js.map