"""OpenAI API price table and per-call cost.

Prices are USD per 1,000,000 tokens (input, output). Verified 2026-09-05;
update here if OpenAI changes pricing. Cost is stored per row so the monitoring
dashboard stays correct even when the demo runs on a cheaper model than the eval.
"""

PRICES = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
}


def cost_usd(model, prompt_tokens, completion_tokens):
    """Cost of one call in USD. Returns 0.0 for an unknown model or missing usage."""
    if model not in PRICES or prompt_tokens is None or completion_tokens is None:
        return 0.0
    in_price, out_price = PRICES[model]
    return round(prompt_tokens / 1_000_000 * in_price + completion_tokens / 1_000_000 * out_price, 6)
