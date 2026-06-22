import yfinance as yf
import pandas as pd

def get_last_price(ticker):
    df = yf.download(ticker, period="1y", interval="1d", progress=False)
    return df["Close"].iloc[-1], df

# -------------------------
# SPY signal
# -------------------------
def get_spy_signal():
    price, df = get_last_price("SPY")

    high_52w = df["Close"].rolling(252).max().iloc[-1]

    drop = (price - high_52w) / high_52w

    if drop >= -0.05:
        return "🟢 SPY 創新高附近"
    elif drop >= -0.10:
        return "🟡 SPY 距高點 -5%"
    elif drop >= -0.15:
        return "🟠 SPY 距高點 -10%"
    elif drop >= -0.20:
        return "🔴 SPY 距高點 -20%"
    else:
        return "🟣 SPY 距高點 -30%以下"

# -------------------------
# MTUM signal
# -------------------------
def get_mtum_signal():
    price, df = get_last_price("MTUM")

    high_52w = df["Close"].rolling(252).max().iloc[-1]

    drop = (price - high_52w) / high_52w

    if drop <= -0.10:
        return "🔴 MTUM 跌10%"
    elif drop <= -0.05:
        return "🟠 MTUM 跌5%"
    else:
        return "🟢 MTUM 正常"

# -------------------------
# VIX signal
# -------------------------
def get_vix_signal():
    price, _ = get_last_price("^VIX")

    if price > 20:
        return "⚠️ VIX 偏高"
    elif price > 15:
        return "🟡 VIX 中性偏高"
    else:
        return "🟢 VIX 正常"

# -------------------------
# main
# -------------------------
def main():
    messages = []

    try:
        messages.append(get_spy_signal())
    except Exception as e:
        messages.append(f"⚠️ SPY error: {e}")

    try:
        messages.append(get_mtum_signal())
    except Exception as e:
        messages.append(f"⚠️ MTUM error: {e}")

    try:
        messages.append(get_vix_signal())
    except Exception as e:
        messages.append(f"⚠️ VIX error: {e}")

    msg = "大盤 ETF 每日訊號通知\n\n" + "\n".join(messages)

    print(msg)

    # Discord webhook
    import os, requests
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")

    if webhook:
        requests.post(webhook, json={"content": msg})

if __name__ == "__main__":
    main()
