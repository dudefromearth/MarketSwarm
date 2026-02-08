/**
 * AI Routes - AI-powered features
 *
 * Provides endpoints for AI-assisted functionality like CSV format detection.
 */

import express from 'express';

const router = express.Router();

// AI provider configuration
const ANTHROPIC_API_KEY = process.env.ANTHROPIC_API_KEY;
const AI_MODEL = 'claude-3-5-haiku-20241022'; // Fast, cost-effective for structured tasks

/**
 * POST /api/ai/analyze-csv
 * Analyze a CSV sample to detect format and column mappings for trade import
 */
router.post('/analyze-csv', async (req, res) => {
  try {
    const { sample, totalRows } = req.body;

    if (!sample) {
      return res.json({
        success: false,
        error: 'No CSV sample provided',
      });
    }

    if (!ANTHROPIC_API_KEY) {
      return res.json({
        success: false,
        error: 'AI service not configured',
      });
    }

    const systemPrompt = `You are a CSV format analyzer for options trading data. Analyze the provided CSV sample and identify column mappings for trade import.

You must identify these columns (by their 0-based index):
- date: Trade date (required)
- time: Trade time (optional)
- symbol: Underlying symbol like SPX, NDX, QQQ (required)
- expiration: Option expiration date (required)
- strike: Strike price (required)
- type: Option type - call or put (required)
- quantity: Number of contracts, negative for short (required)
- price: Per-contract price (required)
- commission: Commission amount (optional)
- fees: Fees amount (optional)
- effect: Position effect - open or close (optional)
- side: Buy/Sell indicator if quantity is always positive (optional)

Respond with ONLY valid JSON in this exact format:
{
  "platform": "tos" | "tastytrade" | "ibkr" | "schwab" | "unknown",
  "platformConfidence": 0.0 to 1.0,
  "columnMapping": {
    "date": <column_index>,
    "time": <column_index or null>,
    "symbol": <column_index>,
    "expiration": <column_index>,
    "strike": <column_index>,
    "type": <column_index>,
    "quantity": <column_index>,
    "price": <column_index>,
    "commission": <column_index or null>,
    "fees": <column_index or null>,
    "effect": <column_index or null>,
    "side": <column_index or null>
  },
  "dateFormat": "ISO" | "US" | "EU" | null,
  "notes": ["any observations about the data format"]
}

If you cannot determine the format, respond with:
{
  "platform": "unknown",
  "platformConfidence": 0,
  "columnMapping": {},
  "error": "reason why format could not be determined"
}`;

    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': ANTHROPIC_API_KEY,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: AI_MODEL,
        max_tokens: 1024,
        system: systemPrompt,
        messages: [
          {
            role: 'user',
            content: `Analyze this CSV sample (${totalRows} total rows in file):\n\n${sample}`,
          },
        ],
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error('[AI] API error:', response.status, errorText);
      return res.json({
        success: false,
        error: `AI service error: ${response.status}`,
      });
    }

    const aiResponse = await response.json();
    const content = aiResponse.content?.[0]?.text;

    if (!content) {
      return res.json({
        success: false,
        error: 'No response from AI',
      });
    }

    // Parse JSON from response
    try {
      // Extract JSON from potential markdown code blocks
      let jsonStr = content;
      const jsonMatch = content.match(/```(?:json)?\s*([\s\S]*?)\s*```/);
      if (jsonMatch) {
        jsonStr = jsonMatch[1];
      }

      const analysis = JSON.parse(jsonStr);

      // Validate the response has required fields
      if (!analysis.columnMapping) {
        return res.json({
          success: false,
          error: 'AI response missing column mapping',
        });
      }

      return res.json({
        success: true,
        ...analysis,
      });
    } catch (parseErr) {
      console.error('[AI] Failed to parse response:', content);
      return res.json({
        success: false,
        error: 'Failed to parse AI response',
      });
    }
  } catch (err) {
    console.error('[AI] analyze-csv error:', err);
    return res.json({
      success: false,
      error: err.message || 'AI analysis failed',
    });
  }
});

export default router;
