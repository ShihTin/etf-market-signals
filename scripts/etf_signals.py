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
    """修正後的 CNN 抓取（目前應抓到 40）"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        resp = requests.get("https://www.cnn.com/markets/fear-and-greed", headers=headers, timeout=15)
        resp.raise_for_status()
        # 加強 regex 抓取
        match = re.search(r'Fear & Greed Index["\s\w]*?(\d{1,3})', resp.text)
        if match:
            return int(match.group(1))
        match2 = re.search(r'(\d{1,3})\s*(?:</div>|<div[^>]*class="[^"]*index[^"]*"|Fear)', resp.text, re.IGNORECASE)
        if match2:
            return int(match2.group(1))
    except Exception as e:
        print("CNN 抓取失敗:", e)
    return None

def get_sentimentrader_smart_dumb():
    try:
        resp = requests.get("https://sentimentrader.com/", 
                           headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}, 
                           timeout=15)
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
    """嘗試 MacroMicro + AAII 官網"""
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        # 先試 MacroMicro
        resp = requests.get("https://www.macromicro.me/charts/20828/us-aaii-sentimentsurvey", headers=headers, timeout=10)
        text = resp.text
        match = re.search(r'Bearish[^0-9]*?(\d{1,2}\.\d)', text, re.IGNORECASE | re.DOTALL)
        if match:
            return float(match.group(1))
    except:
        pass
    
    try:
        # 備用 AAII 官網
        resp = requests.get("https://www.aaii.com/sentimentsurvey", headers=headers, timeout=10)
        text = resp.text
        match = re.search(r'Bearish[^0-9]*?(\d{1,2}\.\d)', text, re.IGNORECASE | re.DOTALL)
        if match:
            return float(match.group(1))
    except Exception as e:
        print("AAII 抓取失敗:", e)
    return None

def get_vix_current():
    """優先 yfinance，其次 Yahoo"""
    try:
        data = yf.download('^VIX', period="5d", progress=False)
        if not data.empty:
            return round(data['Close'].iloc[-1], 2)
    except:
        pass
    try:
        resp = requests.get("https://finance.yahoo.com/quote/%5EVIX", 
                           headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        match = re.search(r'([\d.]{3,6})\s*(?:<|VIX)', resp.text)
        if match:
            return float(match.group(1))
    except:
        pass
    return None

# ==================== 主程式 ====================
def main():
    signals = []
    daily_info = []

    data = yf.download(list(TICKERS.values()), period="400d", group_by='ticker', auto_adjust=True, progress=False)

    latest = {}
    vix_current = get_vix_current()

    for name, ticker in TICKERS.items():
        try:
            if ticker in data:
                df = data[ticker].dropna()
                if not df.empty:
                    latest[name] = {'close': df['Close'].iloc[-1], 'df': df}
        except:
            continue

    spy = latest.get('SPY')
    mtum = latest.get('MTUM')

    # ==================== 每日市場概況 ====================
    if spy:
        close = spy['close']
        high_6m = get_historical_high(spy['df'], 180)
        dd_6m = calculate_drawdown(close, high_6m)
        daily_info.append(f"**SPY 收盤**: {round(close, 2)} (距半年高點 {round(dd_6m, 1)}%)")

    cnn = get_cnn_fear_greed()
    daily_info.append(f"**CNN Fear & Greed**: {cnn if cnn is not None else '抓取失敗'}")

    daily_info.append(f"**VIX**: {vix_current if vix_current else '抓取失敗'}")

    aaii = get_aaii_bearish()
    daily_info.append(f"**AAII Bearish**: {aaii if aaii is not None else '抓取失敗'}%")

    smart, dumb = get_sentimentrader_smart_dumb()
    if smart is not None and dumb is not None:
        daily_info.append(f"**Smart/Dumb Money**: Smart {smart:.2f} | Dumb {dumb:.2f}")
    else:
        daily_info.append("**Smart/Dumb Money**: 抓取失敗")

    # ==================== 觸發訊號 ====================
    if vix_current:
        if 30 <= vix_current < 40:
            signals.append(f"🟡 **VIX = {vix_current}**")
        elif vix_current >= 40:
            signals.append(f"🔴 **VIX = {vix_current}**")

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

        requests.post(DISCORD_WEBHOOK, json={"content": message, "username": "Market Signal Bot - ETF"}, timeout=10)
        print("✅ Discord 發送成功")

if __name__ == "__main__":
    main()
