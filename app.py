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
import pytz

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

# 基準日與對照組
st.sidebar.divider()
st.sidebar.header("📅 損益與對照設定")
default_base = datetime.now() - timedelta(days=2)
base_date = st.sidebar.date_input("區段比較基準日", value=default_base)
benchmark_input = st.sidebar.text_input("對照代號", value="0050, ^TWII")

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
                    realized_profit = (sell_price - buy_p) * current_s
                    st.sidebar.warning(f"已全數清倉 {final_ticker}，實現損益約: ${int(realized_profit):,}")
                else:
                    df_portfolio.at[idx, "股數"] = current_s - sell_shares
                    realized_profit = (sell_price - buy_p) * sell_shares
                    st.sidebar.success(f"{final_ticker} 已減倉，本次實現損益約: ${int(realized_profit):,}")
                
                df_portfolio.reset_index(drop=True).to_csv(SAVE_FILE, index=False)
                st.rerun()
            else:
                st.sidebar.error("找不到該股票持倉")

# --- 5. 主畫面數據獲取 ---
st.title(f"📈 股票損益監測看板")

# 💥 脫鉤修正：如果大盤接口塞車，自動留下一行提示並跳過，絕對不拖累下方個人庫存的載入速度
try:
    twii = yf.download("^TWII", period="5d", progress=False, timeout=3)
    if isinstance(twii.columns, pd.MultiIndex): 
        twii.columns = twii.columns.droplevel(1)
    if not twii.empty and len(twii) >= 2:
        p = float(twii['Close'].iloc[-1])
        c = p - float(twii['Close'].iloc[-2])
        pct = (c / float(twii['Close'].iloc[-2])) * 100
        st.markdown(f"### 🇹🇼 台灣加權指數：**{p:,.2f}** <span style='color:{'#ff4b4b' if c > 0 else '#008000'}'>({'▲' if c > 0 else '▼'} {abs(c):.2f}, {pct:.2f}%)</span>", unsafe_allow_html=True)
    else:
        st.info("ℹ️ 今日大盤即時流量較高，現貨加權指數快取同步中...")
except Exception as e:
    st.info("ℹ️ 今日大盤即時流量較高，現貨加權指數快取同步中...")

st.divider()

# --- 6. 運算核心 ---
if not df_portfolio.empty:
    results, history_combined = [], pd.DataFrame()
    t_mkt, t_cost, t_today, t_period = 0.0, 0.0, 0.0, 0.0
    individual_stocks_data = {}

    with st.spinner('正在為您同步庫存個股市場數據...'):
        for _, row in df_portfolio.iterrows():
            try:
                ticker = row['代號']
                df_h = yf.download(ticker, period="2y", progress=False, timeout=3).sort_index()
                if isinstance(df_h.columns, pd.MultiIndex): 
                    df_h.columns = df_h.columns.droplevel(1)
                
                df_h.index = pd.to_datetime(df_h.index).tz_localize(None)
                
                if not df_h.empty and len(df_h) >= 2:
                    now_p = float(df_h['Close'].iloc[-1])
                    prev_p = float(df_h['Close'].iloc[-2])
                    
                    base_df = df_h[df_h.index <= pd.Timestamp(base_date)]
                    base_p = float(base_df['Close'].iloc[-1]) if not base_df.empty else float(df_h['Close'].iloc[0])
                    
                    day_change = now_p - prev_p
                    day_profit = day_change * row['股數']
                    
                    cost, val = row['買進單價'] * row['股數'], now_p * row['股數']
                    t_mkt += val; t_cost += cost
                    t_today += day_profit
                    t_period += (now_p - base_p) * row['股數']
                    
                    results.append({
                        "代號": ticker, 
                        "現價": round(now_p, 2), 
                        "今日漲跌": round(day_change, 2),
                        "今日幅度%": round((day_change/prev_p)*100, 2),
                        "今日損益": int(day_profit),
                        "區段變動": round(now_p - base_p, 2), 
                        "股數": row['股數'], 
                        "成本": int(cost), 
                        "市值": int(val), 
                        "損益": int(val - cost),
                        "報酬%": round(((val - cost)/cost)*100, 2) if cost != 0 else 0
                    })
                    history_combined[ticker] = df_h['Close'].tail(260) * row['股數']
                    individual_stocks_data[ticker] = df_h
            except Exception as e: 
                continue

    if results:
        if t_cost > 0:
            c1, c2, c3, c4 = st.columns(4)
            profit = t_mkt - t_cost
            c1.metric("累積總損益", f"${int(profit):,}", delta=f"{(profit/t_cost)*100:.2f}%")
            c2.metric("總市值", f"${int(t_mkt):,}")
            c3.metric("今日總變動", f"${int(t_today):,}", delta=f"{int(t_today):,}")
            c4.metric("區段總變動", f"${int(t_period):,}", delta=f"{int(t_period):,}")

        st.divider()

        df_res = pd.DataFrame(results)
        st.write("### 📜 持倉行情明細")
        
        color_f = lambda v: f'color: {"#ff4b4b" if v > 0 else "#008000" if v < 0 else "#888888"}; font-weight: bold'
        st.dataframe(df_res.style.map(color_f, subset=['今日漲跌', '今日幅度%', '今日損益', '區段變動', '損益', '報酬%'])\
                                .format({
                                    "成本": "{:,}", "市值": "{:,}", "損益": "{:,}",
                                    "今日損益": "{:+,}", "今日幅度%": "{:.2f}%", "報酬%": "{:.2f}%"
                                }), use_container_width=True)

        st.write("---")
        col_c1, col_c2 = st.columns([2, 1])
        with col_c1:
            st.write("### 📊 資產累積走勢與對照組")
            if not history_combined.empty:
                history_combined['Total'] = history_combined.sum(axis=1)
                valid_h = history_combined['Total'].dropna()
                if not valid_h.empty:
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=valid_h.index, y=valid_h.values, name='我的總資產', line=dict(color='#00CC96', width=4)))
                    s_val = valid_h.iloc[0]; s_date = valid_h.index[0]
                    for b in [s.strip() for s in benchmark_input.split(",") if s.strip()]:
                        try:
                            bt = get_tw_ticker(b)
                            bh = yf.download(bt, period="2y", progress=False)
                            if isinstance(bh.columns, pd.MultiIndex): 
                                bh.columns = bh.columns.droplevel(1)
                            if not bh.empty:
                                bh_c = bh['Close'].squeeze(); bh_c.index = pd.to_datetime(bh_c.index).tz_localize(None)
                                bh_f = bh_c[bh_c.index >= s_date]
                                if not bh_f.empty:
                                    fig.add_trace(go.Scatter(x=bh_f.index, y=(bh_f/bh_f.iloc[0])*s_val, name=f'對照: {bt}', line=dict(dash='dash', width=2)))
                        except: continue
                    fig.add_hline(y=t_cost, line_dash="dot", line_color="red", annotation_text="平均成本線")
                    fig.update_layout(hovermode="x unified", legend=dict(orientation="h", y=-0.2))
                    st.plotly_chart(fig, use_container_width=True)
        with col_c2:
            st.write("### 🍰 資產配置")
            st.plotly_chart(px.pie(df_res, values='市值', names='代號', hole=0.4), use_container_width=True)

        # --- 📈 個股均線走勢圖 ---
        st.write("---")
        st.write("### 📈 個股均線走勢圖")
        selected_stock = st.selectbox("選擇要檢視的庫存股票", options=list(individual_stocks_data.keys()))
        
        if selected_stock:
            df_stock = individual_stocks_data[selected_stock].copy()
            df_stock['MA10'] = df_stock['Close'].rolling(window=10).mean()
            df_stock['MA60'] = df_stock['Close'].rolling(window=60).mean()
            df_stock['MA120'] = df_stock['Close'].rolling(window=120).mean()
            
            df_plot = df_stock.tail(130)
            fig_stock = go.Figure()
            
            fig_stock.add_trace(go.Scatter(x=df_plot.index, y=df_plot['Close'], name='現價 (收盤價)', line=dict(color='#333333', width=3)))
            fig_stock.add_trace(go.Scatter(x=df_plot.index, y=df_stock['MA10'], name='10日線 (MA10)', line=dict(color='#E377C2', width=1.5)))
            fig_stock.add_trace(go.Scatter(x=df_plot.index, y=df_stock['MA60'], name='季線 (MA60)', line=dict(color='#1F77B4', width=2)))
            fig_stock.add_trace(go.Scatter(x=df_plot.index, y=df_stock['MA120'], name='半年線 (MA120)', line=dict(color='#FF7F0E', width=2.5)))
            
            stock_cost = float(df_portfolio[df_portfolio["代號"] == selected_stock]["買進單價"].iloc[0])
            fig_stock.add_hline(y=stock_cost, line_dash="dash", line_color="#9467BD", annotation_text="您的持倉成本線")

            fig_stock.update_layout(
                title=f"{selected_stock} 歷史走勢與技術均線 (半年內)",
                xaxis_title="日期",
                yaxis_title="價格 (TWD)",
                hovermode="x unified",
                legend=dict(orientation="h", y=1.1)
            )
            st.plotly_chart(fig_stock, use_container_width=True)

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
