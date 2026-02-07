/**
 * Positions Endpoint
 *
 * CRUD operations for leg-based positions.
 */
export function createPositionsEndpoint(network, baseUrl, getHeaders) {
    const endpoint = `${baseUrl}/api/positions`;
    return {
        async list() {
            const response = await network.request(endpoint, {
                headers: getHeaders(),
            });
            if (!response.ok || !response.data.success) {
                throw new Error(response.data.error ?? 'Failed to fetch positions');
            }
            return response.data.data ?? [];
        },
        async get(id) {
            const response = await network.request(`${endpoint}/${id}`, {
                headers: getHeaders(),
            });
            if (!response.ok || !response.data.success || !response.data.data) {
                throw new Error(response.data.error ?? 'Position not found');
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
                throw new Error(response.data.error ?? 'Failed to create position');
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
                throw new Error(response.data.error ?? 'Failed to update position');
            }
            return response.data.data;
        },
        async delete(id) {
            const response = await network.request(`${endpoint}/${id}`, {
                method: 'DELETE',
                headers: getHeaders(),
            });
            if (!response.ok || !response.data.success) {
                throw new Error('Failed to delete position');
            }
        },
        async reorder(ids) {
            const response = await network.request(`${endpoint}/reorder`, {
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
//# sourceMappingURL=positions.js.map