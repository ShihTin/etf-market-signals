import os
import requests
import yfinance as yf
import pandas as pd


TICKERS = ["SPY", "MTUM", "VIX"]
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")


def get_data(ticker: str) -> pd.DataFrame:
    """
    抓 ETF 歷史資料
    """
    df = yf.download(ticker, period="1y", interval="1d", progress=False)

    if df is None or df.empty:
        raise ValueError(f"{ticker} no data returned")

    df = df.dropna()

    # 計算均線
    df["ma50"] = df["Close"].rolling(50).mean()
    df["ma200"] = df["Close"].rolling(200).mean()

    return df


def compute_signal(df: pd.DataFrame) -> str:
    """
    單一 ETF 訊號（只看最後一筆，避免 Series bug）
    """
    last = df.iloc[-1]

    close = float(last["Close"])
    ma50 = float(last["ma50"]) if not pd.isna(last["ma50"]) else None
    ma200 = float(last["ma200"]) if not pd.isna(last["ma200"]) else None

    if ma50 is None:
        return "⚪ DATA WAIT"

    # === 基本趨勢判斷 ===
    if close > ma50 and ma50 > ma200:
        return "🟢 STRONG BULL"

    if close > ma50:
        return "🟡 BULL"

    if close < ma50 and close > ma200:
        return "🟠 WEAK"

    if close < ma200:
        return "🔴 BEAR"

    return "⚪ NEUTRAL"


def send_webhook(message: str):
    """
    發 Discord webhook
    """
    if not WEBHOOK_URL:
        print("No webhook url set")
        return

    payload = {
        "content": message
    }

    try:
        requests.post(WEBHOOK_URL, json=payload, timeout=10)
    except Exception as e:
        print("Webhook error:", e)


def main():
    print("大盤 ETF 每日訊號通知\n")

    results = []

    for ticker in TICKERS:
        try:
            df = get_data(ticker)
            signal = compute_signal(df)
            results.append(f"{ticker}: {signal}")

        except Exception as e:
            results.append(f"⚠️ {ticker} error: {str(e)}")

    message = "\n".join(results)

    print(message)
    send_webhook(message)


if __name__ == "__main__":
    main()
