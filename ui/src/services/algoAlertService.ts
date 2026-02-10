/**
 * Algo Alert Service — API layer for algo-alerts and proposals.
 *
 * Follows alertService.ts pattern: pure functions, credentials: 'include'.
 */

import type {
  AlgoAlert,
  AlgoProposal,
  CreateAlgoAlertInput,
  UpdateAlgoAlertInput,
} from '../types/algoAlerts';

interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
}

// ==================== Algo Alerts ====================

export async function fetchAlgoAlerts(status?: string): Promise<AlgoAlert[]> {
  try {
    const params = status ? `?status=${status}` : '';
    const response = await fetch(`/api/algo-alerts${params}`, {
      credentials: 'include',
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const result: ApiResponse<AlgoAlert[]> = await response.json();
    if (result.success && result.data) {
      return result.data;
    }
    throw new Error(result.error || 'Failed to fetch algo alerts');
  } catch (err) {
    console.error('fetchAlgoAlerts error:', err);
    throw err;
  }
}

export async function createAlgoAlertApi(input: CreateAlgoAlertInput): Promise<AlgoAlert> {
  try {
    const response = await fetch('/api/algo-alerts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(input),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const result: ApiResponse<AlgoAlert> = await response.json();
    if (result.success && result.data) {
      return result.data;
    }
    throw new Error(result.error || 'Failed to create algo alert');
  } catch (err) {
    console.error('createAlgoAlertApi error:', err);
    throw err;
  }
}

export async function updateAlgoAlertApi(id: string, input: UpdateAlgoAlertInput): Promise<AlgoAlert> {
  try {
    const response = await fetch(`/api/algo-alerts/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(input),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const result: ApiResponse<AlgoAlert> = await response.json();
    if (result.success && result.data) {
      return result.data;
    }
    throw new Error(result.error || 'Failed to update algo alert');
  } catch (err) {
    console.error('updateAlgoAlertApi error:', err);
    throw err;
  }
}

export async function deleteAlgoAlertApi(id: string): Promise<void> {
  try {
    const response = await fetch(`/api/algo-alerts/${id}`, {
      method: 'DELETE',
      credentials: 'include',
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const result: ApiResponse<void> = await response.json();
    if (!result.success) {
      throw new Error(result.error || 'Failed to delete algo alert');
    }
  } catch (err) {
    console.error('deleteAlgoAlertApi error:', err);
    throw err;
  }
}

// ==================== Algo Proposals ====================

export async function fetchAlgoProposals(
  algoAlertId?: string,
  status?: string,
): Promise<AlgoProposal[]> {
  try {
    const params = new URLSearchParams();
    if (algoAlertId) params.set('algoAlertId', algoAlertId);
    if (status) params.set('status', status);
    const qs = params.toString();
    const response = await fetch(`/api/algo-proposals${qs ? `?${qs}` : ''}`, {
      credentials: 'include',
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const result: ApiResponse<AlgoProposal[]> = await response.json();
    if (result.success && result.data) {
      return result.data;
    }
    throw new Error(result.error || 'Failed to fetch algo proposals');
  } catch (err) {
    console.error('fetchAlgoProposals error:', err);
    throw err;
  }
}

export async function approveProposalApi(id: string): Promise<AlgoProposal> {
  try {
    const response = await fetch(`/api/algo-proposals/${id}/approve`, {
      method: 'POST',
      credentials: 'include',
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const result: ApiResponse<AlgoProposal> = await response.json();
    if (result.success && result.data) {
      return result.data;
    }
    throw new Error(result.error || 'Failed to approve proposal');
  } catch (err) {
    console.error('approveProposalApi error:', err);
    throw err;
  }
}

export async function rejectProposalApi(id: string): Promise<AlgoProposal> {
  try {
    const response = await fetch(`/api/algo-proposals/${id}/reject`, {
      method: 'POST',
      credentials: 'include',
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const result: ApiResponse<AlgoProposal> = await response.json();
    if (result.success && result.data) {
      return result.data;
    }
    throw new Error(result.error || 'Failed to reject proposal');
  } catch (err) {
    console.error('rejectProposalApi error:', err);
    throw err;
  }
}
