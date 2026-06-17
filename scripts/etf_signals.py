import yfinance as yf
import requests
import re
from datetime import datetime, timedelta
import os

# ==================== 設定 ====================
TICKERS = {
    'SPY': 'SPY',
    'VIX': '^VIX',
    'MTUM': 'MTUM'
}

DISCORD_WEBHOOK = os.getenv('DISCORD_WEBHOOK_URL')

# ==================== Helper Functions ====================
def get_historical_high(df, days):
    end = df.index[-1]
    start = end - timedelta(days=days)
    period = df.loc[start:end] if not df.empty else df
    return period['High'].max() if not period.empty else None

def calculate_drawdown(current, high):
    if not high or high == 0:
        return 0
    return (current - high) / high * 100

def get_cnn_fear_greed():
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata/"
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()
        latest = data['fear_and_greed_historical']['data'][-1]
        return int(latest['score'])
    except Exception as e:
        print("CNN 抓取失敗:", e)
        return None

def get_sentimentrader_smart_dumb():
    try:
        url = "https://sentimentrader.com/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        text = resp.text
        
        smart_match = re.search(r'SMART MONEY \(?\s*([\d.]+)', text, re.IGNORECASE)
        dumb_match = re.search(r'DUMB MONEY \(?\s*([\d.]+)', text, re.IGNORECASE)
        
        smart = float(smart_match.group(1)) if smart_match else None
        dumb = float(dumb_match.group(1)) if dumb_match else None
        return smart, dumb
    except Exception as e:
        print("SentimenTrader 抓取失敗:", e)
        return None, None

def get_aaii_bearish():
    """抓取 AAII Bearish %"""
    try:
        url = "https://www.aaii.com/sentimentsurvey"
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=10)
        text = resp.text
        
        # 抓取最新的 Bearish 百分比
        bearish_match = re.search(r'Bearish\s*[\d.]+\s*%\s*([\d.]+)%', text, re.IGNORECASE)
        if not bearish_match:
            bearish_match = re.search(r'(\d{1,2}\.\d)%\s*(?:</td>|\s+)</?t[rd]', text)  # 備用 pattern
        bearish = float(bearish_match.group(1)) if bearish_match else None
        return bearish
    except Exception as e:
        print("AAII 抓取失敗:", e)
        return None

# ==================== 主程式 ====================
def main():
    signals = []          # 觸發條件訊號
    daily_info = []       # 每日必顯示的資訊

    # 下載資料
    data = yf.download(list(TICKERS.values()), period="400d", group_by='ticker', auto_adjust=True)

    latest = {}
    for name, ticker in TICKERS.items():
        if ticker in data:
            df = data[ticker].dropna()
            if not df.empty:
                latest[name] = {
                    'close': df['Close'].iloc[-1],
                    'high_6m': get_historical_high(df, 180),
                    'df': df
                }
                if name == 'VIX':
                    vix_current = round(df['Close'].iloc[-1], 2)

    spy = latest.get('SPY')
    vix_current = latest.get('VIX', {}).get('close')
    mtum = latest.get('MTUM')

    # ==================== 每日必顯示資訊 ====================
    # 1. SPY 距離半年高點 %
    if spy:
        spy_close = spy['close']
        high_6m = spy['high_6m']
        dd_6m = calculate_drawdown(spy_close, high_6m)
        daily_info.append(f"**SPY 收盤**: {round(spy_close, 2)} (距半年高點 {round(dd_6m, 1)}%)")

    # 2. CNN Fear & Greed
    cnn = get_cnn_fear_greed()
    if cnn is not None:
        daily_info.append(f"**CNN Fear & Greed**: {cnn}")

    # 3. VIX
    if vix_current:
        daily_info.append(f"**VIX**: {vix_current}")

    # 4. AAII Bearish
    aaii_bearish = get_aaii_bearish()
    if aaii_bearish is not None:
        daily_info.append(f"**AAII Bearish**: {aaii_bearish}%")

    # 5. Smart vs Dumb Money
    smart, dumb = get_sentimentrader_smart_dumb()
    if smart is not None and dumb is not None:
        daily_info.append(f"**Smart/Dumb Money**: Smart {smart:.2f} | Dumb {dumb:.2f}")

    # ==================== 觸發訊號條件 ====================
    # 原有 SPY 創新高 & 跌幅條件...
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
            color_map = {20:"🔴", 25:"🟣", 30:"🟣", 35:"🟣", 40:"⚫"}
            for thresh in [20,25,30,35,40]:
                if dd_1y <= -thresh:
                    signals.append(f"{color_map.get(thresh,'🔴')} **SPY 距一年高點下跌 {abs(round(dd_1y,1))}%**")

    # VIX
    if vix_current:
        if 30 <= vix_current < 40:
            signals.append(f"🟡 **VIX = {vix_current}**")
        elif vix_current >= 40:
            signals.append(f"🔴 **VIX = {vix_current}**")

    # MTUM
    if mtum:
        close_m = mtum['close']
        df_m = mtum['df']
        high_2m = get_historical_high(df_m, 60)
        dd_m = calculate_drawdown(close_m, high_2m)
        if dd_m <= -5:
            signals.append(f"🌼 **MTUM 距2個月高點下跌 {abs(round(dd_m,1))}%**")

    # CNN
    if cnn is not None:
        if 20 < cnn < 30:
            signals.append(f"🟡 **CNN Fear & Greed = {cnn}**")
        elif cnn <= 20:
            signals.append(f"🔴 **CNN Fear & Greed = {cnn}**")

    # Smart > Dumb 且 Smart > 0.7
    if smart is not None and dumb is not None:
        if smart > dumb and smart > 0.7:
            signals.append(f"🟢 **Smart Money 優勢** (Smart: {smart:.2f} > Dumb: {dumb:.2f})")

    # ==================== 發送 Discord ====================
    if daily_info or signals:
        message = "**🌍 大盤 ETF 每日訊號通知**\n"
        message += f"**時間**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        
        # 每日必顯示區塊
        message += "**📊 每日市場概況**\n"
        message += "\n".join(daily_info) + "\n\n"
        
        # 觸發訊號區塊
        if signals:
            message += "**🚨 觸發訊號**\n"
            message += "\n".join(signals)
        else:
            message += "**今日無特殊觸發訊號**"

        payload = {
            "content": message,
            "username": "Market Signal Bot - ETF"
        }
        
        if DISCORD_WEBHOOK:
            requests.post(DISCORD_WEBHOOK, json=payload)
        print("已發送每日通知")
    else:
        print("無資料可發送")

if __name__ == "__main__":
    main()
