import { useState, useRef, useEffect, useCallback } from 'react';
import { useChangelog, type ChangelogVersion, type ChangelogEntryType } from '../hooks/useChangelog';

const TYPE_COLORS: Record<ChangelogEntryType, string> = {
  feature: '#22c55e',
  enhancement: '#3b82f6',
  fix: '#f59e0b',
  change: '#a78bfa',
};

const TYPE_LABELS: Record<ChangelogEntryType, string> = {
  feature: 'New',
  enhancement: 'Improved',
  fix: 'Fixed',
  change: 'Changed',
};

export default function VersionIndicator() {
  const {
    versions,
    loading,
    unseenCount,
    markSeen,
    markAllSeen,
    isEntrySeen,
    latestVersion,
  } = useChangelog();

  const [isOpen, setIsOpen] = useState(false);
  const [expandedVersion, setExpandedVersion] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const hoverTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  // Expand the latest version by default when opening
  useEffect(() => {
    if (isOpen && versions.length > 0 && expandedVersion === null) {
      setExpandedVersion(versions[0].version);
    }
  }, [isOpen, versions, expandedVersion]);

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

  // Close on Escape
  useEffect(() => {
    if (!isOpen) return;
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setIsOpen(false);
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [isOpen]);

  // Clean up hover timers
  useEffect(() => {
    return () => {
      Object.values(hoverTimers.current).forEach(clearTimeout);
    };
  }, []);

  const handleEntryHover = useCallback((id: string) => {
    if (hoverTimers.current[id]) return;
    hoverTimers.current[id] = setTimeout(() => {
      markSeen(id);
      delete hoverTimers.current[id];
    }, 1000);
  }, [markSeen]);

  const handleEntryLeave = useCallback((id: string) => {
    if (hoverTimers.current[id]) {
      clearTimeout(hoverTimers.current[id]);
      delete hoverTimers.current[id];
    }
  }, []);

  if (loading) return null;

  return (
    <div className="version-indicator" ref={containerRef}>
      <button
        className="version-indicator-btn"
        onClick={() => setIsOpen(!isOpen)}
        title="What's new"
      >
        <span className="version-label">v{latestVersion}</span>
        {unseenCount > 0 && <span className="version-unseen-dot" />}
      </button>

      {isOpen && (
        <div className="version-dropdown">
          <div className="version-dropdown-header">
            <span className="version-dropdown-title">What's New</span>
            {unseenCount > 0 && (
              <button className="version-mark-all" onClick={markAllSeen}>
                Mark all read
              </button>
            )}
          </div>
          <div className="version-dropdown-list">
            {versions.map((v: ChangelogVersion) => {
              const isExpanded = expandedVersion === v.version;
              const versionUnseen = v.entries.filter(e => !isEntrySeen(e.id)).length;
              return (
                <div key={v.version} className="version-group">
                  <button
                    className="version-group-header"
                    onClick={() => setExpandedVersion(isExpanded ? null : v.version)}
                  >
                    <span className="version-group-label">
                      v{v.version}
                      {versionUnseen > 0 && <span className="version-group-dot" />}
                    </span>
                    <span className="version-group-date">{v.date}</span>
                    <span className={`version-group-chevron ${isExpanded ? 'expanded' : ''}`}>
                      ›
                    </span>
                  </button>
                  {isExpanded && (
                    <div className="version-entries">
                      {v.entries.map(entry => {
                        const seen = isEntrySeen(entry.id);
                        return (
                          <div
                            key={entry.id}
                            className={`version-entry ${seen ? 'seen' : 'unseen'}`}
                            onMouseEnter={() => !seen && handleEntryHover(entry.id)}
                            onMouseLeave={() => handleEntryLeave(entry.id)}
                          >
                            <span
                              className="version-entry-type"
                              style={{ background: TYPE_COLORS[entry.type] }}
                            >
                              {TYPE_LABELS[entry.type]}
                            </span>
                            <div className="version-entry-content">
                              <span className="version-entry-title">
                                {entry.title}
                                {!seen && <span className="version-entry-dot" />}
                              </span>
                              <span className="version-entry-desc">{entry.description}</span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      <style>{`
        .version-indicator {
          position: relative;
          display: inline-flex;
          align-items: center;
        }

        .version-indicator-btn {
          background: transparent;
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 4px;
          padding: 3px 8px;
          cursor: pointer;
          display: flex;
          align-items: center;
          gap: 6px;
          transition: border-color 0.2s;
        }

        .version-indicator-btn:hover {
          border-color: rgba(255, 255, 255, 0.2);
        }

        .version-label {
          font-family: 'SF Mono', 'Fira Code', 'Fira Mono', monospace;
          font-size: 11px;
          color: #6b7280;
          letter-spacing: 0.02em;
        }

        .version-unseen-dot {
          width: 7px;
          height: 7px;
          border-radius: 50%;
          background: #3b82f6;
          flex-shrink: 0;
        }

        .version-dropdown {
          position: absolute;
          top: calc(100% + 8px);
          left: 0;
          width: 360px;
          max-height: 480px;
          background: #1a1a1f;
          border: 1px solid #2a2a35;
          border-radius: 8px;
          box-shadow: 0 10px 25px rgba(0, 0, 0, 0.5);
          z-index: 1000;
          overflow: hidden;
          display: flex;
          flex-direction: column;
        }

        .version-dropdown-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 12px 16px;
          border-bottom: 1px solid #2a2a35;
        }

        .version-dropdown-title {
          font-weight: 600;
          color: #e5e7eb;
          font-size: 14px;
        }

        .version-mark-all {
          background: transparent;
          border: none;
          color: #3b82f6;
          font-size: 12px;
          cursor: pointer;
          padding: 4px 8px;
          border-radius: 4px;
        }

        .version-mark-all:hover {
          background: rgba(59, 130, 246, 0.1);
        }

        .version-dropdown-list {
          overflow-y: auto;
          flex: 1;
        }

        .version-group {
          border-bottom: 1px solid #2a2a35;
        }

        .version-group:last-child {
          border-bottom: none;
        }

        .version-group-header {
          width: 100%;
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 10px 16px;
          background: transparent;
          border: none;
          cursor: pointer;
          color: #e5e7eb;
          font-size: 13px;
          transition: background 0.15s;
        }

        .version-group-header:hover {
          background: rgba(255, 255, 255, 0.03);
        }

        .version-group-label {
          font-weight: 600;
          font-family: 'SF Mono', 'Fira Code', 'Fira Mono', monospace;
          font-size: 12px;
          display: flex;
          align-items: center;
          gap: 6px;
        }

        .version-group-dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: #3b82f6;
        }

        .version-group-date {
          color: #6b7280;
          font-size: 11px;
          margin-left: auto;
        }

        .version-group-chevron {
          color: #6b7280;
          font-size: 16px;
          transition: transform 0.2s;
          transform: rotate(0deg);
        }

        .version-group-chevron.expanded {
          transform: rotate(90deg);
        }

        .version-entries {
          padding: 0 8px 8px;
        }

        .version-entry {
          display: flex;
          align-items: flex-start;
          gap: 10px;
          padding: 8px;
          border-radius: 6px;
          transition: background 0.15s;
        }

        .version-entry:hover {
          background: rgba(255, 255, 255, 0.03);
        }

        .version-entry.unseen {
          background: rgba(59, 130, 246, 0.04);
        }

        .version-entry-type {
          font-size: 10px;
          font-weight: 600;
          color: #fff;
          padding: 2px 6px;
          border-radius: 3px;
          white-space: nowrap;
          margin-top: 1px;
          flex-shrink: 0;
        }

        .version-entry-content {
          display: flex;
          flex-direction: column;
          gap: 2px;
          min-width: 0;
        }

        .version-entry-title {
          color: #e5e7eb;
          font-size: 13px;
          font-weight: 500;
          display: flex;
          align-items: center;
          gap: 6px;
        }

        .version-entry-dot {
          width: 5px;
          height: 5px;
          border-radius: 50%;
          background: #3b82f6;
          flex-shrink: 0;
        }

        .version-entry-desc {
          color: #9ca3af;
          font-size: 12px;
          line-height: 1.4;
        }
      `}</style>
    </div>
  );
}
