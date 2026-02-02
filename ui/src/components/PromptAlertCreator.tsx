// src/components/PromptAlertCreator.tsx
/**
 * PromptAlertCreator - Natural language prompt alert creation UI
 *
 * Allows traders to describe alert conditions in natural language.
 * The AI parses the prompt into semantic zones for evaluation.
 */

import { useState, useCallback } from 'react';
import type {
  ConfidenceThreshold,
  OrchestrationMode,
  CreatePromptAlertInput,
  ReferenceStateSnapshot,
} from '../types/alerts';
import '../styles/prompt-alert.css';

interface PromptAlertCreatorProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (alert: CreatePromptAlertInput) => Promise<void>;
  strategyId: string;
  strategyLabel: string;

  // Current strategy state for reference capture
  strategyState?: {
    delta?: number;
    gamma?: number;
    theta?: number;
    maxProfit?: number;
    maxLoss?: number;
    pnlAtSpot?: number;
    spotPrice?: number;
    vix?: number;
    dte?: number;
    debit?: number;
    strike?: number;
    width?: number;
    side?: string;
  };

  // Existing prompt alerts for orchestration
  existingAlerts?: Array<{ id: string; promptText: string }>;
}

const CONFIDENCE_OPTIONS: Array<{ value: ConfidenceThreshold; label: string; description: string }> = [
  { value: 'low', label: 'Low', description: 'AI needs 40%+ confidence to transition' },
  { value: 'medium', label: 'Medium', description: 'AI needs 60%+ confidence to transition' },
  { value: 'high', label: 'High', description: 'AI needs 80%+ confidence to transition' },
];

const ORCHESTRATION_OPTIONS: Array<{ value: OrchestrationMode; label: string; description: string }> = [
  { value: 'parallel', label: 'Parallel', description: 'Evaluate independently, no side effects' },
  { value: 'overlapping', label: 'Overlapping', description: 'Both active until objective met' },
  { value: 'sequential', label: 'Sequential', description: 'Relay: A -> B -> C with fresh reference' },
];

const EXAMPLE_PROMPTS = [
  'Alert me if gamma starts eating into my profit zone as we get closer to expiration. I want to protect at least 40% of the max profit.',
  'Notify me when theta decay accelerates but my profit isn\'t growing proportionally.',
  'Watch for the risk profile to shift unfavorably if spot moves more than 1% from entry.',
  'Tell me if the position starts losing money faster than expected based on the greeks.',
];

export default function PromptAlertCreator({
  isOpen,
  onClose,
  onSave,
  strategyId,
  strategyLabel,
  strategyState,
  existingAlerts = [],
}: PromptAlertCreatorProps) {
  const [promptText, setPromptText] = useState('');
  const [confidenceThreshold, setConfidenceThreshold] = useState<ConfidenceThreshold>('medium');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [orchestrationMode, setOrchestrationMode] = useState<OrchestrationMode>('parallel');
  const [activatesAfter, setActivatesAfter] = useState<string>('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSave = useCallback(async () => {
    if (!promptText.trim()) {
      setError('Please describe what you want to be alerted about');
      return;
    }

    setSaving(true);
    setError(null);

    try {
      // Build reference state from current strategy state
      const referenceState: Partial<ReferenceStateSnapshot> = strategyState ? {
        delta: strategyState.delta,
        gamma: strategyState.gamma,
        theta: strategyState.theta,
        maxProfit: strategyState.maxProfit,
        maxLoss: strategyState.maxLoss,
        pnlAtSpot: strategyState.pnlAtSpot,
        spotPrice: strategyState.spotPrice,
        vix: strategyState.vix,
        dte: strategyState.dte,
        debit: strategyState.debit,
        strike: strategyState.strike,
        width: strategyState.width,
        side: strategyState.side,
      } : {};

      const input: CreatePromptAlertInput = {
        strategyId,
        promptText: promptText.trim(),
        confidenceThreshold,
        orchestrationMode,
        activatesAfterAlertId: activatesAfter || undefined,
        referenceState,
      };

      await onSave(input);
      onClose();

      // Reset form
      setPromptText('');
      setConfidenceThreshold('medium');
      setOrchestrationMode('parallel');
      setActivatesAfter('');
      setShowAdvanced(false);

    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create alert');
    } finally {
      setSaving(false);
    }
  }, [promptText, confidenceThreshold, orchestrationMode, activatesAfter, strategyId, strategyState, onSave, onClose]);

  const handleUseExample = useCallback((example: string) => {
    setPromptText(example);
  }, []);

  if (!isOpen) return null;

  return (
    <div className="prompt-alert-modal-overlay" onClick={onClose}>
      <div className="prompt-alert-modal" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="prompt-alert-header">
          <h2>Create Prompt Alert</h2>
          <span className="prompt-alert-strategy">{strategyLabel}</span>
          <button className="prompt-alert-close" onClick={onClose}>&times;</button>
        </div>

        {/* Main Content */}
        <div className="prompt-alert-content">
          {/* Prompt Input */}
          <div className="prompt-alert-section">
            <label className="prompt-alert-label">
              Describe what you want to be alerted about
            </label>
            <textarea
              className="prompt-alert-textarea"
              value={promptText}
              onChange={(e) => setPromptText(e.target.value)}
              placeholder="e.g., Alert me if gamma starts eating into my profit zone as we get closer to expiration. I want to protect at least 40% of the max profit."
              rows={4}
              autoFocus
            />
            <div className="prompt-alert-hint">
              Describe the condition in natural language. The AI will parse your intent and monitor for it.
            </div>
          </div>

          {/* Example Prompts */}
          <div className="prompt-alert-section">
            <label className="prompt-alert-label">Examples</label>
            <div className="prompt-alert-examples">
              {EXAMPLE_PROMPTS.map((example, i) => (
                <button
                  key={i}
                  className="prompt-alert-example"
                  onClick={() => handleUseExample(example)}
                  title="Click to use this example"
                >
                  {example.length > 80 ? example.substring(0, 77) + '...' : example}
                </button>
              ))}
            </div>
          </div>

          {/* Confidence Threshold */}
          <div className="prompt-alert-section">
            <label className="prompt-alert-label">AI Confidence Threshold</label>
            <div className="prompt-alert-options">
              {CONFIDENCE_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  className={`prompt-alert-option ${confidenceThreshold === option.value ? 'selected' : ''}`}
                  onClick={() => setConfidenceThreshold(option.value)}
                >
                  <span className="option-label">{option.label}</span>
                  <span className="option-desc">{option.description}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Advanced Options */}
          <div className="prompt-alert-section">
            <button
              className="prompt-alert-advanced-toggle"
              onClick={() => setShowAdvanced(!showAdvanced)}
            >
              {showAdvanced ? '- Hide' : '+ Show'} Advanced Options
            </button>

            {showAdvanced && (
              <div className="prompt-alert-advanced">
                {/* Orchestration Mode */}
                <div className="prompt-alert-subsection">
                  <label className="prompt-alert-label">Orchestration Mode</label>
                  <div className="prompt-alert-options vertical">
                    {ORCHESTRATION_OPTIONS.map((option) => (
                      <button
                        key={option.value}
                        className={`prompt-alert-option ${orchestrationMode === option.value ? 'selected' : ''}`}
                        onClick={() => setOrchestrationMode(option.value)}
                      >
                        <span className="option-label">{option.label}</span>
                        <span className="option-desc">{option.description}</span>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Sequential Dependency */}
                {orchestrationMode === 'sequential' && existingAlerts.length > 0 && (
                  <div className="prompt-alert-subsection">
                    <label className="prompt-alert-label">Activates After</label>
                    <select
                      className="prompt-alert-select"
                      value={activatesAfter}
                      onChange={(e) => setActivatesAfter(e.target.value)}
                    >
                      <option value="">Activate immediately</option>
                      {existingAlerts.map((alert) => (
                        <option key={alert.id} value={alert.id}>
                          {alert.promptText.length > 50
                            ? alert.promptText.substring(0, 47) + '...'
                            : alert.promptText}
                        </option>
                      ))}
                    </select>
                    <div className="prompt-alert-hint">
                      This alert will remain dormant until the selected alert accomplishes its objective.
                    </div>
                  </div>
                )}

                {/* Reference State Preview */}
                {strategyState && (
                  <div className="prompt-alert-subsection">
                    <label className="prompt-alert-label">Reference State (captured now)</label>
                    <div className="prompt-alert-reference">
                      <div className="reference-row">
                        <span className="reference-label">Delta:</span>
                        <span className="reference-value">{strategyState.delta?.toFixed(4) ?? 'N/A'}</span>
                      </div>
                      <div className="reference-row">
                        <span className="reference-label">Gamma:</span>
                        <span className="reference-value">{strategyState.gamma?.toFixed(6) ?? 'N/A'}</span>
                      </div>
                      <div className="reference-row">
                        <span className="reference-label">Theta:</span>
                        <span className="reference-value">{strategyState.theta?.toFixed(4) ?? 'N/A'}</span>
                      </div>
                      <div className="reference-row">
                        <span className="reference-label">Max Profit:</span>
                        <span className="reference-value">
                          {strategyState.maxProfit != null ? `$${strategyState.maxProfit.toFixed(2)}` : 'N/A'}
                        </span>
                      </div>
                      <div className="reference-row">
                        <span className="reference-label">P&L at Spot:</span>
                        <span className="reference-value">
                          {strategyState.pnlAtSpot != null ? `$${strategyState.pnlAtSpot.toFixed(2)}` : 'N/A'}
                        </span>
                      </div>
                      <div className="reference-row">
                        <span className="reference-label">DTE:</span>
                        <span className="reference-value">{strategyState.dte ?? 'N/A'}</span>
                      </div>
                      <div className="reference-row">
                        <span className="reference-label">Spot:</span>
                        <span className="reference-value">{strategyState.spotPrice?.toFixed(2) ?? 'N/A'}</span>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Error */}
          {error && (
            <div className="prompt-alert-error">
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="prompt-alert-footer">
          <button className="prompt-alert-btn cancel" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button
            className="prompt-alert-btn save"
            onClick={handleSave}
            disabled={saving || !promptText.trim()}
          >
            {saving ? 'Creating...' : 'Create Alert'}
          </button>
        </div>
      </div>
    </div>
  );
}
