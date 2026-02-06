// ui/src/components/FloatingDialog.tsx
// Reusable floating dialog/modal component

import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
  width?: string | number;
  maxHeight?: string;
  showBackdrop?: boolean;
  closeOnBackdropClick?: boolean;
}

export default function FloatingDialog({
  isOpen,
  onClose,
  title,
  children,
  width = '600px',
  maxHeight = '80vh',
  showBackdrop: _showBackdrop = true,
  closeOnBackdropClick = true,
}: Props) {
  const widthValue = typeof width === 'number' ? `${width}px` : width;
  const dialogRef = useRef<HTMLDivElement>(null);

  // Close on escape key
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    document.addEventListener('keydown', handleEsc);
    return () => document.removeEventListener('keydown', handleEsc);
  }, [isOpen, onClose]);

  // Close on click outside (if enabled)
  useEffect(() => {
    if (!closeOnBackdropClick) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (dialogRef.current && !dialogRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen, onClose, closeOnBackdropClick]);

  if (!isOpen) return null;

  return (
    <div className="floating-dialog-overlay">
      <div
        ref={dialogRef}
        className="floating-dialog"
        style={{ width: widthValue, maxHeight }}
      >
        {title && (
          <div className="floating-dialog-header">
            <h2>{title}</h2>
            <button className="close-btn" onClick={onClose}>
              &times;
            </button>
          </div>
        )}
        <div className="floating-dialog-content">{children}</div>
      </div>
      <style>{`
        .floating-dialog-overlay {
          position: fixed;
          inset: 0;
          background: rgba(0, 0, 0, 0.6);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 1000;
          backdrop-filter: blur(2px);
        }
        .floating-dialog {
          background: #1a1a1f;
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 12px;
          box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
          overflow: hidden;
          display: flex;
          flex-direction: column;
        }
        .floating-dialog-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 16px 20px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.08);
          background: rgba(255, 255, 255, 0.02);
        }
        .floating-dialog-header h2 {
          margin: 0;
          font-size: 16px;
          font-weight: 600;
          color: #f1f5f9;
        }
        .floating-dialog-header .close-btn {
          background: none;
          border: none;
          color: #71717a;
          font-size: 24px;
          cursor: pointer;
          padding: 0;
          line-height: 1;
          transition: color 0.2s;
        }
        .floating-dialog-header .close-btn:hover {
          color: #f1f5f9;
        }
        .floating-dialog-content {
          padding: 20px;
          overflow-y: auto;
          flex: 1;
        }
      `}</style>
    </div>
  );
}
