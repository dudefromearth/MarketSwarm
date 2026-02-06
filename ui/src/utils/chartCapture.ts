/**
 * Chart Capture Utility
 *
 * Captures chart screenshots for AI analysis.
 * Works with Lightweight Charts API.
 */

import type { IChartApi } from 'lightweight-charts';

/**
 * Capture a screenshot of a Lightweight Chart.
 *
 * @param chartApi - The chart API instance from lightweight-charts
 * @returns Base64-encoded PNG image data (without data:image/png;base64, prefix)
 */
export function captureChart(chartApi: IChartApi): string | null {
  try {
    // Lightweight Charts has takeScreenshot() method
    const canvas = chartApi.takeScreenshot();
    if (!canvas) {
      console.error('[chartCapture] takeScreenshot() returned null');
      return null;
    }

    // Convert to data URL and remove prefix
    const dataUrl = canvas.toDataURL('image/png');
    const base64 = dataUrl.split(',')[1];
    return base64;
  } catch (error) {
    console.error('[chartCapture] Failed to capture chart:', error);
    return null;
  }
}

/**
 * Capture a screenshot of a DOM element.
 *
 * @param element - The DOM element to capture
 * @returns Base64-encoded PNG image data
 */
export async function captureElement(element: HTMLElement): Promise<string | null> {
  try {
    // Use html2canvas if available, otherwise fallback to canvas method
    // For now, we'll use a simple canvas-based approach for chart containers

    const canvas = document.createElement('canvas');
    const rect = element.getBoundingClientRect();

    canvas.width = rect.width * window.devicePixelRatio;
    canvas.height = rect.height * window.devicePixelRatio;

    const ctx = canvas.getContext('2d');
    if (!ctx) {
      console.error('[chartCapture] Failed to get canvas context');
      return null;
    }

    // Scale for retina displays
    ctx.scale(window.devicePixelRatio, window.devicePixelRatio);

    // Find canvas elements within the element and draw them
    const canvases = element.querySelectorAll('canvas');
    for (const sourceCanvas of canvases) {
      const sourceRect = sourceCanvas.getBoundingClientRect();
      const offsetX = sourceRect.left - rect.left;
      const offsetY = sourceRect.top - rect.top;

      ctx.drawImage(sourceCanvas, offsetX, offsetY);
    }

    const dataUrl = canvas.toDataURL('image/png');
    return dataUrl.split(',')[1];
  } catch (error) {
    console.error('[chartCapture] Failed to capture element:', error);
    return null;
  }
}

/**
 * Capture a screenshot of a chart by its container ID.
 *
 * @param containerId - The ID of the chart container element
 * @returns Base64-encoded PNG image data
 */
export async function captureChartById(containerId: string): Promise<string | null> {
  const container = document.getElementById(containerId);
  if (!container) {
    console.error(`[chartCapture] Container not found: ${containerId}`);
    return null;
  }

  return captureElement(container);
}
