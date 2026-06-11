"""
🏠 한국 부동산 웹 대시보드 - 모바일/데스크탑 지원
python dashboard.py
"""
import streamlit as st
import sqlite3
import pandas as pd
import os
import sys
from datetime import datetime
import urllib.request
import gzip
import shutil

sys.path.insert(0, os.path.dirname(__file__))
from data.database import DB_PATH

# --- 부트스트랩: DB 자동 다운로드 ---
DB_GZ_URL = "https://github.com/jinukahn98-lab/korealestate/releases/download/v1.0/realestate.db.gz"

def ensure_db():
    if os.path.exists(DB_PATH) and os.path.getsize(DB_PATH) > 1000:
        return True
    try:
        with st.spinner("📦 DB 다운로드 중 (첫 실행, 1~2분 소요)..."):
            urllib.request.urlretrieve(DB_GZ_URL, DB_PATH + ".gz")
            with gzip.open(DB_PATH + ".gz", 'rb') as fi, open(DB_PATH, 'wb') as fo:
                shutil.copyfileobj(fi, fo)
            os.remove(DB_PATH + ".gz")
        return True
    except Exception as e:
        st.warning(f"DB 다운로드 실패: {e}")
        return False

ensure_db()

from data.legal_dong_codes import get_cities, get_districts, get_region_name
from analysis.statistics import get_region_trade_summary, get_jeonse_rate_analysis, get_monthly_trend, get_gap_analysis
from report.html_report import generate_html_report, CHART_DIR, REPORT_DIR

st.set_page_config(
    page_title="부동산 전략 시스템",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# CSS 모바일 최적화
st.markdown("""
<style>
    .main > div { padding: 0.5rem 0.5rem; }
    .stTabs [data-baseweb="tab-list"] { gap: 4px; }
    .stTabs [data-baseweb="tab"] { padding: 8px 12px; font-size: 13px; }
    .block-container { max-width: 100%; padding: 1rem; }
    h1 { font-size: 1.4rem !important; }
    h2 { font-size: 1.1rem !important; }
    h3 { font-size: 0.95rem !important; }
    .metric-card {
        background: #f0f2f6;
        border-radius: 10px;
        padding: 12px;
        margin-bottom: 8px;
        border: 1px solid #e0e0e0;
    }
    .metric-label { color: #666; font-size: 12px; }
    .metric-value { color: #1a1a2e; font-size: 20px; font-weight: 700; }
    .metric-sub { color: #0f7b3e; font-size: 12px; }
    .highlight-box {
        background: #e8f0fe;
        border-left: 3px solid #1a73e8;
        padding: 10px 14px;
        border-radius: 6px;
        margin: 8px 0;
    }
</style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=300)
def load_region_list():
    """지역 목록 로드"""
    districts = get_districts('서울특별시')
    regions = [f'서울특별시 {d["name"]}' for d in districts]
    return sorted(regions)

@st.cache_data(ttl=300)
def get_stats(region, months=3):
    """통계 조회"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    t = cur.execute("SELECT COUNT(*) FROM apt_trade WHERE region=? AND deal_date >= date('now', ?)",
                    (region, f'-{months} months')).fetchone()[0]
    t_total = cur.execute("SELECT COUNT(*) FROM apt_trade WHERE region=?", (region,)).fetchone()[0]
    avg_p = cur.execute("SELECT ROUND(AVG(price)) FROM apt_trade WHERE region=?", (region,)).fetchone()[0] or 0
    avg_a = cur.execute("SELECT ROUND(AVG(area),1) FROM apt_trade WHERE region=?", (region,)).fetchone()[0] or 0
    r = cur.execute("SELECT COUNT(*) FROM apt_rent WHERE region=?", (region,)).fetchone()[0]
    avg_d = cur.execute("SELECT ROUND(AVG(deposit)) FROM apt_rent WHERE region=? AND deposit>0", (region,)).fetchone()[0] or 0

    conn.close()
    return {'trades': t, 'total_trades': t_total, 'avg_price': avg_p, 'avg_area': avg_a,
            'rents': r, 'avg_deposit': avg_d}

@st.cache_data(ttl=300)
def get_dong_stats(region):
    """동별 통계"""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT dong, ROUND(AVG(price)) as avg_price, COUNT(*) as cnt, ROUND(AVG(area),1) as avg_area "
        "FROM apt_trade WHERE region=? AND dong!='' GROUP BY dong ORDER BY cnt DESC", conn, params=(region,))
    conn.close()
    return df

@st.cache_data(ttl=300)
def get_top_apts(region):
    """단지별 통계"""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT apt_name, dong, ROUND(AVG(price)) as avg_price, COUNT(*) as cnt, ROUND(AVG(area),1) as avg_area "
        "FROM apt_trade WHERE region=? GROUP BY apt_name ORDER BY cnt DESC LIMIT 20", conn, params=(region,))
    conn.close()
    return df

@st.cache_data(ttl=300)
def get_trend(region):
    """월별 추이"""
    return get_monthly_trend(region, 12)

@st.cache_data(ttl=300)
def get_jeonse(region):
    """전세가율"""
    return get_jeonse_rate_analysis(region)

@st.cache_data(ttl=300)
def get_chart_paths(region):
    """차트 경로 조회"""
    chart_prefix = region.replace(' ', '_')
    today = datetime.now().strftime('%Y%m%d')
    paths = {}
    for name in ['price_trend', 'jeonse_rate', 'gap']:
        p = os.path.join(CHART_DIR, f"{name}_{chart_prefix}_{today}.png")
        if os.path.exists(p):
            paths[name] = p
    return paths

# ==================== 앱 ====================

st.title("🏠 부동산 전략 시스템")
regions = load_region_list()
col1, col2 = st.columns([3, 1])
with col1:
    region = st.selectbox("지역 선택", regions, label_visibility="collapsed")
with col2:
    if st.button("🔄 새로고침"):
        st.cache_data.clear()
        st.rerun()

tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 개요", "📍 동별", "🏢 단지별", "🔵 전세", "📈 추이"])

s = get_stats(region)

# ===== TAB 1: 개요 =====
with tab1:
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f'<div class="metric-card"><div class="metric-label">평균 매매가</div><div class="metric-value">{s["avg_price"]/10000:.1f}억</div><div class="metric-sub">평균 {s["avg_area"]:.0f}m²</div></div>', unsafe_allow_html=True)
    with col2:
        st.markdown(f'<div class="metric-card"><div class="metric-label">매매 거래</div><div class="metric-value">{s["total_trades"]:,}건</div><div class="metric-sub">최근 3개월 {s["trades"]}건</div></div>', unsafe_allow_html=True)
    with col3:
        st.markdown(f'<div class="metric-card"><div class="metric-label">전월세 거래</div><div class="metric-value">{s["rents"]:,}건</div><div class="metric-sub">전세 평균 {s["avg_deposit"]/10000:.1f}억</div></div>', unsafe_allow_html=True)
    with col4:
        if s["avg_price"] > 0:
            rate = s["avg_deposit"] / s["avg_price"] * 100
            st.markdown(f'<div class="metric-card"><div class="metric-label">전세가율</div><div class="metric-value">{rate:.1f}%</div><div class="metric-sub">{s["avg_deposit"]/10000:.1f}억 / {s["avg_price"]/10000:.1f}억</div></div>', unsafe_allow_html=True)

    # 차트
    charts = get_chart_paths(region)
    if charts:
        st.subheader("📈 차트")
        for name, path in charts.items():
            titles = {'price_trend': '매매가 추이', 'jeonse_rate': '전세가율', 'gap': '갭 분석'}
            st.caption(titles.get(name, name))
            st.image(path, use_container_width=True)

# ===== TAB 2: 동별 =====
with tab2:
    df = get_dong_stats(region)
    if not df.empty:
        st.dataframe(df.rename(columns={
            'dong': '동', 'avg_price': '평균가(만원)', 'cnt': '거래건수', 'avg_area': '평균면적(m²)'
        }), use_container_width=True, hide_index=True,
            column_config={
                "평균가(만원)": st.column_config.NumberColumn(format="%.0f"),
            })
    else:
        st.info("데이터 없음")

# ===== TAB 3: 단지별 =====
with tab3:
    df = get_top_apts(region)
    if not df.empty:
        df['평균가(억)'] = df['avg_price'] / 10000
        st.dataframe(df.rename(columns={
            'apt_name': '아파트', 'dong': '동', 'cnt': '거래건수', 'avg_area': '면적(m²)'
        }).drop(columns=['avg_price']),
            use_container_width=True, hide_index=True,
            column_config={"평균가(억)": st.column_config.NumberColumn(format="%.1f")})
    else:
        st.info("데이터 없음")

# ===== TAB 4: 전세 =====
with tab4:
    df = get_jeonse(region)
    if df is not None and not df.empty:
        st.metric("평균 전세가율", f"{df['전세가율'].mean():.1f}%")
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("전세 데이터가 충분하지 않습니다")

# ===== TAB 5: 추이 =====
with tab5:
    df = get_trend(region)
    if df is not None and not df.empty:
        df['평균매매가(억)'] = df['평균매매가'] / 10000
        st.line_chart(df.set_index('월')['평균매매가(억)'])
        st.dataframe(df[['월', '거래건수', '평균매매가(억)', '평균면적']], use_container_width=True, hide_index=True)
    else:
        st.info("데이터 없음")

st.caption(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')} · 데이터 출처: 국토교통부 실거래가 API")
