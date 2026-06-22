import os
import requests
import yfinance as yf
import pandas as pd


TICKERS = ["SPY", "MTUM", "^VIX"]

DISPLAY_NAMES = {
    "^VIX": "VIX",
}

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    return df


def to_float(value):
    if isinstance(value, pd.Series):
        value = value.dropna()
        if value.empty:
            return None
        value = value.iloc[0]

    if pd.isna(value):
        return None

    return float(value)


def get_data(ticker: str) -> pd.DataFrame:
    df = yf.download(
        ticker,
        period="1y",
        interval="1d",
        progress=False,
        auto_adjust=False,
        group_by="column",
    )

    if df is None or df.empty:
        raise ValueError(f"{ticker} no data returned")

    df = normalize_columns(df)

    if "Close" not in df.columns:
        raise ValueError(f"{ticker} close price not found")

    df = df.dropna(subset=["Close"])

    if df.empty:
        raise ValueError(f"{ticker} no valid close price returned")

    df["ma50"] = df["Close"].rolling(50).mean()
    df["ma200"] = df["Close"].rolling(200).mean()

    return df


def compute_signal(df: pd.DataFrame) -> str:
    last = df.iloc[-1]

    close = to_float(last["Close"])
    ma50 = to_float(last["ma50"])
    ma200 = to_float(last["ma200"])

    if close is None or ma50 is None or ma200 is None:
        return "DATA WAIT"

    if close > ma50 and ma50 > ma200:
        return "STRONG BULL"

    if close > ma50:
        return "BULL"

    if close < ma50 and close > ma200:
        return "WEAK"

    if close < ma200:
        return "BEAR"

    return "NEUTRAL"


def send_webhook(message: str):
    if not WEBHOOK_URL:
        print("No webhook url set")
        return

    payload = {
        "content": message,
    }

    try:
        response = requests.post(WEBHOOK_URL, json=payload, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        print("Webhook failed:", e)


def main():
    print("大盤 ETF 每日訊號通知\n")

    results = []

    for ticker in TICKERS:
        display_name = DISPLAY_NAMES.get(ticker, ticker)

        try:
            df = get_data(ticker)
            signal = compute_signal(df)
            results.append(f"{display_name}: {signal}")

        except Exception as e:
            results.append(f"{display_name}: DATA UNAVAILABLE - {str(e)}")

    message = "\n".join(results)

    print(message)
    send_webhook(message)


if __name__ == "__main__":
    main()
