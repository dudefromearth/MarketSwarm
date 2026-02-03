/**
 * GexPrimitive - Custom Lightweight Charts primitive for GEX horizontal bars
 *
 * Draws gamma exposure bars at each strike price:
 * - Call GEX: Green bars extending right from center
 * - Put GEX: Red bars extending left from center
 * - Net GEX mode: Single bar showing net value
 */

import type {
  ISeriesPrimitive,
  SeriesAttachedParameter,
  Time,
  ISeriesApi,
  SeriesType,
  IPrimitivePaneView,
  IPrimitivePaneRenderer,
} from 'lightweight-charts';

export type GexDataPoint = {
  strike: number;
  calls: number;
  puts: number;
};

export type GexPrimitiveOptions = {
  mode: 'combined' | 'net';
  maxGex: number;
  maxNetGex: number;
  barHeight: number;
  opacity: number;
  callColor: string;
  putColor: string;
  currentSpot: number | null;
  atmHighlightColor: string;
  maxBarWidthPercent: number;  // % of chart width for max bar
};

type RendererData = {
  y: number;
  calls: number;
  puts: number;
  strike: number;
  isAtm: boolean;
};

const defaultOptions: GexPrimitiveOptions = {
  mode: 'combined',
  maxGex: 1,
  maxNetGex: 1,
  barHeight: 3,
  opacity: 0.7,
  callColor: 'rgba(34, 197, 94, 0.7)',
  putColor: 'rgba(239, 68, 68, 0.7)',
  currentSpot: null,
  atmHighlightColor: 'rgba(251, 191, 36, 0.8)',
  maxBarWidthPercent: 25,
};

class GexPaneRenderer implements IPrimitivePaneRenderer {
  private _data: RendererData[];
  private _options: GexPrimitiveOptions;

  constructor(data: RendererData[], options: GexPrimitiveOptions) {
    this._data = data;
    this._options = options;
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  draw(target: any): void {
    // Use mediaCoordinateSpace - coordinates match priceToCoordinate() output directly
    target.useMediaCoordinateSpace((scope: { context: CanvasRenderingContext2D; mediaSize: { width: number; height: number } }) => {
      const ctx = scope.context;
      const { width, height } = scope.mediaSize;

      if (this._data.length === 0) return;

      const { mode, maxGex, maxNetGex, barHeight, callColor, putColor, atmHighlightColor, maxBarWidthPercent } = this._options;

      // GEX bars render on the right side of the chart, before the price scale
      const rightMargin = 55; // Space for price scale
      const maxBarWidth = width * (maxBarWidthPercent / 100);
      const centerX = width - rightMargin - maxBarWidth / 2;

      ctx.save();

      for (const point of this._data) {
        const { y, calls, puts, isAtm } = point;
        // Skip if outside visible area
        if (y < 0 || y > height) continue;

        const actualBarHeight = isAtm ? barHeight + 1 : barHeight;

        if (mode === 'net') {
          const netGex = calls - puts;
          const normalizedWidth = maxNetGex > 0 ? Math.abs(netGex) / maxNetGex : 0;
          const barWidth = normalizedWidth * (maxBarWidth / 2);
          const isPositive = netGex > 0;

          ctx.fillStyle = isPositive ? callColor : putColor;

          if (isPositive) {
            ctx.fillRect(centerX, y - actualBarHeight / 2, barWidth, actualBarHeight);
          } else {
            ctx.fillRect(centerX - barWidth, y - actualBarHeight / 2, barWidth, actualBarHeight);
          }
        } else {
          // Combined mode: calls go right, puts go left from center
          const callWidth = maxGex > 0 ? (calls / maxGex) * (maxBarWidth / 2) : 0;
          const putWidth = maxGex > 0 ? (puts / maxGex) * (maxBarWidth / 2) : 0;

          if (putWidth > 0) {
            ctx.fillStyle = putColor;
            ctx.fillRect(centerX - putWidth, y - actualBarHeight / 2, putWidth, actualBarHeight);
          }

          if (callWidth > 0) {
            ctx.fillStyle = callColor;
            ctx.fillRect(centerX, y - actualBarHeight / 2, callWidth, actualBarHeight);
          }
        }

        // ATM highlight line
        if (isAtm) {
          ctx.strokeStyle = atmHighlightColor;
          ctx.lineWidth = 1;
          ctx.setLineDash([4, 2]);
          ctx.beginPath();
          ctx.moveTo(centerX - maxBarWidth / 2 - 10, y);
          ctx.lineTo(centerX + maxBarWidth / 2 + 10, y);
          ctx.stroke();
          ctx.setLineDash([]);
        }
      }

      ctx.restore();
    });
  }
}

class GexPaneView implements IPrimitivePaneView {
  private _source: GexPrimitive;

  constructor(source: GexPrimitive) {
    this._source = source;
  }

  renderer(): IPrimitivePaneRenderer | null {
    return new GexPaneRenderer(this._source.getRendererData(), this._source.getOptions());
  }

  zOrder(): 'bottom' | 'top' | 'normal' {
    return 'top';
  }
}

export class GexPrimitive implements ISeriesPrimitive<Time> {
  private _paneView: GexPaneView;
  private _data: GexDataPoint[] = [];
  private _options: GexPrimitiveOptions;
  private _series: ISeriesApi<SeriesType> | null = null;
  private _requestUpdate?: () => void;

  constructor(options?: Partial<GexPrimitiveOptions>) {
    this._options = { ...defaultOptions, ...options };
    this._paneView = new GexPaneView(this);
  }

  attached(param: SeriesAttachedParameter<Time>): void {
    this._requestUpdate = param.requestUpdate;
    this._series = param.series as ISeriesApi<SeriesType>;
  }

  detached(): void {
    this._requestUpdate = undefined;
    this._series = null;
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return [this._paneView];
  }

  updateAllViews(): void {
    // Views are recreated on each render
  }

  setData(data: GexDataPoint[]): void {
    this._data = data;
    this._requestUpdate?.();
  }

  setOptions(options: Partial<GexPrimitiveOptions>): void {
    this._options = { ...this._options, ...options };
    this._requestUpdate?.();
  }

  getData(): GexDataPoint[] {
    return this._data;
  }

  getOptions(): GexPrimitiveOptions {
    return this._options;
  }

  getRendererData(): RendererData[] {
    if (!this._series) return [];

    const { currentSpot } = this._options;
    const result: RendererData[] = [];

    for (const point of this._data) {
      const y = this._series.priceToCoordinate(point.strike);
      if (y === null) continue;

      const isAtm = currentSpot !== null && Math.abs(point.strike - currentSpot) < 5;

      result.push({
        y: y as number,
        calls: point.calls,
        puts: point.puts,
        strike: point.strike,
        isAtm,
      });
    }

    return result;
  }
}
