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
    """CNN Fear & Greed - 使用官方 JSON API"""
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata/"
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        latest = data['fear_and_greed_historical']['data'][-1]
        return int(latest['score'])
    except Exception as e:
        print("CNN 抓取失敗:", e)
        return None

def get_macromicro_smart_dumb():
    """Smart vs Dumb Money - MacroMicro"""
    try:
        url = "https://www.macromicro.me/charts/128350/us-smart-vs-dumb-money-confidence"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        resp = requests.get(url, headers=headers, timeout=15)
        text = resp.text
        
        smart_match = re.search(r'Smart Money.*?([\d.]{3,})', text, re.IGNORECASE | re.DOTALL)
        dumb_match = re.search(r'Dumb Money.*?([\d.]{3,})', text, re.IGNORECASE | re.DOTALL)
        
        smart = float(smart_match.group(1)) if smart_match else None
        dumb = float(dumb_match.group(1)) if dumb_match else None
        return smart, dumb
    except Exception as e:
        print("MacroMicro Smart/Dumb 抓取失敗:", e)
        return None, None

def get_aaii_bearish():
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        resp = requests.get("https://www.macromicro.me/charts/20828/us-aaii-sentimentsurvey", 
                           headers=headers, timeout=10)
        text = resp.text
        match = re.search(r'Bearish[^0-9]*?(\d{1,2}\.\d)', text, re.IGNORECASE | re.DOTALL)
        if match:
            return float(match.group(1))
    except:
        pass
    try:
        resp = requests.get("https://www.aaii.com/sentimentsurvey", headers=headers, timeout=10)
        text = resp.text
        match = re.search(r'Bearish[^0-9]*?(\d{1,2}\.\d)', text, re.IGNORECASE | re.DOTALL)
        if match:
            return float(match.group(1))
    except Exception as e:
        print("AAII 抓取失敗:", e)
    return None

def get_vix_current():
    for attempt in range(3):
        try:
            data = yf.download('^VIX', period="5d", progress=False)
            if not data.empty:
                return round(float(data['Close'].iloc[-1]), 2)
        except:
            time.sleep(2)
    return None

# ==================== 主程式 ====================
def main():
    signals = []
    daily_info = []

    data = yf.download(['SPY', 'MTUM'], period="400d", group_by='ticker', auto_adjust=True, progress=False)

    latest = {}
    for t in ['SPY', 'MTUM']:
        try:
            if t in data:
                df = data[t].dropna()
                if not df.empty:
                    latest[t] = {'close': df['Close'].iloc[-1], 'df': df}
        except:
            continue

    spy = latest.get('SPY')
    mtum = latest.get('MTUM')
    vix_current = get_vix_current()

    # ==================== 每日市場概況 ====================
    if spy:
        close = spy['close']
        high_6m = get_historical_high(spy['df'], 180)
        dd_6m = calculate_drawdown(close, high_6m)
        daily_info.append(f"**SPY 收盤**: {round(close, 2)} (距半年高點 {round(dd_6m, 1)}%)")

    cnn = get_cnn_fear_greed()
    daily_info.append(f"**CNN Fear & Greed**: {cnn if cnn is not None else '抓取失敗'}")

    daily_info.append(f"**VIX**: {vix_current if vix_current is not None else '抓取失敗'}")

    aaii = get_aaii_bearish()
    daily_info.append(f"**AAII Bearish**: {aaii if aaii is not None else '抓取失敗'}%")

    smart, dumb = get_macromicro_smart_dumb()
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

if __name__ == "__main__":
    main()
