import yfinance as yf
import requests
from datetime import datetime
import os

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")


# -------------------------
# SPY 風險階梯（6級）
# -------------------------
def get_spy_signal():
    spy = yf.download("SPY", period="6mo", auto_adjust=True, progress=False)

    close = float(spy["Close"].iloc[-1])
    high_6m = float(spy["Close"].max())

    drawdown = (close - high_6m) / high_6m * 100

    if abs(drawdown) < 0.5:
        return "🟢 SPY 創半年新高"

    elif drawdown <= -30:
        return f"🟣 SPY 距半年高點 {drawdown:.1f}%"

    elif drawdown <= -20:
        return f"🟥🟣 SPY 距半年高點 {drawdown:.1f}%"

    elif drawdown <= -15:
        return f"🔴 SPY 距半年高點 {drawdown:.1f}%"

    elif drawdown <= -10:
        return f"🟠 SPY 距半年高點 {drawdown:.1f}%"

    elif drawdown <= -5:
        return f"🟡 SPY 距半年高點 {drawdown:.1f}%"

    return None


# -------------------------
# VIX 風險燈號
# -------------------------
def get_vix_signal():
    vix = yf.download("^VIX", period="5d", auto_adjust=True, progress=False)

    value = float(vix["Close"].iloc[-1])

    if value > 40:
        return f"🔴 VIX {value:.1f}"
    elif value > 30:
        return f"🟠 VIX {value:.1f}"
    elif value > 25:
        return f"🟡 VIX {value:.1f}"
    elif value < 20:
        return f"🟢 VIX {value:.1f}"

    return None


# -------------------------
# MTUM 動能 + 回撤監控
# -------------------------
def get_mtum_signal():
    spy = yf.download("SPY", period="6mo", auto_adjust=True, progress=False)
    mtum = yf.download("MTUM", period="6mo", auto_adjust=True, progress=False)

    spy_return = (spy["Close"].iloc[-1] / spy["Close"].iloc[0] - 1) * 100
    mtum_return = (mtum["Close"].iloc[-1] / mtum["Close"].iloc[0] - 1) * 100

    mtum_drawdown = (mtum["Close"].iloc[-1] / mtum["Close"].max() - 1) * 100

    signals = []

    # 相對強弱
    if mtum_return > spy_return:
        signals.append(
            f"🟢 MTUM 領先 SPY ({mtum_return:.1f}% vs {spy_return:.1f}%)"
        )
    else:
        signals.append(
            f"⚪ MTUM 落後 SPY ({mtum_return:.1f}% vs {spy_return:.1f}%)"
        )

    # MTUM 動能回撤
    if mtum_drawdown <= -10:
        signals.append(f"🔴 MTUM 距高點 {mtum_drawdown:.1f}%")
    elif mtum_drawdown <= -5:
        signals.append(f"🟡 MTUM 距高點 {mtum_drawdown:.1f}%")

    return signals


# -------------------------
# Discord 發送
# -------------------------
def send_discord(message):
    requests.post(
        DISCORD_WEBHOOK_URL,
        json={"content": message}
    )


# -------------------------
# 主程式
# -------------------------
def main():
    signals = []

    # SPY + VIX
    for fn in [get_spy_signal, get_vix_signal]:
        try:
            r = fn()
            if r:
                signals.append(r)
        except Exception as e:
            signals.append(f"⚠️ {fn.__name__} error: {e}")

    # MTUM（list）
    try:
        mtum_signals = get_mtum_signal()
        if mtum_signals:
            signals.extend(mtum_signals)
    except Exception as e:
        signals.append(f"⚠️ MTUM error: {e}")

    # fallback
    if not signals:
        signals.append("✅ 今日無訊號")

    message = (
        "📈 大盤 ETF 每日訊號通知\n"
        f"時間: {datetime.now():%Y-%m-%d %H:%M}\n\n"
        + "\n".join(signals)
    )

    send_discord(message)

    print("✅ Discord 發送成功")


if __name__ == "__main__":
    main()
