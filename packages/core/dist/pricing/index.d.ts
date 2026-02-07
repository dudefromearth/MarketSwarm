/**
 * Pricing Module
 *
 * Options pricing calculations including Black-Scholes model.
 * Platform-agnostic implementation.
 */
/** Annual trading days for volatility calculations */
export declare const TRADING_DAYS_PER_YEAR = 252;
/** Minutes per trading day */
export declare const TRADING_MINUTES_PER_DAY = 390;
/** Greeks for an option or position */
export interface Greeks {
    delta: number;
    gamma: number;
    theta: number;
    vega: number;
    rho?: number;
}
/** Input for Black-Scholes calculation */
export interface BlackScholesInput {
    /** Current underlying price */
    spot: number;
    /** Strike price */
    strike: number;
    /** Time to expiration in years */
    timeToExpiry: number;
    /** Annualized volatility (decimal, e.g., 0.20 for 20%) */
    volatility: number;
    /** Risk-free interest rate (decimal) */
    riskFreeRate: number;
    /** Dividend yield (decimal) */
    dividendYield?: number;
    /** Option type */
    optionType: 'call' | 'put';
}
/** Result of Black-Scholes calculation */
export interface BlackScholesResult {
    /** Theoretical option price */
    price: number;
    /** Option Greeks */
    greeks: Greeks;
}
/**
 * Standard normal cumulative distribution function
 */
export declare function normCdf(x: number): number;
/**
 * Standard normal probability density function
 */
export declare function normPdf(x: number): number;
/**
 * Calculate option price and Greeks using Black-Scholes model
 *
 * Uses the generalized Black-Scholes formula (Merton model) that
 * accounts for continuous dividend yield.
 */
export declare function blackScholes(input: BlackScholesInput): BlackScholesResult;
/**
 * Calculate implied volatility using Newton-Raphson iteration
 */
export declare function impliedVolatility(marketPrice: number, spot: number, strike: number, timeToExpiry: number, riskFreeRate: number, optionType: 'call' | 'put', dividendYield?: number, maxIterations?: number, tolerance?: number): number | null;
/**
 * Calculate days to expiration from date string
 */
export declare function calculateDTE(expiration: string, now?: number): number;
/**
 * Convert DTE to time in years for Black-Scholes
 */
export declare function dteToYears(dte: number): number;
/**
 * Convert DTE to trading time in years
 */
export declare function dteToTradingYears(dte: number): number;
//# sourceMappingURL=index.d.ts.map