/**
 * PromptInput - Primary Prompt-First Alert Creation Interface
 *
 * Natural language is the universal entry point for creating alerts.
 * The prompt is parsed by AI into evaluator specs on the backend.
 *
 * From alert-mgr.md spec v1:
 * - Prompt-first creation
 * - Scope selection (position/symbol/portfolio/workflow/behavioral)
 * - Severity ladder (inform/notify/warn/block)
 */

import { useState, useCallback, useRef } from 'react';
import type { KeyboardEvent } from 'react';
import type { AlertScope, AlertSeverity } from '../../types/alerts';
import { getScopeStyle, getSeverityStyle } from '../../types/alerts';

interface PromptInputProps {
  onSubmit: (prompt: string, scope: AlertScope, severity: AlertSeverity) => Promise<void>;
  isCreating: boolean;
}

const SCOPE_OPTIONS: { value: AlertScope; label: string; hint: string }[] = [
  { value: 'symbol', label: 'Symbol', hint: 'Market price/level alerts' },
  { value: 'position', label: 'Position', hint: 'Tied to a specific position' },
  { value: 'portfolio', label: 'Portfolio', hint: 'Aggregate posture alerts' },
  { value: 'workflow', label: 'Workflow', hint: 'Process triggers' },
  { value: 'behavioral', label: 'Behavioral', hint: 'Trading pattern alerts' },
];

const SEVERITY_OPTIONS: { value: AlertSeverity; label: string; hint: string }[] = [
  { value: 'inform', label: 'Inform', hint: 'Passive awareness' },
  { value: 'notify', label: 'Notify', hint: 'Important signal' },
  { value: 'warn', label: 'Warn', hint: 'Risk increasing' },
  { value: 'block', label: 'Block', hint: 'Policy violation' },
];

const EXAMPLE_PROMPTS: Record<AlertScope, string[]> = {
  symbol: [
    'Alert when SPX breaks 6000',
    'Notify if VIX spikes above 20',
    'Warn when SPX approaches yesterday high',
  ],
  position: [
    'Alert if this butterfly hits +3R',
    'Warn when breakeven is threatened',
    'Notify if theta decay exceeds expectations',
  ],
  portfolio: [
    'Warn if delta exceeds +50',
    'Alert when portfolio heat exceeds 5%',
    'Block if daily loss exceeds 2%',
  ],
  workflow: [
    'Remind me to journal after closing a trade',
    'Alert when routine checklist incomplete',
    'Notify at 9:15 to check VIX regime',
  ],
  behavioral: [
    'Notice if I revenge trade after loss',
    'Warn if trading outside my hours',
    'Alert if trade count exceeds daily limit',
  ],
};

export default function PromptInput({ onSubmit, isCreating }: PromptInputProps) {
  const [prompt, setPrompt] = useState('');
  const [scope, setScope] = useState<AlertScope>('symbol');
  const [severity, setSeverity] = useState<AlertSeverity>('notify');
  const [showScopeMenu, setShowScopeMenu] = useState(false);
  const [showSeverityMenu, setShowSeverityMenu] = useState(false);
  const [isFocused, setIsFocused] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const scopeStyle = getScopeStyle(scope);
  const severityStyle = getSeverityStyle(severity);

  const handleSubmit = useCallback(async () => {
    const trimmed = prompt.trim();
    if (!trimmed || isCreating) return;

    await onSubmit(trimmed, scope, severity);
    setPrompt('');
  }, [prompt, scope, severity, isCreating, onSubmit]);

  const handleKeyDown = useCallback((e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }, [handleSubmit]);

  const handleExampleClick = useCallback((example: string) => {
    setPrompt(example);
    inputRef.current?.focus();
  }, []);

  const examples = EXAMPLE_PROMPTS[scope];
  const showExamples = isFocused && !prompt.trim() && examples.length > 0;

  return (
    <div className="prompt-input-container">
      <div className="prompt-input-header">
        <span className="prompt-input-label">Create Alert</span>
        <div className="prompt-input-options">
          {/* Scope Selector */}
          <div className="prompt-option-group">
            <button
              className="prompt-option-btn"
              onClick={() => setShowScopeMenu(!showScopeMenu)}
              style={{
                background: scopeStyle.bgColor,
                color: scopeStyle.color,
                borderColor: scopeStyle.color,
              }}
            >
              {SCOPE_OPTIONS.find((s) => s.value === scope)?.label}
              <span className="dropdown-arrow">▼</span>
            </button>
            {showScopeMenu && (
              <div className="prompt-option-menu">
                {SCOPE_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    className={`option-item ${scope === opt.value ? 'selected' : ''}`}
                    onClick={() => {
                      setScope(opt.value);
                      setShowScopeMenu(false);
                    }}
                  >
                    <span className="option-label">{opt.label}</span>
                    <span className="option-hint">{opt.hint}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Severity Selector */}
          <div className="prompt-option-group">
            <button
              className="prompt-option-btn"
              onClick={() => setShowSeverityMenu(!showSeverityMenu)}
              style={{
                background: severityStyle.bgColor,
                color: severityStyle.color,
                borderColor: severityStyle.color,
              }}
            >
              {SEVERITY_OPTIONS.find((s) => s.value === severity)?.label}
              <span className="dropdown-arrow">▼</span>
            </button>
            {showSeverityMenu && (
              <div className="prompt-option-menu">
                {SEVERITY_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    className={`option-item ${severity === opt.value ? 'selected' : ''}`}
                    onClick={() => {
                      setSeverity(opt.value);
                      setShowSeverityMenu(false);
                    }}
                  >
                    <span className="option-label">{opt.label}</span>
                    <span className="option-hint">{opt.hint}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className={`prompt-input-wrapper ${isFocused ? 'focused' : ''}`}>
        <textarea
          ref={inputRef}
          className="prompt-input"
          placeholder="Describe your alert in natural language..."
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => setIsFocused(true)}
          onBlur={() => setTimeout(() => setIsFocused(false), 200)}
          rows={2}
          disabled={isCreating}
        />
        <button
          className="prompt-submit-btn"
          onClick={handleSubmit}
          disabled={!prompt.trim() || isCreating}
        >
          {isCreating ? (
            <span className="spinner" />
          ) : (
            <span className="submit-icon">→</span>
          )}
        </button>
      </div>

      {/* Example prompts */}
      {showExamples && (
        <div className="prompt-examples">
          <span className="examples-label">Examples:</span>
          {examples.map((example, i) => (
            <button
              key={i}
              className="example-chip"
              onClick={() => handleExampleClick(example)}
            >
              {example}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
