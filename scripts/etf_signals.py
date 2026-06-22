import os
import re
import requests
import yfinance as yf
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime, timezone


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

    if df.empty:
        return pd.DataFrame()

    df["ma50"] = df["Close"].rolling(50).mean()
    df["ma200"] = df["Close"].rolling(200).mean()

    return df


def latest_close(df: pd.DataFrame):
    if df.empty:
        return None

    return safe_float(df.iloc[-1]["Close"])


def latest_ma(df: pd.DataFrame, column: str):
    if df.empty or column not in df.columns:
        return None

    return safe_float(df.iloc[-1][column])


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


def ma_position_text(close, ma_value, ma_name):
    if close is None or ma_value is None:
        return f"{ma_name} N/A"

    position = "高於" if close >= ma_value else "低於"
    return f"{position}{ma_name} ({ma_value:.2f})"


def spy_signal(drawdown_pct):
    if drawdown_pct is None:
        return "N/A"

    if drawdown_pct >= -0.1:
        return "新高 綠色標籤"

    if drawdown_pct <= -40:
        return "-40% 黑色標籤"
    if drawdown_pct <= -35:
        return "-35% 紫紅色標籤"
    if drawdown_pct <= -30:
        return "-30% 紫色標籤"
    if drawdown_pct <= -20:
        return "-20% 紅色標籤"
    if drawdown_pct <= -15:
        return "-15% 橘紅色標籤"
    if drawdown_pct <= -10:
        return "-10% 橘色標籤"
    if drawdown_pct <= -5:
        return "-5% 黃色標籤"

    return "正常"


def vix_signal(vix_value):
    if vix_value is None:
        return "N/A"

    if vix_value >= 40:
        return ">=40 黑色標籤"
    if vix_value >= 30:
        return ">=30且<40 紅色標籤"
    if vix_value >= 25:
        return ">=25且<30 黃色標籤"

    return "正常"


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
        return "N/A"

    relative = mtum_ret - spy_ret
    direction = "領先 SPY" if relative >= 0 else "落後 SPY"

    if relative <= -10:
        decay = "-10% 動能衰退"
    elif relative <= -5:
        decay = "-5% 動能衰退"
    else:
        decay = "無明顯衰退"

    return f"{direction} ({relative:+.2f}%) / {decay}"


def fear_greed_label(score):
    if score <= 25:
        return "Extreme Fear"
    if score < 50:
        return "Fear"
    if score == 50:
        return "Neutral"
    if score < 75:
        return "Greed"
    return "Extreme Greed"


def find_fear_greed_score(data):
    if isinstance(data, dict):
        if "fear_and_greed" in data:
            node = data["fear_and_greed"]
            if isinstance(node, dict) and "score" in node:
                return node.get("score"), node.get("rating")

        if "score" in data and ("rating" in data or "classification" in data):
            return data.get("score"), data.get("rating") or data.get("classification")

        for value in data.values():
            score, rating = find_fear_greed_score(value)
            if score is not None:
                return score, rating

    if isinstance(data, list):
        for item in data:
            score, rating = find_fear_greed_score(item)
            if score is not None:
                return score, rating

    return None, None


def get_fear_greed():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    urls = [
        "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
        f"https://production.dataviz.cnn.io/index/fearandgreed/graphdata/{today}",
    ]

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json,text/plain,*/*",
    }

    for url in urls:
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            data = response.json()
            score, rating = find_fear_greed_score(data)

            if score is None:
                continue

            score = float(score)
            label = rating if rating else fear_greed_label(score)

            return f"{score:.0f} ({label})"

        except Exception:
            continue

    return "N/A"


def get_aaii_bearish():
    try:
        url = "https://www.aaii.com/sentimentsurvey"
        headers = {
            "User-Agent": "Mozilla/5.0",
        }

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        lines = [
            line.strip()
            for line in soup.get_text("\n").splitlines()
            if line.strip()
        ]

        date_pattern = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")
        percent_pattern = re.compile(r"^\d+(\.\d+)?%$")

        for i, line in enumerate(lines):
            if not date_pattern.match(line):
                continue

            percentages = []

            for next_line in lines[i + 1 : i + 12]:
                if percent_pattern.match(next_line):
                    percentages.append(next_line)

                if len(percentages) == 3:
                    break

            if len(percentages) == 3:
                week_ending = line
                bearish = percentages[2]
                return f"{bearish} ({week_ending})"

        return "N/A"

    except Exception:
        return "N/A"


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
    spy_ma50 = latest_ma(spy_df, "ma50")
    spy_ma200 = latest_ma(spy_df, "ma200")
    vix_close = latest_close(vix_df)

    fear_greed = get_fear_greed()
    aaii_bearish = get_aaii_bearish()

    spy_close_text = "N/A" if spy_close is None else f"{spy_close:.2f}"
    spy_drawdown_text = "N/A" if spy_drawdown is None else f"{spy_drawdown:+.1f}%"
    vix_text = "N/A" if vix_close is None else f"{vix_close:.2f}"

    spy_ma50_text = ma_position_text(spy_close, spy_ma50, "50MA")
    spy_ma200_text = ma_position_text(spy_close, spy_ma200, "200MA")

    message = f"""大盤 ETF 每日訊號通知

每日顯示數據：
SPY 收盤: {spy_close_text} [距半年高點 {spy_drawdown_text}、{spy_ma50_text}、{spy_ma200_text}]
Fear & Greed: {fear_greed}
VIX: {vix_text}
AAII Bearish: {aaii_bearish}

條件觸發訊號：
SPY: {spy_signal(spy_drawdown)}
VIX: {vix_signal(vix_close)}
MTUM: {mtum_signal(mtum_df, spy_df)}
"""

    print(message)
    send_webhook(message)


if __name__ == "__main__":
    main()
