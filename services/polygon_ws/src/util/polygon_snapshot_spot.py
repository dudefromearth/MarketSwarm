from polygon import RESTClient
import os


def get_spot_price(symbol='SPY', api_key=None):
    """
    Send snapshot request and extract spot price from first record's underlying_asset.
    """
    if not api_key:
        api_key = os.environ.get('POLYGON_API_KEY')
    if not api_key:
        raise ValueError("API key required – set POLYGON_API_KEY env")

    client = RESTClient(api_key)
    try:
        options_chain = []
        for o in client.list_snapshot_options_chain(
                symbol,
                params={
                    "order": "asc",
                    "limit": 1,  # Quick for spot
                    "sort": "ticker",
                },
        ):
            options_chain.append(o)

        if options_chain:
            first_item = options_chain[0]
            # Extract spot
            ua = first_item.underlying_asset
            if ua and ua.price is not None:
                return ua.price
            lt = first_item.last_trade
            if lt and lt.price is not None:
                return lt.price
            lq = first_item.last_quote
            if lq and lq.bid is not None and lq.ask is not None:
                return (lq.bid + lq.ask) / 2
            return None  # No spot available
        else:
            print("No records returned")
            return None
    except Exception as e:
        print(f"Error: {e}")
        return None


if __name__ == '__main__':
    spot = get_spot_price('SPY')
    print(f"Spot price for SPY: {spot}")