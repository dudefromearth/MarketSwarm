// src/components/LeaderboardSettingsModal.tsx
import { useState, useEffect } from 'react';
import type { LeaderboardSettings, LeaderboardSettingsUpdate } from '../types/leaderboard';

const SSE_BASE = '';

interface LeaderboardSettingsModalProps {
  onClose: () => void;
  onSaved?: () => void;
}

export default function LeaderboardSettingsModal({ onClose, onSaved }: LeaderboardSettingsModalProps) {
  const [settings, setSettings] = useState<LeaderboardSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Form state
  const [screenName, setScreenName] = useState('');
  const [showScreenName, setShowScreenName] = useState(true);

  useEffect(() => {
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    try {
      setLoading(true);
      const res = await fetch(`${SSE_BASE}/api/profile/leaderboard-settings`, {
        credentials: 'include',
      });

      if (!res.ok) {
        throw new Error('Failed to fetch settings');
      }

      const data: LeaderboardSettings = await res.json();
      setSettings(data);
      setScreenName(data.screenName || '');
      setShowScreenName(data.showScreenName);
    } catch (err) {
      console.error('Failed to fetch leaderboard settings:', err);
      setError('Failed to load settings');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      setError(null);

      const updates: LeaderboardSettingsUpdate = {
        screenName: screenName.trim() || undefined,
        showScreenName,
      };

      const res = await fetch(`${SSE_BASE}/api/profile/leaderboard-settings`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(updates),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to save settings');
      }

      onSaved?.();
      onClose();
    } catch (err) {
      console.error('Failed to save leaderboard settings:', err);
      setError(err instanceof Error ? err.message : 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  const previewName = showScreenName && screenName.trim()
    ? screenName.trim()
    : settings?.displayName || 'Your Name';

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content leaderboard-settings-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Leaderboard Settings</h2>
          <button className="modal-close" onClick={onClose}>&times;</button>
        </div>

        <div className="modal-body">
          {loading ? (
            <div className="loading-state">Loading settings...</div>
          ) : error && !settings ? (
            <div className="error-state">{error}</div>
          ) : (
            <>
              <div className="settings-section">
                <h3>Display Name</h3>
                <p className="settings-description">
                  Choose how you appear on the leaderboard. Your screen name is visible to all users.
                </p>

                <div className="form-group">
                  <label htmlFor="screenName">Screen Name (optional)</label>
                  <input
                    id="screenName"
                    type="text"
                    value={screenName}
                    onChange={e => setScreenName(e.target.value)}
                    placeholder="TraderX"
                    maxLength={100}
                    className="form-input"
                  />
                  <span className="input-hint">
                    Letters, numbers, underscores, hyphens, spaces (max 100 chars)
                  </span>
                </div>

                <div className="form-group">
                  <label className="toggle-label">
                    <input
                      type="checkbox"
                      checked={showScreenName}
                      onChange={e => setShowScreenName(e.target.checked)}
                    />
                    <span className="toggle-text">
                      {showScreenName
                        ? 'Show screen name on leaderboard'
                        : 'Show real name on leaderboard'}
                    </span>
                  </label>
                </div>

                <div className="preview-section">
                  <span className="preview-label">Preview:</span>
                  <span className="preview-name">{previewName}</span>
                </div>
              </div>

              {error && (
                <div className="error-message">{error}</div>
              )}
            </>
          )}
        </div>

        <div className="modal-footer">
          <button className="btn-secondary" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button
            className="btn-primary"
            onClick={handleSave}
            disabled={loading || saving}
          >
            {saving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}
