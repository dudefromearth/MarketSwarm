/**
 * ErrorBoundary - Catches React rendering errors gracefully
 *
 * Features:
 * - Prevents black screen crashes
 * - Shows user-friendly error message
 * - Provides "Report Issue" functionality
 * - Allows recovery via retry
 */

import { Component, ReactNode } from 'react';

interface ErrorInfo {
  componentStack: string;
}

interface ErrorReport {
  message: string;
  stack?: string;
  componentStack?: string;
  timestamp: string;
  url: string;
  userAgent: string;
}

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
  componentName?: string;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
  reported: boolean;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      reported: false,
    };
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    // Log to console for debugging
    console.error('[ErrorBoundary] Caught error:', error);
    console.error('[ErrorBoundary] Component stack:', errorInfo.componentStack);

    this.setState({ errorInfo });

    // Call optional error handler
    this.props.onError?.(error, errorInfo);

    // Store error for potential reporting
    const errorReport: ErrorReport = {
      message: error.message,
      stack: error.stack,
      componentStack: errorInfo.componentStack,
      timestamp: new Date().toISOString(),
      url: window.location.href,
      userAgent: navigator.userAgent,
    };

    // Store in sessionStorage for the error report
    try {
      const existingErrors = JSON.parse(sessionStorage.getItem('ms_errors') || '[]');
      existingErrors.push(errorReport);
      // Keep only last 10 errors
      if (existingErrors.length > 10) existingErrors.shift();
      sessionStorage.setItem('ms_errors', JSON.stringify(existingErrors));
    } catch {
      // Ignore storage errors
    }
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null, errorInfo: null, reported: false });
  };

  handleReport = async () => {
    const { error, errorInfo } = this.state;
    if (!error) return;

    const report: ErrorReport = {
      message: error.message,
      stack: error.stack,
      componentStack: errorInfo?.componentStack,
      timestamp: new Date().toISOString(),
      url: window.location.href,
      userAgent: navigator.userAgent,
    };

    // Copy to clipboard for easy reporting
    try {
      const reportText = `
MarketSwarm Error Report
========================
Time: ${report.timestamp}
URL: ${report.url}

Error: ${report.message}

Stack Trace:
${report.stack || 'N/A'}

Component Stack:
${report.componentStack || 'N/A'}

User Agent: ${report.userAgent}
`.trim();

      await navigator.clipboard.writeText(reportText);
      this.setState({ reported: true });

      // Also try to send to server (non-blocking)
      fetch('/api/logs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          type: 'error',
          message: `UI Error: ${report.message}`,
          metadata: report,
        }),
      }).catch(() => {
        // Ignore - clipboard copy is the primary mechanism
      });

    } catch {
      // Fallback: show alert with error details
      alert(`Error details:\n\n${error.message}\n\nPlease screenshot this and report to support.`);
    }
  };

  render() {
    const { hasError, error, reported } = this.state;
    const { children, fallback, componentName } = this.props;

    if (hasError) {
      // Custom fallback provided
      if (fallback) {
        return fallback;
      }

      // Default error UI
      return (
        <div className="error-boundary-container">
          <div className="error-boundary-content">
            <div className="error-boundary-icon">⚠️</div>
            <h3 className="error-boundary-title">Something went wrong</h3>
            <p className="error-boundary-message">
              {componentName ? `The ${componentName} encountered an error.` : 'A component encountered an error.'}
            </p>
            {error && (
              <div className="error-boundary-details">
                <code>{error.message}</code>
              </div>
            )}
            <div className="error-boundary-actions">
              <button className="error-boundary-btn retry" onClick={this.handleRetry}>
                Try Again
              </button>
              <button
                className={`error-boundary-btn report ${reported ? 'reported' : ''}`}
                onClick={this.handleReport}
                disabled={reported}
              >
                {reported ? '✓ Copied to Clipboard' : 'Copy Error Report'}
              </button>
            </div>
            <p className="error-boundary-help">
              If this persists, please report the error to support.
            </p>
          </div>
        </div>
      );
    }

    return children;
  }
}

/**
 * Higher-order component to wrap any component with error boundary
 */
export function withErrorBoundary<P extends object>(
  WrappedComponent: React.ComponentType<P>,
  componentName?: string
) {
  return function WithErrorBoundary(props: P) {
    return (
      <ErrorBoundary componentName={componentName}>
        <WrappedComponent {...props} />
      </ErrorBoundary>
    );
  };
}

export default ErrorBoundary;
