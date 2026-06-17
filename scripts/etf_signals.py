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
        # 備用：直接抓 CNN 網頁
        try:
            resp = requests.get("https://www.cnn.com/markets/fear-and-greed", headers=headers, timeout=10)
            match = re.search(r'Fear & Greed Index["\s\w]*?(\d{1,3})', resp.text)
            if match:
                return int(match.group(1))
        except:
            pass
        return None

def get_sentimentrader_smart_dumb():
    try:
        url = "https://sentimentrader.com/"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        text = resp.text
        smart_match = re.search(r'SMART MONEY.*?([\d.]+)', text, re.IGNORECASE)
        dumb_match = re.search(r'DUMB MONEY.*?([\d.]+)', text, re.IGNORECASE)
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
        # 改善 regex
        bearish_match = re.search(r'Bearish[^0-9]*?(\d{1,2}\.\d)', text, re.IGNORECASE)
        if bearish_match:
            return float(bearish_match.group(1))
        return None
    except Exception as e:
        print("AAII 抓取失敗:", e)
        return None

def download_with_retry(tickers, period="400d"):
    for attempt in range(3):
        try:
            data = yf.download(tickers, period=period, group_by='ticker', auto_adjust=True)
            return data
        except Exception as e:
            print(f"yfinance 嘗試 {attempt+1} 失敗:", e)
            time.sleep(2)
    return None

# ==================== 主程式 ====================
def main():
    signals = []
    daily_info = []

    # 下載資料（加重試）
    data = download_with_retry(list(TICKERS.values()))

    if data is None:
        print("無法下載市場資料")
        # 仍繼續執行其他部分

    latest = {}
    vix_current = None
    for name, ticker in TICKERS.items():
        try:
            if data is not None and ticker in data:
                df = data[ticker].dropna()
                if not df.empty:
                    latest[name] = {
                        'close': df['Close'].iloc[-1],
                        'df': df
                    }
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
        daily_info.append(f"**Smart/Dumb**: Smart {smart:.2f} | Dumb {dumb:.2f}")
    else:
        daily_info.append("**Smart/Dumb**: 抓取失敗")

    # ==================== 觸發訊號（維持原邏輯） ====================
    # ... (SPY 條件、VIX、MTUM、CNN、Smart Money 條件保持不變，我這裡省略以節省篇幅，你可以保留上次版本的這段)

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
        try:
            requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
            print("✅ Discord 發送成功")
        except Exception as e:
            print("Discord 發送失敗:", e)
    else:
        print("❌ DISCORD_WEBHOOK_URL 未設定！")

if __name__ == "__main__":
    main()
