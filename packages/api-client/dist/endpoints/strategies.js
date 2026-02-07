/**
 * Strategies Endpoint
 *
 * CRUD operations for legacy strategies.
 */
export function createStrategiesEndpoint(network, baseUrl, getHeaders) {
    const endpoint = `${baseUrl}/api/risk-graph/strategies`;
    return {
        async list() {
            const response = await network.request(endpoint, {
                headers: getHeaders(),
            });
            if (!response.ok || !response.data.success) {
                throw new Error(response.data.error ?? 'Failed to fetch strategies');
            }
            return response.data.data ?? [];
        },
        async get(id) {
            const response = await network.request(`${endpoint}/${id}`, {
                headers: getHeaders(),
            });
            if (!response.ok || !response.data.success || !response.data.data) {
                throw new Error(response.data.error ?? 'Strategy not found');
            }
            return response.data.data;
        },
        async create(input) {
            const response = await network.request(endpoint, {
                method: 'POST',
                headers: getHeaders(),
                body: input,
            });
            if (!response.ok || !response.data.success || !response.data.data) {
                throw new Error(response.data.error ?? 'Failed to create strategy');
            }
            return response.data.data;
        },
        async update(id, input) {
            const response = await network.request(`${endpoint}/${id}`, {
                method: 'PATCH',
                headers: getHeaders(),
                body: input,
            });
            if (!response.ok || !response.data.success || !response.data.data) {
                throw new Error(response.data.error ?? 'Failed to update strategy');
            }
            return response.data.data;
        },
        async delete(id) {
            const response = await network.request(`${endpoint}/${id}`, {
                method: 'DELETE',
                headers: getHeaders(),
            });
            if (!response.ok || !response.data.success) {
                throw new Error('Failed to delete strategy');
            }
        },
        async reorder(ids) {
            const response = await network.request(`${endpoint}/reorder`, {
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
//# sourceMappingURL=strategies.js.map