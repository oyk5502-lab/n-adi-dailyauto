import json
import os
from datetime import datetime, timezone, timedelta
import pandas as pd
import yfinance as yf

DATA_PATH = "data.json"
BACKFILL_TRADING_DAYS = 60  # 최근 60거래일(약 3개월) 실제 영업일 일괄 갱신


def fetch_fred_series(series_id: str) -> pd.Series:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    df = pd.read_csv(url)
    date_col = df.columns[0]
    val_col = df.columns[1]
    df[val_col] = pd.to_numeric(df[val_col], errors="coerce")
    df = df.dropna(subset=[val_col])
    df[date_col] = pd.to_datetime(df[date_col]).dt.tz_localize(None)
    return df.set_index(date_col)[val_col].sort_index()


def _to_1d_series(df: pd.DataFrame) -> pd.Series:
    s = df["Close"].squeeze()
    if isinstance(s, pd.DataFrame):
        s = s.iloc[:, 0]
    s = pd.to_numeric(s, errors="coerce").dropna()
    s.index = pd.to_datetime(s.index).tz_localize(None)
    return s.sort_index()


def main():
    # 1. 6개월(약 126거래일) 전 수익률 계산을 위해 1년 6개월치 일봉 확보
    ndx_df = yf.download("^NDX", period="18mo", interval="1d", progress=False, auto_adjust=False)
    vxn_df = yf.download("^VXN", period="1y", interval="1d", progress=False, auto_adjust=False)
    irx_df = yf.download("^IRX", period="6mo", interval="1d", progress=False, auto_adjust=False)

    ndx_close = _to_1d_series(ndx_df)
    vxn_close = _to_1d_series(vxn_df)
    irx_close = _to_1d_series(irx_df)

    # 2. FRED 거시 지표 시계열 (일별/월별/분기별 시계열을 날짜 기준으로 정렬 후 asof 매칭)
    m2_s = fetch_fred_series("M2SL")
    m2_yoy_s = ((m2_s / m2_s.shift(12)) - 1.0) * 100.0
    m2_yoy_s = m2_yoy_s.dropna()

    m2v_s = fetch_fred_series("M2V")
    tips_s = fetch_fred_series("DFII10")

    # 3. 기존 data.json 로드
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
    else:
        payload = {"daily_entries": {}}

    daily_entries = payload.get("daily_entries", {})

    # 최근 BACKFILL_TRADING_DAYS 거래일 대상
    start_pos = max(126, len(ndx_close) - BACKFILL_TRADING_DAYS)
    updated_count = 0
    last_summary = ""

    for pos in range(start_pos, len(ndx_close)):
        dt = ndx_close.index[pos]
        date_str = dt.strftime("%Y-%m-%d")
        latest_ndx = float(ndx_close.iloc[pos])

        # 약 6개월(126거래일) 전 종가 대비 연율화 수익률 (%)
        ndx_6m_ago = float(ndx_close.iloc[pos - 126])
        g_ndx_6m = ((latest_ndx / ndx_6m_ago) - 1.0) * 2.0 * 100.0

        # 해당 영업일 기준 VXN 및 직전 20거래일 이동평균
        vxn_upto = vxn_close[vxn_close.index <= dt]
        if len(vxn_upto) == 0:
            continue
        latest_vxn = float(vxn_upto.iloc[-1])
        vxn_20ma = float(vxn_upto.tail(20).mean())

        # 단기국채 파킹 금리 (^IRX)
        irx_upto = irx_close[irx_close.index <= dt]
        rf_rate = float(irx_upto.iloc[-1]) if len(irx_upto) > 0 else 3.75

        # FRED 시계열은 해당 일자 이하의 가장 최근 공표치(asof) 사용
        m2_upto = m2_yoy_s[m2_yoy_s.index <= dt]
        g_m2 = float(m2_upto.iloc[-1]) if len(m2_upto) > 0 else 5.70

        m2v_upto = m2v_s[m2v_s.index <= dt]
        latest_m2v = float(m2v_upto.iloc[-1]) if len(m2v_upto) > 0 else 1.417

        tips_upto = tips_s[tips_s.index <= dt]
        latest_tips = float(tips_upto.iloc[-1]) if len(tips_upto) > 0 else 2.79

        daily_entries[date_str] = {
            "ndx": round(latest_ndx, 2),
            "g_NDX_6M": round(g_ndx_6m, 2),
            "g_M2": round(g_m2, 2),
            "M2V": round(latest_m2v, 3),
            "r_TIPS10": round(latest_tips, 2),
            "VXN": round(latest_vxn, 2),
            "VXN_20MA": round(vxn_20ma, 2),
            "rfRate": round(rf_rate, 2)
        }
        updated_count += 1
        last_summary = (
            f"{date_str}: NDX={latest_ndx:.2f}, g6M={g_ndx_6m:.2f}%, "
            f"TIPS={latest_tips:.2f}%, VXN={latest_vxn:.2f}/{vxn_20ma:.2f}"
        )

    kst_now = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST")
    payload["updated_at"] = kst_now
    payload["daily_entries"] = daily_entries

    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[{kst_now}] Backfilled {updated_count} trading days. Latest -> {last_summary}")


if __name__ == "__main__":
    main()
