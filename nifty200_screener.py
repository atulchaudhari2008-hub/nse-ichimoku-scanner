# Install required packages:
# pip install yfinance pandas ta requests zipfile36

import yfinance as yf
import pandas as pd
import ta
import requests
import zipfile
import io
from datetime import datetime, timedelta

# Example: NIFTY 200 stock list (replace with full list of tickers)
nifty200_symbols = ["RELIANCE.NS", "TCS.NS", "INFY.NS"]

# --- Bhavcopy Functions ---
def get_bhavcopy(date):
    """
    Download NSE bhavcopy for a given date (YYYY-MM-DD).
    """
    date_str = date.strftime("%d%m%Y")
    url = f"https://nsearchives.nseindia.com/content/historical/EQUITIES/{date.year}/{date.strftime('%b').upper()}/cm{date_str}bhav.csv.zip"
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        raise Exception(f"Bhavcopy not available for {date_str}")
    z = zipfile.ZipFile(io.BytesIO(resp.content))
    csv_file = z.namelist()[0]
    df = pd.read_csv(z.open(csv_file))
    return df

def get_delivery_percentages(symbol, days=3):
    """
    Get last N days of delivery % for a stock.
    """
    delivery_list = []
    today = datetime.today()
    count = 0
    offset = 1
    while count < days:
        date = today - timedelta(days=offset)
        try:
            df = get_bhavcopy(date)
            row = df[df['SYMBOL'] == symbol.replace('.NS','')]
            if not row.empty:
                deliv_qty = row['DELIV_QTY'].values[0]
                traded_qty = row['TOTTRDQTY'].values[0]
                delivery_pct = (deliv_qty / traded_qty) * 100 if traded_qty > 0 else 0
                delivery_list.append(delivery_pct)
                count += 1
        except Exception:
            pass
        offset += 1
    return delivery_list[::-1]  # chronological order

def delivery_rising_3days(symbol):
    """
    Check if delivery % is rising sequentially for last 3 days.
    """
    history = get_delivery_percentages(symbol, days=3)
    if len(history) < 3:
        return False
    return history[0] < history[1] < history[2]

# --- Screener ---
results = []

for symbol in nifty200_symbols:
    try:
        # Download 250+ days of OHLCV
        df = yf.download(symbol, period="250d", interval="1d")
        df.dropna(inplace=True)

        # Indicators
        df['EMA20'] = ta.trend.EMAIndicator(df['Close'], window=20).ema_indicator()
        df['EMA50'] = ta.trend.EMAIndicator(df['Close'], window=50).ema_indicator()
        df['EMA200'] = ta.trend.EMAIndicator(df['Close'], window=200).ema_indicator()
        df['RSI'] = ta.momentum.RSIIndicator(df['Close'], window=14).rsi()
        macd = ta.trend.MACD(df['Close'])
        df['MACD'] = macd.macd()
        df['MACD_signal'] = macd.macd_signal()
        df['VWAP'] = ta.volume.VolumeWeightedAveragePrice(
            high=df['High'], low=df['Low'], close=df['Close'], volume=df['Volume']
        ).volume_weighted_average_price()

        # Conditions
        latest = df.iloc[-1]
        avg_vol20 = df['Volume'].tail(20).mean()
        breakout_9d = df['High'].tail(9).max()

        cond_volume = latest['Volume'] > 1.5 * avg_vol20
        cond_price_above_ema20 = latest['Close'] > latest['EMA20']
        cond_ema_alignment = latest['EMA20'] > latest['EMA50'] > latest['EMA200']
        cond_rsi = latest['RSI'] > 60
        cond_macd = latest['MACD'] > latest['MACD_signal']  # bullish crossover
        cond_vwap = latest['Close'] > latest['VWAP']
        cond_breakout = latest['Close'] > breakout_9d
        cond_delivery = delivery_rising_3days(symbol)

        if all([cond_volume, cond_price_above_ema20, cond_ema_alignment,
                cond_rsi, cond_macd, cond_vwap, cond_breakout, cond_delivery]):
            results.append({
                'Symbol': symbol,
                'Close': latest['Close'],
                'Volume': latest['Volume'],
                'RSI': latest['RSI'],
                'EMA20': latest['EMA20'],
                'EMA50': latest['EMA50'],
                'EMA200': latest['EMA200']
            })

    except Exception as e:
        print(f"Error with {symbol}: {e}")

# Export results
df_results = pd.DataFrame(results)
df_results.to_csv("nifty200_screened.csv", index=False)
print(df_results)
