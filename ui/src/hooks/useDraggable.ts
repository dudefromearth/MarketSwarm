/**
 * useDraggable - Hook to make any element draggable
 *
 * Usage:
 * const { position, dragHandleProps, containerStyle } = useDraggable({
 *   handleSelector: '.modal-header',
 *   initialCentered: true,
 * });
 *
 * <div style={containerStyle} {...dragHandleProps}>
 *   <div className="modal-header">Drag me</div>
 *   ...
 * </div>
 */

import { useState, useRef, useCallback, useEffect, type CSSProperties } from 'react';

interface Position {
  x: number;
  y: number;
}

interface UseDraggableOptions {
  /** CSS selector for the drag handle (e.g., '.modal-header'). If not set, whole element is draggable */
  handleSelector?: string;
  /** Start centered in viewport */
  initialCentered?: boolean;
  /** Initial position (overrides centered) */
  initialPosition?: Position;
  /** Constrain to viewport bounds */
  constrainToViewport?: boolean;
  /** Callback when dragging starts */
  onDragStart?: () => void;
  /** Callback when dragging ends */
  onDragEnd?: (position: Position) => void;
}

interface UseDraggableReturn {
  /** Current position */
  position: Position | null;
  /** Whether currently being dragged */
  isDragging: boolean;
  /** Props to spread on the container element */
  dragHandleProps: {
    onMouseDown: (e: React.MouseEvent) => void;
    ref: React.RefObject<HTMLDivElement | null>;
  };
  /** Style object to apply to container */
  containerStyle: CSSProperties;
  /** Reset position to initial/centered */
  resetPosition: () => void;
}

export function useDraggable(options: UseDraggableOptions = {}): UseDraggableReturn {
  const {
    handleSelector,
    initialCentered = true,
    initialPosition,
    constrainToViewport = true,
    onDragStart,
    onDragEnd,
  } = options;

  const containerRef = useRef<HTMLDivElement | null>(null);
  const [position, setPosition] = useState<Position | null>(initialPosition || null);
  const [isDragging, setIsDragging] = useState(false);
  const dragOffset = useRef<Position>({ x: 0, y: 0 });

  // Center on first render if requested
  useEffect(() => {
    if (initialCentered && !position && containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect();
      setPosition({
        x: (window.innerWidth - rect.width) / 2,
        y: Math.max(50, (window.innerHeight - rect.height) / 3),
      });
    }
  }, [initialCentered, position]);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (!containerRef.current) return;

    // Check if click is on the handle (if specified)
    if (handleSelector) {
      const target = e.target as HTMLElement;
      const handle = target.closest(handleSelector);
      if (!handle) return;
      // Don't drag when clicking buttons within handle
      if (target.closest('button')) return;
    }

    e.preventDefault();
    setIsDragging(true);
    onDragStart?.();

    const rect = containerRef.current.getBoundingClientRect();
    dragOffset.current = {
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    };
  }, [handleSelector, onDragStart]);

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!isDragging || !containerRef.current) return;

    let newX = e.clientX - dragOffset.current.x;
    let newY = e.clientY - dragOffset.current.y;

    if (constrainToViewport) {
      const rect = containerRef.current.getBoundingClientRect();
      const maxX = window.innerWidth - rect.width;
      const maxY = window.innerHeight - rect.height;
      newX = Math.max(0, Math.min(maxX, newX));
      newY = Math.max(0, Math.min(maxY, newY));
    }

    setPosition({ x: newX, y: newY });
  }, [isDragging, constrainToViewport]);

  const handleMouseUp = useCallback(() => {
    if (isDragging) {
      setIsDragging(false);
      onDragEnd?.(position || { x: 0, y: 0 });
    }
  }, [isDragging, position, onDragEnd]);

  // Global mouse event listeners
  useEffect(() => {
    if (isDragging) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
      return () => {
        window.removeEventListener('mousemove', handleMouseMove);
        window.removeEventListener('mouseup', handleMouseUp);
      };
    }
  }, [isDragging, handleMouseMove, handleMouseUp]);

  const resetPosition = useCallback(() => {
    if (initialPosition) {
      setPosition(initialPosition);
    } else if (containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect();
      setPosition({
        x: (window.innerWidth - rect.width) / 2,
        y: Math.max(50, (window.innerHeight - rect.height) / 3),
      });
    }
  }, [initialPosition]);

  const containerStyle: CSSProperties = {
    position: 'fixed',
    left: position?.x ?? '50%',
    top: position?.y ?? '20%',
    transform: position ? 'none' : 'translateX(-50%)',
    cursor: isDragging ? 'grabbing' : undefined,
    userSelect: isDragging ? 'none' : undefined,
  };

  return {
    position,
    isDragging,
    dragHandleProps: {
      onMouseDown: handleMouseDown,
      ref: containerRef,
    },
    containerStyle,
    resetPosition,
  };
}

export default useDraggable;
