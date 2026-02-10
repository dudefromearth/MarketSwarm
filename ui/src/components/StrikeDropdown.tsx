/**
 * StrikeDropdown - Virtualized strike picker for option legs
 *
 * Features:
 * - Opens centered on ATM or current value
 * - Shows +/- 6-7 strikes visible at a time
 * - Lazy loads more strikes on scroll
 * - Type to jump to a specific strike
 */

import { useState, useRef, useEffect, useCallback, useMemo } from 'react';

interface StrikeDropdownProps {
  value: number;
  onChange: (strike: number) => void;
  atmStrike?: number;      // Current ATM strike for centering
  minStrike?: number;      // Minimum available strike
  maxStrike?: number;      // Maximum available strike
  strikeStep?: number;     // Step between strikes (default 5)
  className?: string;
  disabled?: boolean;
}

// Number of strikes to show above and below center
const VISIBLE_BUFFER = 3;
// Total visible strikes (buffer * 2 + center)
const VISIBLE_COUNT = VISIBLE_BUFFER * 2 + 1;
// Strike item height in pixels
const STRIKE_HEIGHT = 32;
// Extra strikes to load beyond visible for smooth scrolling
const LOAD_BUFFER = 10;

export default function StrikeDropdown({
  value,
  onChange,
  atmStrike = 5900,
  minStrike = 4000,
  maxStrike = 7000,
  strikeStep = 5,
  className = '',
  disabled = false,
}: StrikeDropdownProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [inputValue, setInputValue] = useState(value.toString());
  const [loadedRange, setLoadedRange] = useState({ min: 0, max: 0 });
  const containerRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Generate all possible strikes
  const allStrikes = useMemo(() => {
    const strikes: number[] = [];
    for (let s = minStrike; s <= maxStrike; s += strikeStep) {
      strikes.push(s);
    }
    return strikes;
  }, [minStrike, maxStrike, strikeStep]);

  // Find index of a strike value
  const getStrikeIndex = useCallback((strike: number) => {
    return Math.round((strike - minStrike) / strikeStep);
  }, [minStrike, strikeStep]);

  // Initialize loaded range around current value
  useEffect(() => {
    const centerIndex = getStrikeIndex(value || atmStrike);
    setLoadedRange({
      min: Math.max(0, centerIndex - VISIBLE_BUFFER - LOAD_BUFFER),
      max: Math.min(allStrikes.length - 1, centerIndex + VISIBLE_BUFFER + LOAD_BUFFER),
    });
  }, [value, atmStrike, allStrikes.length, getStrikeIndex]);

  // Sync input value when external value changes
  useEffect(() => {
    if (!isOpen) {
      setInputValue(value.toString());
    }
  }, [value, isOpen]);

  // Scroll to center on current value when opening
  useEffect(() => {
    if (isOpen && listRef.current) {
      const centerIndex = getStrikeIndex(value || atmStrike);
      const scrollPosition = (centerIndex - VISIBLE_BUFFER) * STRIKE_HEIGHT;
      listRef.current.scrollTop = Math.max(0, scrollPosition);
    }
  }, [isOpen, value, atmStrike, getStrikeIndex]);

  // Close on click outside
  useEffect(() => {
    if (!isOpen) return;

    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  // Handle scroll to load more strikes
  const handleScroll = useCallback(() => {
    if (!listRef.current) return;

    const scrollTop = listRef.current.scrollTop;
    const visibleStartIndex = Math.floor(scrollTop / STRIKE_HEIGHT);
    const visibleEndIndex = visibleStartIndex + VISIBLE_COUNT;

    // Expand loaded range if approaching edges
    if (visibleStartIndex <= loadedRange.min + 2) {
      setLoadedRange(prev => ({
        ...prev,
        min: Math.max(0, prev.min - LOAD_BUFFER),
      }));
    }
    if (visibleEndIndex >= loadedRange.max - 2) {
      setLoadedRange(prev => ({
        ...prev,
        max: Math.min(allStrikes.length - 1, prev.max + LOAD_BUFFER),
      }));
    }
  }, [loadedRange, allStrikes.length]);

  // Handle input change - jump to typed strike
  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = e.target.value;
    setInputValue(newValue);

    // If valid number, scroll to it
    const numValue = parseFloat(newValue);
    if (!isNaN(numValue) && numValue >= minStrike && numValue <= maxStrike) {
      // Snap to nearest valid strike
      const snappedStrike = Math.round(numValue / strikeStep) * strikeStep;
      const targetIndex = getStrikeIndex(snappedStrike);

      // Expand loaded range to include this strike
      setLoadedRange(prev => ({
        min: Math.min(prev.min, Math.max(0, targetIndex - LOAD_BUFFER)),
        max: Math.max(prev.max, Math.min(allStrikes.length - 1, targetIndex + LOAD_BUFFER)),
      }));

      // Scroll to the strike
      if (listRef.current && isOpen) {
        const scrollPosition = (targetIndex - VISIBLE_BUFFER) * STRIKE_HEIGHT;
        listRef.current.scrollTop = Math.max(0, scrollPosition);
      }
    }
  };

  // Handle input blur - commit value
  const handleInputBlur = () => {
    const numValue = parseFloat(inputValue);
    if (!isNaN(numValue) && numValue >= minStrike && numValue <= maxStrike) {
      // Snap to nearest valid strike
      const snappedStrike = Math.round(numValue / strikeStep) * strikeStep;
      onChange(snappedStrike);
      setInputValue(snappedStrike.toString());
    } else {
      // Reset to current value
      setInputValue(value.toString());
    }
  };

  // Handle input keydown
  const handleInputKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleInputBlur();
      setIsOpen(false);
    } else if (e.key === 'Escape') {
      setInputValue(value.toString());
      setIsOpen(false);
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (!isOpen) {
        setIsOpen(true);
      } else {
        const newStrike = Math.min(maxStrike, value + strikeStep);
        onChange(newStrike);
        setInputValue(newStrike.toString());
      }
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (!isOpen) {
        setIsOpen(true);
      } else {
        const newStrike = Math.max(minStrike, value - strikeStep);
        onChange(newStrike);
        setInputValue(newStrike.toString());
      }
    }
  };

  // Handle strike selection
  const handleSelectStrike = (strike: number) => {
    onChange(strike);
    setInputValue(strike.toString());
    setIsOpen(false);
  };

  // Toggle dropdown
  const handleToggle = () => {
    if (disabled) return;
    setIsOpen(!isOpen);
    if (!isOpen) {
      // Focus input when opening
      setTimeout(() => inputRef.current?.select(), 0);
    }
  };

  // Get loaded strikes for rendering
  const loadedStrikes = useMemo(() => {
    return allStrikes.slice(loadedRange.min, loadedRange.max + 1);
  }, [allStrikes, loadedRange]);

  // Calculate spacer heights for virtual scrolling
  const topSpacerHeight = loadedRange.min * STRIKE_HEIGHT;
  const bottomSpacerHeight = (allStrikes.length - 1 - loadedRange.max) * STRIKE_HEIGHT;

  return (
    <div
      className={`strike-dropdown ${className} ${isOpen ? 'open' : ''} ${disabled ? 'disabled' : ''}`}
      ref={containerRef}
    >
      <div className="strike-dropdown-trigger" onClick={handleToggle}>
        <input
          ref={inputRef}
          type="text"
          className="strike-input"
          value={inputValue}
          onChange={handleInputChange}
          onBlur={handleInputBlur}
          onKeyDown={handleInputKeyDown}
          onFocus={() => setIsOpen(true)}
          disabled={disabled}
        />
        <span className="strike-dropdown-arrow">▼</span>
      </div>

      {isOpen && (
        <div className="strike-dropdown-list" ref={listRef} onScroll={handleScroll}>
          {/* Top spacer for virtual scrolling */}
          <div style={{ height: topSpacerHeight }} />

          {loadedStrikes.map((strike) => {
            const isATM = strike === atmStrike;
            const isSelected = strike === value;
            return (
              <div
                key={strike}
                className={`strike-option ${isSelected ? 'selected' : ''} ${isATM ? 'atm' : ''}`}
                onClick={() => handleSelectStrike(strike)}
                style={{ height: STRIKE_HEIGHT }}
              >
                <span className="strike-value">{strike}</span>
                {isATM && <span className="atm-badge">ATM</span>}
              </div>
            );
          })}

          {/* Bottom spacer for virtual scrolling */}
          <div style={{ height: bottomSpacerHeight }} />
        </div>
      )}

      <style>{`
        .strike-dropdown {
          position: relative;
          display: inline-block;
          width: 90px;
        }

        .strike-dropdown.disabled {
          opacity: 0.5;
          pointer-events: none;
        }

        .strike-dropdown-trigger {
          display: flex;
          align-items: center;
          background: #1f2937;
          border: 1px solid #374151;
          border-radius: 4px;
          cursor: pointer;
        }

        .strike-dropdown.open .strike-dropdown-trigger {
          border-color: #3b82f6;
        }

        .strike-input {
          flex: 1;
          background: transparent;
          border: none;
          color: #e5e7eb;
          padding: 6px 8px;
          font-size: 13px;
          width: 100%;
          min-width: 0;
          font-family: inherit;
        }

        .strike-input:focus {
          outline: none;
        }

        .strike-dropdown-arrow {
          color: #6b7280;
          font-size: 8px;
          padding: 0 8px;
          transition: transform 0.2s;
        }

        .strike-dropdown.open .strike-dropdown-arrow {
          transform: rotate(180deg);
        }

        .strike-dropdown-list {
          position: absolute;
          top: 100%;
          left: 0;
          right: 0;
          margin-top: 4px;
          background: #1f2937;
          border: 1px solid #374151;
          border-radius: 4px;
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
          z-index: 100;
          max-height: ${VISIBLE_COUNT * STRIKE_HEIGHT + 2}px;
          overflow-y: auto;
          overflow-x: hidden;
        }

        .strike-option {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 0 10px;
          cursor: pointer;
          transition: background 0.1s;
          color: #d1d5db;
          font-size: 13px;
        }

        .strike-option:hover {
          background: #374151;
        }

        .strike-option.selected {
          background: #3b82f6;
          color: white;
        }

        .strike-option.atm {
          font-weight: 500;
        }

        .strike-option.atm:not(.selected) {
          color: #22c55e;
        }

        .atm-badge {
          font-size: 9px;
          background: rgba(34, 197, 94, 0.2);
          color: #22c55e;
          padding: 1px 4px;
          border-radius: 3px;
          font-weight: 600;
        }

        .strike-option.selected .atm-badge {
          background: rgba(255, 255, 255, 0.2);
          color: white;
        }

        /* Scrollbar styling */
        .strike-dropdown-list::-webkit-scrollbar {
          width: 6px;
        }

        .strike-dropdown-list::-webkit-scrollbar-track {
          background: transparent;
        }

        .strike-dropdown-list::-webkit-scrollbar-thumb {
          background: #4b5563;
          border-radius: 3px;
        }

        .strike-dropdown-list::-webkit-scrollbar-thumb:hover {
          background: #6b7280;
        }

        /* Light theme */
        [data-theme="light"] .strike-dropdown-trigger {
          background: #f5f5f7;
          border-color: #d1d1d6;
        }

        [data-theme="light"] .strike-dropdown.open .strike-dropdown-trigger {
          border-color: #007aff;
        }

        [data-theme="light"] .strike-input {
          color: #1d1d1f;
        }

        [data-theme="light"] .strike-dropdown-arrow {
          color: #86868b;
        }

        [data-theme="light"] .strike-dropdown-list {
          background: #ffffff;
          border-color: #d1d1d6;
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
        }

        [data-theme="light"] .strike-option {
          color: #1d1d1f;
        }

        [data-theme="light"] .strike-option:hover {
          background: #f0f0f2;
        }

        [data-theme="light"] .strike-option.selected {
          background: #007aff;
          color: white;
        }

        [data-theme="light"] .strike-dropdown-list::-webkit-scrollbar-thumb {
          background: #c7c7cc;
        }

        [data-theme="light"] .strike-dropdown-list::-webkit-scrollbar-thumb:hover {
          background: #aeaeb2;
        }
      `}</style>
    </div>
  );
}
