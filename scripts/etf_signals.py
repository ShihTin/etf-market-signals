import yfinance as yf
import requests
import re
from datetime import datetime, timedelta
import os
import time

# ==================== 設定 ====================
TICKERS = {
    'SPY': 'SPY',
    'VIX': '^VIX',
    'MTUM': 'MTUM'
}

DISCORD_WEBHOOK = os.getenv('DISCORD_WEBHOOK_URL')

# ==================== Helper Functions ====================
def get_historical_high(df, days):
    if df.empty:
        return None
    end = df.index[-1]
    start = end - timedelta(days=days)
    period = df.loc[start:end]
    return period['High'].max() if not period.empty else None

def calculate_drawdown(current, high):
    if not high or high == 0:
        return 0
    return (current - high) / high * 100

def get_cnn_fear_greed():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        url = "https://www.cnn.com/markets/fear-and-greed"
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        # 改進 regex，抓取主要 Fear & Greed 數值
        match = re.search(r'Fear & Greed Index["\s\w]*?(\d{1,3})', resp.text)
        if match:
            return int(match.group(1))
        # 備用抓取
        match2 = re.search(r'(\d{1,3})\s*</?div[^>]*>.*?(?:Fear|Greed)', resp.text, re.IGNORECASE)
        if match2:
            return int(match2.group(1))
    except Exception as e:
        print("CNN 抓取失敗:", e)
    return None

def get_sentimentrader_smart_dumb():
    try:
        url = "https://sentimentrader.com/"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        text = resp.text
        
        smart_match = re.search(r'SMART MONEY.*?([\d.]+)', text, re.IGNORECASE | re.DOTALL)
        dumb_match = re.search(r'DUMB MONEY.*?([\d.]+)', text, re.IGNORECASE | re.DOTALL)
        
        smart = float(smart_match.group(1)) if smart_match else None
        dumb = float(dumb_match.group(1)) if dumb_match else None
        return smart, dumb
    except Exception as e:
        print("SentimenTrader 抓取失敗:", e)
        return None, None

def get_aaii_bearish():
    try:
        url = "https://www.aaii.com/sentimentsurvey"
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=10)
        text = resp.text
        
        # 針對最新 Bearish 百分比
        bearish_match = re.search(r'Bearish[^0-9]*?(\d{1,2}\.\d)', text, re.IGNORECASE | re.DOTALL)
        if bearish_match:
            return float(bearish_match.group(1))
        return None
    except Exception as e:
        print("AAII 抓取失敗:", e)
        return None

def download_with_retry(tickers, period="400d"):
    for attempt in range(3):
        try:
            data = yf.download(tickers, period=period, group_by='ticker', auto_adjust=True, progress=False)
            return data
        except Exception as e:
            print(f"yfinance 嘗試 {attempt+1} 失敗:", e)
            time.sleep(3)
    return None

# ==================== 主程式 ====================
def main():
    signals = []
    daily_info = []

    data = download_with_retry(list(TICKERS.values()))

    latest = {}
    vix_current = None
    for name, ticker in TICKERS.items():
        try:
            if data is not None and ticker in data:
                df = data[ticker].dropna()
                if not df.empty:
                    latest[name] = {'close': df['Close'].iloc[-1], 'df': df}
                    if name == 'VIX':
                        vix_current = round(df['Close'].iloc[-1], 2)
        except:
            continue

    spy = latest.get('SPY')
    mtum = latest.get('MTUM')

    # ==================== 每日必顯示 ====================
    if spy:
        close = spy['close']
        high_6m = get_historical_high(spy['df'], 180)
        dd_6m = calculate_drawdown(close, high_6m)
        daily_info.append(f"**SPY 收盤**: {round(close, 2)} (距半年高點 {round(dd_6m, 1)}%)")

    cnn = get_cnn_fear_greed()
    if cnn is not None:
        daily_info.append(f"**CNN Fear & Greed**: {cnn}")
    else:
        daily_info.append("**CNN Fear & Greed**: 抓取失敗")

    if vix_current:
        daily_info.append(f"**VIX**: {vix_current}")
    else:
        daily_info.append("**VIX**: 抓取失敗")

    aaii = get_aaii_bearish()
    if aaii is not None:
        daily_info.append(f"**AAII Bearish**: {aaii}%")
    else:
        daily_info.append("**AAII Bearish**: 抓取失敗")

    smart, dumb = get_sentimentrader_smart_dumb()
    if smart is not None and dumb is not None:
        daily_info.append(f"**Smart/Dumb Money**: Smart {smart:.2f} | Dumb {dumb:.2f}")
    else:
        daily_info.append("**Smart/Dumb Money**: 抓取失敗")

    # ==================== 觸發訊號 ====================
    if spy:
        close = spy['close']
        df_spy = spy['df']
        high_6m = get_historical_high(df_spy, 180)
        dd_6m = calculate_drawdown(close, high_6m)
        high_1y = get_historical_high(df_spy, 365)
        dd_1y = calculate_drawdown(close, high_1y)

        all_time_high = df_spy['High'].max()
        if abs(close - all_time_high) / all_time_high < 0.001:
            signals.append("🟢 **SPY 創新高**")

        if high_6m and dd_6m <= -5:
            color = "🟡" if dd_6m > -10 else "🟠"
            signals.append(f"{color} **SPY 距半年高點下跌 {abs(round(dd_6m,1))}%**")
        if high_6m and dd_6m <= -15:
            signals.append(f"🔶 **SPY 距半年高點下跌 {abs(round(dd_6m,1))}%**")

        if high_1y and dd_1y <= -20:
            for thresh, color in [(20,"🔴"), (25,"🟣"), (30,"🟣"), (35,"🟣"), (40,"⚫")]:
                if dd_1y <= -thresh:
                    signals.append(f"{color} **SPY 距一年高點下跌 {abs(round(dd_1y,1))}%**")

    if vix_current:
        if 30 <= vix_current < 40:
            signals.append(f"🟡 **VIX = {vix_current}**")
        elif vix_current >= 40:
            signals.append(f"🔴 **VIX = {vix_current}**")

    if mtum:
        close_m = mtum['close']
        df_m = mtum['df']
        high_2m = get_historical_high(df_m, 60)
        dd_m = calculate_drawdown(close_m, high_2m)
        if dd_m <= -5:
            signals.append(f"🌼 **MTUM 距2個月高點下跌 {abs(round(dd_m,1))}%**")

    if cnn is not None:
        if 20 < cnn < 30:
            signals.append(f"🟡 **CNN Fear & Greed = {cnn}**")
        elif cnn <= 20:
            signals.append(f"🔴 **CNN Fear & Greed = {cnn}**")

    if smart is not None and dumb is not None:
        if smart > dumb and smart > 0.7:
            signals.append(f"🟢 **Smart Money 優勢** (Smart: {smart:.2f} > Dumb: {dumb:.2f})")

    # ==================== 發送 ====================
    if DISCORD_WEBHOOK:
        message = "**🌍 大盤 ETF 每日訊號通知**\n"
        message += f"**時間**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        message += "**📊 每日市場概況**\n" + "\n".join(daily_info) + "\n\n"
        
        if signals:
            message += "**🚨 觸發訊號**\n" + "\n".join(signals)
        else:
            message += "**今日無特殊觸發訊號**"

        payload = {"content": message, "username": "Market Signal Bot - ETF"}
        requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
        print("✅ Discord 發送成功")
    else:
        print("❌ Webhook 未設定")

if __name__ == "__main__":
    main()
