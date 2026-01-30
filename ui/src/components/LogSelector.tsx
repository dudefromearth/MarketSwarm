// src/components/LogSelector.tsx
import { useState, useEffect } from 'react';

const JOURNAL_API = 'http://localhost:3002';

export interface TradeLog {
  id: string;
  name: string;
  starting_capital: number;
  starting_capital_dollars: number;
  risk_per_trade: number | null;
  risk_per_trade_dollars?: number;
  max_position_size: number | null;
  intent: string | null;
  constraints: string | null;
  regime_assumptions: string | null;
  notes: string | null;
  is_active: number;
  total_trades: number;
  open_trades: number;
  closed_trades: number;
  total_pnl: number;
  total_pnl_dollars: number;
  created_at: string;
  updated_at: string;
}

interface LogSelectorProps {
  selectedLogId: string | null;
  onSelectLog: (log: TradeLog) => void;
  onManageLogs: () => void;
  refreshTrigger?: number;
}

export default function LogSelector({
  selectedLogId,
  onSelectLog,
  onManageLogs,
  refreshTrigger = 0
}: LogSelectorProps) {
  const [logs, setLogs] = useState<TradeLog[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchLogs = async () => {
      try {
        const response = await fetch(`${JOURNAL_API}/api/logs`);
        const result = await response.json();

        if (result.success && result.data.length > 0) {
          setLogs(result.data);

          // Auto-select first log if none selected
          if (!selectedLogId) {
            onSelectLog(result.data[0]);
          }
        }
      } catch (err) {
        console.error('LogSelector fetch error:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchLogs();
  }, [refreshTrigger, selectedLogId, onSelectLog]);

  const selectedLog = logs.find(l => l.id === selectedLogId);

  if (loading) {
    return (
      <div className="log-selector">
        <span className="log-selector-loading">Loading...</span>
      </div>
    );
  }

  return (
    <div className="log-selector">
      <select
        className="log-select"
        value={selectedLogId || ''}
        onChange={(e) => {
          const log = logs.find(l => l.id === e.target.value);
          if (log) onSelectLog(log);
        }}
      >
        {logs.length === 0 ? (
          <option value="">No Logs</option>
        ) : (
          logs.map(log => (
            <option key={log.id} value={log.id}>
              {log.name}
            </option>
          ))
        )}
      </select>

      {selectedLog && (
        <span className="log-summary">
          <span className={`log-pnl ${selectedLog.total_pnl >= 0 ? 'profit' : 'loss'}`}>
            {selectedLog.total_pnl >= 0 ? '+' : ''}${(selectedLog.total_pnl / 100).toFixed(0)}
          </span>
          <span className="log-trade-count">
            {selectedLog.total_trades} trades
          </span>
        </span>
      )}

      <button
        className="btn-manage-logs"
        onClick={onManageLogs}
        title="Manage Trade Logs"
      >
        Manage
      </button>
    </div>
  );
}
