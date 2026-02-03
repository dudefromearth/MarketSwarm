/**
 * VolumeProfilePrimitive - Custom Lightweight Charts primitive for Volume Profile
 *
 * Draws horizontal volume bars at each price level from the left side of the chart.
 * Higher volume levels are more prominent, showing areas of price acceptance.
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

export type VolumeProfileDataPoint = {
  price: number;
  volume: number;
};

export type VolumeProfilePrimitiveOptions = {
  maxVolume: number;
  barHeight: number;
  maxBarWidthPercent: number;  // % of chart width for profile scaling
  color: string;
};

type RendererData = {
  y: number;
  volume: number;
  price: number;
};

const defaultOptions: VolumeProfilePrimitiveOptions = {
  maxVolume: 1,
  barHeight: 2,
  maxBarWidthPercent: 15,
  color: 'rgba(147, 51, 234, 0.5)',
};

class VolumeProfilePaneRenderer implements IPrimitivePaneRenderer {
  private _data: RendererData[];
  private _options: VolumeProfilePrimitiveOptions;

  constructor(data: RendererData[], options: VolumeProfilePrimitiveOptions) {
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

      const { maxVolume, barHeight, maxBarWidthPercent, color } = this._options;

      // Volume profile renders on the left side
      const leftMargin = 5;
      const actualMaxWidth = width * (maxBarWidthPercent / 100);

      ctx.save();
      ctx.fillStyle = color;

      for (const point of this._data) {
        const { y, volume } = point;
        // Skip if outside visible area
        if (y < 0 || y > height) continue;

        const normalizedWidth = maxVolume > 0 ? volume / maxVolume : 0;
        const barWidth = normalizedWidth * actualMaxWidth;

        ctx.fillRect(leftMargin, y - barHeight / 2, barWidth, barHeight);
      }

      ctx.restore();
    });
  }
}

class VolumeProfilePaneView implements IPrimitivePaneView {
  private _source: VolumeProfilePrimitive;

  constructor(source: VolumeProfilePrimitive) {
    this._source = source;
  }

  renderer(): IPrimitivePaneRenderer | null {
    return new VolumeProfilePaneRenderer(this._source.getRendererData(), this._source.getOptions());
  }

  zOrder(): 'bottom' | 'top' | 'normal' {
    return 'bottom';
  }
}

export class VolumeProfilePrimitive implements ISeriesPrimitive<Time> {
  private _paneView: VolumeProfilePaneView;
  private _data: VolumeProfileDataPoint[] = [];
  private _options: VolumeProfilePrimitiveOptions;
  private _series: ISeriesApi<SeriesType> | null = null;
  private _requestUpdate?: () => void;

  constructor(options?: Partial<VolumeProfilePrimitiveOptions>) {
    this._options = { ...defaultOptions, ...options };
    this._paneView = new VolumeProfilePaneView(this);
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

  setData(data: VolumeProfileDataPoint[]): void {
    this._data = data;
    this._requestUpdate?.();
  }

  setOptions(options: Partial<VolumeProfilePrimitiveOptions>): void {
    this._options = { ...this._options, ...options };
    this._requestUpdate?.();
  }

  getData(): VolumeProfileDataPoint[] {
    return this._data;
  }

  getOptions(): VolumeProfilePrimitiveOptions {
    return this._options;
  }

  getRendererData(): RendererData[] {
    if (!this._series) return [];

    const result: RendererData[] = [];

    for (const point of this._data) {
      const y = this._series.priceToCoordinate(point.price);
      if (y === null) continue;

      result.push({
        y: y as number,
        volume: point.volume,
        price: point.price,
      });
    }

    return result;
  }
}
