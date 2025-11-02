import requests
import os

class IndicesSpotUtility:
    """
    Utility class for fetching and extracting spot price from Polygon.io indices snapshot.
    Primary: 'value' from results[0].
    Fallback: 'session.close'.
    """
    def __init__(self, api_key=None):
        self.api_key = api_key or os.environ.get('POLYGON_API_KEY')
        if not self.api_key:
            raise ValueError("API key required – set POLYGON_API_KEY env")
        self.base_url = "https://api.polygon.io/v3/snapshot/indices"

    def get_spot(self, ticker='I:SPX', limit=1):
        """
        Fetch snapshot and extract spot price.
        Returns spot float or None if error/no data.
        """
        url = f"{self.base_url}?ticker={ticker}&limit={limit}&apikey={self.api_key}"
        resp = requests.get(url, timeout=10)
        print(f"Response for {ticker}: status {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            if 'results' in data and data['results']:
                first_item = data['results'][0]
                # Primary: value
                spot = first_item.get('value', None)
                if spot is not None:
                    print(f"Spot from value: {spot}")
                    return spot
                # Fallback: session.close
                session = first_item.get('session', {})
                spot = session.get('close', None)
                if spot is not None:
                    print(f"Spot from session.close: {spot}")
                    return spot
                print(f"No spot for {ticker}")
                return None
            print(f"No results for {ticker}")
            return None
        print(f"API error for {ticker}: {resp.status_code}")
        return None

    def get_spot_for_multiple(self, tickers=['I:SPX', 'I:NDX']):
        """
        Fetch spot for multiple indices.
        Returns dict {ticker: spot}.
        """
        spots = {}
        for ticker in tickers:
            spots[ticker] = self.get_spot(ticker)
        return spots

# Example use
if __name__ == '__main__':
    util = IndicesSpotUtility()
    spot = util.get_spot('I:SPX')
    print(f"SPX Spot: {spot}")
    spots = util.get_spot_for_multiple(['I:SPX', 'I:NDX'])
    print("Multiple Spots:", spots)