import json
import os
from datetime import datetime, timezone, timedelta
import pandas as pd
import yfinance as yf

DATA_PATH = "data.json"


def fetch_fred_series(series_id: str) -> pd.Series:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    df = pd.read_csv(url)
    date_col = df.columns[0]
    val_col = df.columns[1]
    df[val_col] = pd.to_numeric(df[val_col], errors="coerce")
    df = df.dropna(subset=[val_col])
    df[date_col] = pd.to_datetime(df[date_col])
    return df.set_index(date_col)[val_col].sort_index()


def main():
    # 1. 나스닥 100 (^NDX), VXN (^VXN), 3개월 T-Bill (^IRX 파킹금리) 다운로드
    ndx_df = yf.download("^NDX", period="1y", interval="1d", progress=False)
    vxn_df = yf.download("^VXN", period="6mo", interval="1d", progress=False)
    irx_df = yf.download("^IRX", period="1mo", interval="1d", progress=False)

    ndx_close = ndx_df["Close"].squeeze().dropna()
    vxn_close = vxn_df["Close"].squeeze().dropna()
    irx_close = irx_df["Close"].squeeze().dropna()

    latest_dt = ndx_close.index[-1]
    latest_date_str = latest_dt.strftime("%Y-%m-%d")
    latest_ndx = float(ndx_close.iloc[-1])

    # 6개월(약 126거래일) 전 대비 연율화 수익률 (%)
    idx_6m = max(0, len(ndx_close) - 127)
    ndx_6m_ago = float(ndx_close.iloc[idx_6m])
    g_ndx_6m = ((latest_ndx / ndx_6m_ago) - 1.0) * 2.0 * 100.0

    # VXN 최신 종가 및 최근 20거래일 이동평균
    latest_vxn = float(vxn_close.iloc[-1])
    vxn_20ma = float(vxn_close.tail(20).mean())

    # 단기국채 파킹 금리 (%)
    rf_rate = float(irx_close.iloc[-1]) if len(irx_close) > 0 else 3.75

    # 2. FRED 거시 지표 (M2 YoY %, M2V, 10년물 TIPS 실질금리 %)
    m2_s = fetch_fred_series("M2SL")
    g_m2 = ((float(m2_s.iloc[-1]) / float(m2_s.iloc[-13])) - 1.0) * 100.0

    m2v_s = fetch_fred_series("M2V")
    latest_m2v = float(m2v_s.iloc[-1])

    tips_s = fetch_fred_series("DFII10")
    latest_tips = float(tips_s.iloc[-1])

    # 3. 기존 data.json 불러오기 및 오늘 날짜 누적
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
    else:
        payload = {"daily_entries": {}}

    kst_now = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST")
    payload["updated_at"] = kst_now
    payload["daily_entries"][latest_date_str] = {
        "ndx": round(latest_ndx, 2),
        "g_NDX_6M": round(g_ndx_6m, 2),
        "g_M2": round(g_m2, 2),
        "M2V": round(latest_m2v, 3),
        "r_TIPS10": round(latest_tips, 2),
        "VXN": round(latest_vxn, 2),
        "VXN_20MA": round(vxn_20ma, 2),
        "rfRate": round(rf_rate, 2)
    }

    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[{kst_now}] Updated {latest_date_str}: NDX={latest_ndx:.2f}, g6M={g_ndx_6m:.2f}%, TIPS={latest_tips:.2f}%, VXN={latest_vxn:.2f}/{vxn_20ma:.2f}")


if __name__ == "__main__":
    main()