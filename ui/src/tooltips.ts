// Centralized tooltip content for MarketSwarm widgets
// Edit this file to update all tooltips across the application
// Supports HTML content including links to educational materials

export interface TooltipContent {
  title?: string;
  description: string;
  link?: {
    text: string;
    url: string;
  };
}

export const tooltips: Record<string, TooltipContent> = {
  // ═══════════════════════════════════════════════════════════════════════════
  // MARKET MODE WIDGET
  // ═══════════════════════════════════════════════════════════════════════════

  marketMode: {
    title: 'Market Mode',
    description: 'Composite gamma and structure regime indicator that measures whether the market is in compression (range-bound) or expansion (trending) mode.',
    link: {
      text: 'Learn about Market Regimes',
      url: '/docs/market-mode'
    }
  },

  marketModeCompression: {
    title: 'Compression (0-35)',
    description: 'Tight trading ranges with mean reversion favored. Price tends to stay contained within defined levels. Breakout attempts often fail.',
    link: {
      text: 'Trading Compression',
      url: '/docs/market-mode#compression'
    }
  },

  marketModeTransition: {
    title: 'Transition (35-65)',
    description: 'Mixed conditions where the market could go either way. Be cautious and wait for clearer signals before committing to directional trades.',
    link: {
      text: 'Navigating Transitions',
      url: '/docs/market-mode#transition'
    }
  },

  marketModeExpansion: {
    title: 'Expansion (65-100)',
    description: 'Trending conditions with breakouts favored. Price can move quickly and directionally. Momentum strategies tend to work well.',
    link: {
      text: 'Trading Expansion',
      url: '/docs/market-mode#expansion'
    }
  },

  marketModeBadge: {
    description: 'Current market regime based on the composite score. Updates in real-time as market conditions change.',
  },

  // ═══════════════════════════════════════════════════════════════════════════
  // LIQUIDITY INTENT MAP WIDGET
  // ═══════════════════════════════════════════════════════════════════════════

  liquidityIntent: {
    title: 'Liquidity Intent Map',
    description: 'Shows how liquidity responds to price movement — not where price will go, but how it will behave when it gets there. The position indicates the current market stance.',
    link: {
      text: 'Understanding Liquidity Intent',
      url: '/docs/liquidity-intent'
    }
  },

  limBias: {
    title: 'Acceptance Bias',
    description: 'Measures whether liquidity is supportive (+) or hostile (-) to current price direction. Positive bias means price moves are more likely to be sustained.',
    link: {
      text: 'About Acceptance Bias',
      url: '/docs/liquidity-intent#bias'
    }
  },

  limLFI: {
    title: 'Liquidity Flow Index (LFI)',
    description: 'Measures the acceleration or deceleration of liquidity flow. Higher values indicate stronger conviction in the current move.',
    link: {
      text: 'About LFI',
      url: '/docs/liquidity-intent#lfi'
    }
  },

  limQuadrantPin: {
    title: 'Pin / Mean Reversion',
    description: 'Liquidity contains price. Expect range-bound action with moves likely to reverse. Good for selling premium and fading extremes.',
    link: {
      text: 'Trading the Pin Zone',
      url: '/docs/liquidity-intent#pin'
    }
  },

  limQuadrantTrap: {
    title: 'False Breakout Risk',
    description: 'Moves need confirmation. High risk of traps and failed breakouts. Wait for follow-through before committing to directional trades.',
    link: {
      text: 'Avoiding Traps',
      url: '/docs/liquidity-intent#trap'
    }
  },

  limQuadrantSell: {
    title: 'Downside Acceleration',
    description: 'Liquidity amplifies selling pressure. Risk of rapid drops as selling begets more selling. Defensive positioning recommended.',
    link: {
      text: 'Managing Downside Risk',
      url: '/docs/liquidity-intent#sell'
    }
  },

  limQuadrantRun: {
    title: 'Air-Pocket Expansion',
    description: 'Price can travel quickly with little resistance. Low liquidity allows for rapid moves. Good for momentum trades with tight stops.',
    link: {
      text: 'Trading Air Pockets',
      url: '/docs/liquidity-intent#run'
    }
  },

  // ═══════════════════════════════════════════════════════════════════════════
  // DEALER GRAVITY WIDGET
  // ═══════════════════════════════════════════════════════════════════════════

  dealerGravity: {
    title: 'Dealer Gravity',
    description: 'Shows where dealers and market makers are likely hedging their positions, creating gravitational pull on price action. Price tends to gravitate toward these levels.',
    link: {
      text: 'Understanding Dealer Positioning',
      url: '/docs/dealer-gravity'
    }
  },

  dealerGravityBest: {
    title: 'Best Estimate',
    description: 'The most likely price level where dealer hedging activity is concentrated. Price often gravitates toward this level during quieter periods.',
    link: {
      text: 'Using Best Estimate',
      url: '/docs/dealer-gravity#best'
    }
  },

  dealerGravityHigh: {
    title: 'High Band',
    description: 'Upper bound of the dealer gravity range. Price may encounter resistance or selling pressure above this level as dealers adjust hedges.',
    link: {
      text: 'Trading the High Band',
      url: '/docs/dealer-gravity#high'
    }
  },

  dealerGravityLow: {
    title: 'Low Band',
    description: 'Lower bound of the dealer gravity range. Price may find support or buying pressure near this level as dealers adjust hedges.',
    link: {
      text: 'Trading the Low Band',
      url: '/docs/dealer-gravity#low'
    }
  },

  dealerGravity5m: {
    description: 'View 5-minute candles for short-term gravity levels. Best for scalping and very short-term trades.',
  },

  dealerGravity15m: {
    description: 'View 15-minute candles for medium-term gravity levels. Good balance of detail and noise reduction.',
  },

  dealerGravity1h: {
    description: 'View 1-hour candles for longer-term gravity levels. Best for swing trades and identifying major levels.',
  },

  // ═══════════════════════════════════════════════════════════════════════════
  // VEXY WIDGET
  // ═══════════════════════════════════════════════════════════════════════════

  vexy: {
    title: 'Vexy AI Commentary',
    description: 'Real-time AI-generated market commentary providing context on current conditions, significant events, and trading considerations.',
    link: {
      text: 'About Vexy AI',
      url: '/docs/vexy'
    }
  },
};

// Helper to get tooltip by key with fallback
export function getTooltip(key: string): TooltipContent {
  return tooltips[key] || { description: key };
}
