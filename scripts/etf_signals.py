import os
import requests
import yfinance as yf
import pandas as pd


WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

SPY = "SPY"
MTUM = "MTUM"
VIX = "^VIX"


def safe_float(value):
    if isinstance(value, pd.Series):
        value = value.dropna()
        if value.empty:
            return None
        value = value.iloc[0]

    if pd.isna(value):
        return None

    return float(value)


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    return df


def download_data(ticker: str, period: str = "1y") -> pd.DataFrame:
    df = yf.download(
        ticker,
        period=period,
        interval="1d",
        progress=False,
        auto_adjust=False,
        group_by="column",
    )

    if df is None or df.empty:
        return pd.DataFrame()

    df = normalize_columns(df)

    if "Close" not in df.columns:
        return pd.DataFrame()

    df = df.dropna(subset=["Close"])
    return df


def latest_close(df: pd.DataFrame):
    if df.empty:
        return None
    return safe_float(df.iloc[-1]["Close"])


def drawdown_from_high(df: pd.DataFrame, window: int = 126):
    if df.empty or "Close" not in df.columns:
        return None, None

    recent = df.tail(window)
    high = safe_float(recent["Close"].max())
    close = latest_close(df)

    if high is None or close is None or high == 0:
        return close, None

    drawdown_pct = (close / high - 1) * 100
    return close, drawdown_pct


def spy_signal(drawdown_pct):
    if drawdown_pct is None:
        return "⚪ N/A"

    if drawdown_pct >= -0.1:
        return "🟢 新高"

    if drawdown_pct <= -40:
        return "⚫ -40%"
    if drawdown_pct <= -35:
        return "🟣 -35%"
    if drawdown_pct <= -30:
        return "🟪 -30%"
    if drawdown_pct <= -20:
        return "🔴 -20%"
    if drawdown_pct <= -15:
        return "🟥 -15%"
    if drawdown_pct <= -10:
        return "🟠 -10%"
    if drawdown_pct <= -5:
        return "🟡 -5%"

    return "⚪ 正常"


def vix_signal(vix_value):
    if vix_value is None:
        return "⚪ N/A"

    if vix_value >= 40:
        return "⚫ VIX >= 40"
    if vix_value >= 30:
        return "🔴 VIX >= 30"
    if vix_value >= 25:
        return "🟡 VIX >= 25"

    return "⚪ 正常"


def pct_return(df: pd.DataFrame, days: int = 63):
    if df.empty or len(df) <= days:
        return None

    start = safe_float(df.iloc[-days]["Close"])
    end = safe_float(df.iloc[-1]["Close"])

    if start is None or end is None or start == 0:
        return None

    return (end / start - 1) * 100


def mtum_signal(mtum_df: pd.DataFrame, spy_df: pd.DataFrame):
    mtum_ret = pct_return(mtum_df, 63)
    spy_ret = pct_return(spy_df, 63)

    if mtum_ret is None or spy_ret is None:
        return "⚪ N/A"

    relative = mtum_ret - spy_ret

    if relative <= -10:
        decay = "🔴 動能衰退 -10%"
    elif relative <= -5:
        decay = "🟡 動能衰退 -5%"
    else:
        decay = "⚪ 無明顯衰退"

    direction = "領先 SPY" if relative >= 0 else "落後 SPY"

    return f"{direction} ({relative:+.2f}%) / {decay}"


def get_cnn_fear_greed():
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        headers = {
            "User-Agent": "Mozilla/5.0",
        }

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        data = response.json()
        value = data.get("fear_and_greed", {}).get("score")

        if value is None:
            return "N/A"

        return f"{float(value):.0f}"

    except Exception:
        return "N/A"


def get_aaii_bearish():
    value = os.getenv("AAII_BEARISH")

    if not value:
        return "N/A"

    try:
        return f"{float(value):.1f}%"
    except ValueError:
        return "N/A"


def get_smart_dumb_money():
    value = os.getenv("SMART_DUMB_MONEY")

    if not value:
        return "N/A"

    return value


def send_webhook(message: str):
    if not WEBHOOK_URL:
        print("No webhook url set")
        return

    try:
        response = requests.post(
            WEBHOOK_URL,
            json={"content": message},
            timeout=10,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        print("Webhook failed:", e)


def main():
    spy_df = download_data(SPY, "1y")
    mtum_df = download_data(MTUM, "1y")
    vix_df = download_data(VIX, "1y")

    spy_close, spy_drawdown = drawdown_from_high(spy_df, 126)
    vix_close = latest_close(vix_df)

    cnn_fear_greed = get_cnn_fear_greed()
    aaii_bearish = get_aaii_bearish()
    smart_dumb_money = get_smart_dumb_money()

    spy_close_text = "N/A" if spy_close is None else f"{spy_close:.2f}"
    spy_drawdown_text = "N/A" if spy_drawdown is None else f"{spy_drawdown:+.1f}%"
    vix_text = "N/A" if vix_close is None else f"{vix_close:.2f}"

    message = f"""大盤 ETF 每日訊號通知

每日顯示數據：
SPY 收盤: {spy_close_text} (距半年高點 {spy_drawdown_text})
CNN Fear & Greed: {cnn_fear_greed}
VIX: {vix_text}
AAII Bearish: {aaii_bearish}
Smart/Dumb Money: {smart_dumb_money}

條件觸發訊號：
SPY: {spy_signal(spy_drawdown)}
VIX: {vix_signal(vix_close)}
MTUM: {mtum_signal(mtum_df, spy_df)}
"""

    print(message)
    send_webhook(message)


if __name__ == "__main__":
    main()
