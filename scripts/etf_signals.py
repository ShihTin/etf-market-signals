import yfinance as yf
import requests
from datetime import datetime, timedelta
import os

DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL")


# ==================== Helper Functions ====================

def get_historical_high(df, days):
    if df.empty:
        return None

    end = df.index[-1]
    start = end - timedelta(days=days)

    period = df.loc[start:end]

    if period.empty:
        return None

    return float(period["High"].max())


def calculate_drawdown(current, high):
    if not high or high == 0:
        return 0

    return (current - high) / high * 100


def get_vix_current():
    """取得 VIX"""

    try:
        data = yf.download(
            "^VIX",
            period="10d",
            auto_adjust=False,
            progress=False
        )

        if data.empty:
            return None

        close = data["Close"].squeeze()

        return round(float(close.iloc[-1]), 2)

    except Exception as e:
        print(f"VIX 抓取失敗: {e}")
        return None


# ==================== 主程式 ====================

def main():

    signals = []
    daily_info = []

    try:
        data = yf.download(
            ["SPY", "MTUM"],
            period="400d",
            auto_adjust=True,
            group_by="ticker",
            progress=False
        )

    except Exception as e:
        print(f"ETF資料下載失敗: {e}")
        return

    latest = {}

    for ticker in ["SPY", "MTUM"]:

        try:
            df = data[ticker].dropna()

            if not df.empty:
                latest[ticker] = {
                    "close": float(df["Close"].iloc[-1]),
                    "df": df
                }

        except Exception as e:
            print(f"{ticker}資料錯誤: {e}")

    spy = latest.get("SPY")
    mtum = latest.get("MTUM")

    vix_current = get_vix_current()

    # ==================== 每日市場概況 ====================

    if spy:

        close = spy["close"]

        high_6m = get_historical_high(
            spy["df"],
            180
        )

        dd_6m = calculate_drawdown(
            close,
            high_6m
        )

        daily_info.append(
            f"**SPY 收盤**: {close:.2f} (距半年高點 {dd_6m:.1f}%)"
        )

    else:
        daily_info.append("**SPY 收盤**: 抓取失敗")

    daily_info.append(
        f"**VIX**: {vix_current if vix_current is not None else '抓取失敗'}"
    )

    daily_info.append("**AAII Bearish**: 暫停")
    daily_info.append("**Smart/Dumb Money**: 暫停")

    # ==================== SPY 訊號 ====================

    if spy:

        close = spy["close"]
        df_spy = spy["df"]

        high_6m = get_historical_high(df_spy, 180)
        high_1y = get_historical_high(df_spy, 365)

        dd_6m = calculate_drawdown(close, high_6m)
        dd_1y = calculate_drawdown(close, high_1y)

        # 創歷史新高
        all_time_high = float(df_spy["High"].max())

        if abs(close - all_time_high) / all_time_high < 0.001:
            signals.append("🟢 **SPY 創歷史新高**")

        # 半年高點回撤
        if dd_6m <= -15:
            signals.append(
                f"🔶 **SPY 距半年高點下跌 {abs(dd_6m):.1f}%**"
            )

        elif dd_6m <= -10:
            signals.append(
                f"🟠 **SPY 距半年高點下跌 {abs(dd_6m):.1f}%**"
            )

        elif dd_6m <= -5:
            signals.append(
                f"🟡 **SPY 距半年高點下跌 {abs(dd_6m):.1f}%**"
            )

        # 一年高點回撤
        if dd_1y <= -40:
            signals.append(
                f"⚫ **SPY 距一年高點下跌 {abs(dd_1y):.1f}%**"
            )

        elif dd_1y <= -35:
            signals.append(
                f"🟣 **SPY 距一年高點下跌 {abs(dd_1y):.1f}%**"
            )

        elif dd_1y <= -30:
            signals.append(
                f"🟣 **SPY 距一年高點下跌 {abs(dd_1y):.1f}%**"
            )

        elif dd_1y <= -25:
            signals.append(
                f"🟣 **SPY 距一年高點下跌 {abs(dd_1y):.1f}%**"
            )

        elif dd_1y <= -20:
            signals.append(
                f"🔴 **SPY 距一年高點下跌 {abs(dd_1y):.1f}%**"
            )

    # ==================== MTUM 相對強弱 ====================

    if spy and mtum:

        try:

            spy_6m_return = (
                spy["close"] /
                float(spy["df"]["Close"].iloc[-126]) - 1
            ) * 100

            mtum_6m_return = (
                mtum["close"] /
                float(mtum["df"]["Close"].iloc[-126]) - 1
            ) * 100

            daily_info.append(
                f"**SPY 6個月報酬**: {spy_6m_return:.1f}%"
            )

            daily_info.append(
                f"**MTUM 6個月報酬**: {mtum_6m_return:.1f}%"
            )

            if mtum_6m_return > spy_6m_return:
                signals.append(
                    f"🟢 **MTUM 領先 SPY ({mtum_6m_return:.1f}% vs {spy_6m_return:.1f}%)**"
                )

            else:
                signals.append(
                    f"🟡 **MTUM 落後 SPY ({mtum_6m_return:.1f}% vs {spy_6m_return:.1f}%)**"
                )

        except Exception as e:
            print(f"MTUM比較失敗: {e}")

    # ==================== VIX 訊號 ====================

    if vix_current is not None:

        if vix_current >= 40:
            signals.append(
                f"🔴 **VIX = {vix_current}**"
            )

        elif vix_current >= 30:
            signals.append(
                f"🟡 **VIX = {vix_current}**"
            )

    # ==================== Discord ====================

    if DISCORD_WEBHOOK:

        message = (
            "**🌍 大盤 ETF 每日訊號通知**\n"
            f"**時間**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            "**📊 每日市場概況**\n"
            + "\n".join(daily_info)
            + "\n\n"
        )

        if signals:
            message += (
                "**🚨 觸發訊號**\n"
                + "\n".join(signals)
            )
        else:
            message += (
                "**今日無特殊觸發訊號**"
            )

        try:

            requests.post(
                DISCORD_WEBHOOK,
                json={
                    "content": message,
                    "username": "Market Signal Bot - ETF"
                },
                timeout=15
            )

            print("✅ Discord 發送成功")

        except Exception as e:
            print(f"Discord 發送失敗: {e}")


if __name__ == "__main__":
    main()
