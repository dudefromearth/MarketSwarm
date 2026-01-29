import { useState, useRef, useEffect } from 'react';
import type { ReactNode } from 'react';
import { getTooltip } from './tooltips';
import type { TooltipContent } from './tooltips';

interface TooltipProps {
  /** Key to look up in centralized tooltips, or inline TooltipContent */
  content: string | TooltipContent;
  /** The element that triggers the tooltip */
  children: ReactNode;
  /** Position of tooltip relative to trigger */
  position?: 'top' | 'bottom' | 'left' | 'right';
  /** Additional class for the wrapper */
  className?: string;
}

export function Tooltip({ content, children, position = 'top', className = '' }: TooltipProps) {
  const [visible, setVisible] = useState(false);
  const [coords, setCoords] = useState({ top: 0, left: 0 });
  const triggerRef = useRef<HTMLSpanElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);

  // Resolve content from key or use inline content
  const tooltipContent: TooltipContent = typeof content === 'string'
    ? getTooltip(content)
    : content;

  useEffect(() => {
    if (visible && triggerRef.current && tooltipRef.current) {
      const triggerRect = triggerRef.current.getBoundingClientRect();
      const tooltipRect = tooltipRef.current.getBoundingClientRect();

      let top = 0;
      let left = 0;

      switch (position) {
        case 'top':
          top = triggerRect.top - tooltipRect.height - 10;
          left = triggerRect.left + (triggerRect.width / 2) - (tooltipRect.width / 2);
          break;
        case 'bottom':
          top = triggerRect.bottom + 10;
          left = triggerRect.left + (triggerRect.width / 2) - (tooltipRect.width / 2);
          break;
        case 'left':
          top = triggerRect.top + (triggerRect.height / 2) - (tooltipRect.height / 2);
          left = triggerRect.left - tooltipRect.width - 10;
          break;
        case 'right':
          top = triggerRect.top + (triggerRect.height / 2) - (tooltipRect.height / 2);
          left = triggerRect.right + 10;
          break;
      }

      // Keep tooltip within viewport
      const padding = 10;
      if (left < padding) left = padding;
      if (left + tooltipRect.width > window.innerWidth - padding) {
        left = window.innerWidth - tooltipRect.width - padding;
      }
      if (top < padding) top = padding;
      if (top + tooltipRect.height > window.innerHeight - padding) {
        top = window.innerHeight - tooltipRect.height - padding;
      }

      setCoords({ top, left });
    }
  }, [visible, position]);

  return (
    <>
      <span
        ref={triggerRef}
        className={`tooltip-trigger ${className}`}
        onMouseEnter={() => setVisible(true)}
        onMouseLeave={() => setVisible(false)}
      >
        {children}
      </span>
      {visible && (
        <div
          ref={tooltipRef}
          className={`tooltip-popup tooltip-${position}`}
          style={{ top: coords.top, left: coords.left }}
        >
          {tooltipContent.title && (
            <div className="tooltip-title">{tooltipContent.title}</div>
          )}
          <div className="tooltip-description">{tooltipContent.description}</div>
          {tooltipContent.link && (
            <a
              href={tooltipContent.link.url}
              className="tooltip-link"
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
            >
              {tooltipContent.link.text} →
            </a>
          )}
        </div>
      )}
    </>
  );
}

export default Tooltip;
