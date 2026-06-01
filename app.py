import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import os
import shutil
import plotly.express as px
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timedelta

# --- 核心修正：清理 yfinance 資料庫鎖定 ---
def fix_yf_cache():
    cache_dir = os.path.expanduser('~/.cache/py-yfinance')
    try:
        if os.path.exists(cache_dir):
            shutil.rmtree(cache_dir) 
    except:
        pass

fix_yf_cache()

# --- 1. 核心邏輯：代號自動補全 ---
def get_tw_ticker(raw_symbol):
    raw_symbol = str(raw_symbol).strip()
    if not raw_symbol: return None
    if ".TW" in raw_symbol.upper() or ".TWO" in raw_symbol.upper(): return raw_symbol.upper()
    if raw_symbol.isdigit():
        return f"{raw_symbol}.TW"
    return raw_symbol

# --- 2. 基礎設定 (雲端永久儲存路徑) ---
SAVE_FILE = os.path.expanduser("~/.my_portfolio.csv")

if not os.path.exists(SAVE_FILE):
    try:
        df_init = pd.DataFrame(columns=["代號", "買進單價", "股數"])
        df_init.to_csv(SAVE_FILE, index=False)
    except:
        pass

st.set_page_config(page_title="股票損益監測系統", layout="wide")

# --- 3. 側邊欄與自動刷新 ---
st.sidebar.header("⚙️ 系統設定")
enable_refresh = st.sidebar.checkbox("開啟自動刷新功能", value=True)
refresh_interval = st.sidebar.number_input("刷新頻率 (分鐘)", min_value=1, value=5)

if enable_refresh:
    st_autorefresh(interval=refresh_interval * 60 * 1000, key="mkt_refresh")

# --- 4. 持倉異動功能 ---
st.sidebar.divider()
mode = st.sidebar.radio("持倉異動模式", ["➕ 新增/加碼", "➖ 減倉/賣出"])
input_ticker = st.sidebar.text_input("股票代號 (如 2330)")

try:
    df_portfolio = pd.read_csv(SAVE_FILE)
except:
    df_portfolio = pd.DataFrame(columns=["代號", "買進單價", "股數"])

if mode == "➕ 新增/加碼":
    new_buy_price = st.sidebar.number_input("本次買進單價", min_value=0.0, step=0.1)
    new_shares = st.sidebar.number_input("本次買進股數", min_value=1, step=1)
    if st.sidebar.button("確認執行加碼"):
        if input_ticker:
            final_ticker = get_tw_ticker(input_ticker)
            if final_ticker in df_portfolio["代號"].values:
                old_row = df_portfolio[df_portfolio["代號"] == final_ticker].iloc[0]
                total_s = old_row["股數"] + new_shares
                avg_p = ((old_row["買進單價"] * old_row["股數"]) + (new_buy_price * new_shares)) / total_s
                df_portfolio.loc[df_portfolio["代號"] == final_ticker, ["買進單價", "股數"]] = [round(avg_p, 2), total_s]
            else:
                new_row = pd.DataFrame([[final_ticker, new_buy_price, new_shares]], columns=["代號", "買進單價", "股數"])
                df_portfolio = pd.concat([df_portfolio, new_row], ignore_index=True)
            df_portfolio.to_csv(SAVE_FILE, index=False)
            st.rerun()

else: # 減倉模式
    sell_price = st.sidebar.number_input("本次賣出單價", min_value=0.0, step=0.1)
    sell_shares = st.sidebar.number_input("本次賣出股數", min_value=1, step=1)
    if st.sidebar.button("確認執行減倉"):
        if input_ticker:
            final_ticker = get_tw_ticker(input_ticker)
            if final_ticker in df_portfolio["代號"].values:
                idx = df_portfolio[df_portfolio["代號"] == final_ticker].index[0]
                current_s = df_portfolio.at[idx, "股數"]
                buy_p = df_portfolio.at[idx, "買進單價"]
                
                if sell_shares >= current_s:
                    df_portfolio = df_portfolio.drop(idx)
                else:
                    df_portfolio.at[idx, "股數"] = current_s - sell_shares
                
                df_portfolio.reset_index(drop=True).to_csv(SAVE_FILE, index=False)
                st.rerun()

# --- 5. 主畫面標題 ---
st.title(f"📈 股票損益監測看板")
st.divider()

# --- 6. 運算核心 (全新極速輕量化版：不抓取歷史長線，只抓當下價格) ---
if not df_portfolio.empty:
    results = []
    t_mkt, t_cost, t_today = 0.0, 0.0, 0.0

    with st.spinner('🚀 正在繞過擁堵節點，全速同步即時股價...'):
        for _, row in df_portfolio.iterrows():
            try:
                ticker = str(row['代號']).strip()
                if not ticker or ticker == 'nan': continue
                
                # 💥 終極修正：改用 period="2d" (只抓兩天資料)，不抓一年歷史，下載資料量瞬間縮小 99%，徹底免疫 Yahoo 伺服器塞車！
                df_h = yf.download(ticker, period="2d", progress=False, timeout=3)
                if isinstance(df_h.columns, pd.MultiIndex): 
                    df_h.columns = df_h.columns.droplevel(1)
                
                if not df_h.empty and len(df_h) >= 1:
                    now_p = float(df_h['Close'].iloc[-1])
                    # 如果只有一天資料，昨日現價以今日現價暫代
                    prev_p = float(df_h['Close'].iloc[-2]) if len(df_h) >= 2 else now_p
                    
                    day_change = now_p - prev_p
                    day_profit = day_change * row['股數']
                    
                    cost, val = row['買進單價'] * row['股數'], now_p * row['股數']
                    t_mkt += val
                    t_cost += cost
                    t_today += day_profit
                    
                    results.append({
                        "代號": ticker, 
                        "現價": round(now_p, 2), 
                        "今日漲跌": round(day_change, 2),
                        "今日幅度%": round((day_change/prev_p)*100, 2) if prev_p != 0 else 0,
                        "今日損益": int(day_profit),
                        "股數": row['股數'], 
                        "成本": int(cost), 
                        "市值": int(val), 
                        "損益": int(val - cost),
                        "報酬%": round(((val - cost)/cost)*100, 2) if cost != 0 else 0
                    })
            except Exception as e: 
                continue

    if results:
        # 1. 顯示總損益四大字卡
        if t_cost > 0:
            c1, c2, c3 = st.columns(3)
            profit = t_mkt - t_cost
            c1.metric("累積總損益", f"${int(profit):,}", delta=f"{(profit/t_cost)*100:.2f}%")
            c2.metric("總市值", f"${int(t_mkt):,}")
            c3.metric("今日總變動", f"${int(t_today):,}", delta=f"{int(t_today):,}")

        st.divider()

        # 2. 顯示持倉行情明細表格
        df_res = pd.DataFrame(results)
        st.write("### 📜 持倉行情明細")
        
        color_f = lambda v: f'color: {"#ff4b4b" if v > 0 else "#008000" if v < 0 else "#888888"}; font-weight: bold'
        st.dataframe(df_res.style.map(color_f, subset=['今日漲跌', '今日幅度%', '今日損益', '損益', '報酬%'])\
                                .format({
                                    "成本": "{:,}", "市值": "{:,}", "損益": "{:,}",
                                    "今日損益": "{:+,}", "今日幅度%": "{:.2f}%", "報酬%": "{:.2f}%"
                                }), use_container_width=True)

        st.divider()
        
        # 3. 顯示資產配置圓餅圖
        st.write("### 🍰 現有資產配置比例")
        fig_pie = px.pie(df_res, values='市值', names='代號', hole=0.4)
        fig_pie.update_layout(legend=dict(orientation="h", y=-0.1))
        st.plotly_chart(fig_pie, use_container_width=True)

    # 側邊欄快速管理
    st.sidebar.divider()
    with st.sidebar.expander("🗑️ 快速刪除標的"):
        if not df_portfolio.empty:
            target = st.selectbox("選取股票", options=[f"{i}: {r['代號']}" for i, r in df_portfolio.iterrows()])
            if st.button("完全刪除該標的"):
                df_portfolio.drop(int(target.split(":")[0])).reset_index(drop=True).to_csv(SAVE_FILE, index=False)
                st.rerun()
else:
    st.info("👋 歡迎！請在左側輸入代號開始監測。")
