/**
 * Pricing Module
 *
 * Options pricing calculations including Black-Scholes model.
 * Platform-agnostic implementation.
 */
// ============================================================
// Constants
// ============================================================
/** Annual trading days for volatility calculations */
export const TRADING_DAYS_PER_YEAR = 252;
/** Minutes per trading day */
export const TRADING_MINUTES_PER_DAY = 390;
// ============================================================
// Helper Functions
// ============================================================
/**
 * Standard normal cumulative distribution function
 */
export function normCdf(x) {
    const a1 = 0.254829592;
    const a2 = -0.284496736;
    const a3 = 1.421413741;
    const a4 = -1.453152027;
    const a5 = 1.061405429;
    const p = 0.3275911;
    const sign = x < 0 ? -1 : 1;
    x = Math.abs(x) / Math.sqrt(2);
    const t = 1.0 / (1.0 + p * x);
    const y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * Math.exp(-x * x);
    return 0.5 * (1.0 + sign * y);
}
/**
 * Standard normal probability density function
 */
export function normPdf(x) {
    return Math.exp(-0.5 * x * x) / Math.sqrt(2 * Math.PI);
}
// ============================================================
// Black-Scholes Implementation
// ============================================================
/**
 * Calculate option price and Greeks using Black-Scholes model
 *
 * Uses the generalized Black-Scholes formula (Merton model) that
 * accounts for continuous dividend yield.
 */
export function blackScholes(input) {
    const { spot, strike, timeToExpiry, volatility, riskFreeRate, dividendYield = 0, optionType, } = input;
    // Handle edge case of expired option
    if (timeToExpiry <= 0) {
        const intrinsicValue = optionType === 'call'
            ? Math.max(0, spot - strike)
            : Math.max(0, strike - spot);
        return {
            price: intrinsicValue,
            greeks: {
                delta: optionType === 'call' ? (spot > strike ? 1 : 0) : (spot < strike ? -1 : 0),
                gamma: 0,
                theta: 0,
                vega: 0,
                rho: 0,
            },
        };
    }
    const sqrtT = Math.sqrt(timeToExpiry);
    const d1 = (Math.log(spot / strike) + (riskFreeRate - dividendYield + 0.5 * volatility * volatility) * timeToExpiry) / (volatility * sqrtT);
    const d2 = d1 - volatility * sqrtT;
    const expMinusQT = Math.exp(-dividendYield * timeToExpiry);
    const expMinusRT = Math.exp(-riskFreeRate * timeToExpiry);
    let price;
    let delta;
    let rho;
    if (optionType === 'call') {
        price = spot * expMinusQT * normCdf(d1) - strike * expMinusRT * normCdf(d2);
        delta = expMinusQT * normCdf(d1);
        rho = strike * timeToExpiry * expMinusRT * normCdf(d2) / 100;
    }
    else {
        price = strike * expMinusRT * normCdf(-d2) - spot * expMinusQT * normCdf(-d1);
        delta = -expMinusQT * normCdf(-d1);
        rho = -strike * timeToExpiry * expMinusRT * normCdf(-d2) / 100;
    }
    // Gamma is the same for calls and puts
    const gamma = expMinusQT * normPdf(d1) / (spot * volatility * sqrtT);
    // Theta (per day)
    const theta = (-(spot * volatility * expMinusQT * normPdf(d1)) / (2 * sqrtT)
        - riskFreeRate * strike * expMinusRT * (optionType === 'call' ? normCdf(d2) : normCdf(-d2))
        + dividendYield * spot * expMinusQT * (optionType === 'call' ? normCdf(d1) : normCdf(-d1))) / 365;
    // Vega (per 1% change in volatility)
    const vega = spot * expMinusQT * normPdf(d1) * sqrtT / 100;
    return {
        price,
        greeks: {
            delta,
            gamma,
            theta,
            vega,
            rho,
        },
    };
}
/**
 * Calculate implied volatility using Newton-Raphson iteration
 */
export function impliedVolatility(marketPrice, spot, strike, timeToExpiry, riskFreeRate, optionType, dividendYield = 0, maxIterations = 100, tolerance = 0.0001) {
    // Initial guess
    let sigma = 0.3;
    for (let i = 0; i < maxIterations; i++) {
        const result = blackScholes({
            spot,
            strike,
            timeToExpiry,
            volatility: sigma,
            riskFreeRate,
            dividendYield,
            optionType,
        });
        const diff = result.price - marketPrice;
        if (Math.abs(diff) < tolerance) {
            return sigma;
        }
        // Newton-Raphson: sigma_new = sigma - f(sigma) / f'(sigma)
        // where f'(sigma) = vega * 100 (since vega is per 1% change)
        const vegaRaw = result.greeks.vega * 100;
        if (vegaRaw < 0.00001) {
            // Vega too small, can't converge
            return null;
        }
        sigma = sigma - diff / vegaRaw;
        // Keep sigma in reasonable bounds
        if (sigma <= 0.001)
            sigma = 0.001;
        if (sigma > 5)
            sigma = 5;
    }
    return null; // Failed to converge
}
/**
 * Calculate days to expiration from date string
 */
export function calculateDTE(expiration, now = Date.now()) {
    const expDate = new Date(expiration + 'T16:00:00'); // 4pm ET market close
    const diffMs = expDate.getTime() - now;
    return Math.max(0, Math.ceil(diffMs / (1000 * 60 * 60 * 24)));
}
/**
 * Convert DTE to time in years for Black-Scholes
 */
export function dteToYears(dte) {
    return dte / 365;
}
/**
 * Convert DTE to trading time in years
 */
export function dteToTradingYears(dte) {
    return dte / TRADING_DAYS_PER_YEAR;
}
//# sourceMappingURL=index.js.map