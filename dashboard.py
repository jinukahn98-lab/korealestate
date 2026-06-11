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
import plotly.graph_objects as go
from plotly.subplots import make_subplots

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
try:
    from analysis.statistics import (
        get_region_trade_summary, get_jeonse_rate_analysis, get_monthly_trend, get_gap_analysis,
        get_pyoung_price, get_seasonal_pattern, get_trade_gap_alert, get_jeonse_momentum,
    )
except ImportError as e:
    st.error(f"statistics import 실패: {e}")
    st.stop()

try:
    from report.html_report import generate_html_report, CHART_DIR, REPORT_DIR
    from strategy.gap_scanner import scan_gap_opportunities
    from strategy.region_planner import find_regions_by_budget
except ImportError as e:
    st.error(f"기타 import 실패: {e}")
    st.stop()

st.set_page_config(
    page_title="부동산 전략 시스템",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded"
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
    .badge-up { color: #d32f2f; font-weight: 700; }
    .badge-down { color: #1976d2; font-weight: 700; }
    .badge-hold { color: #666; font-weight: 700; }
</style>
""", unsafe_allow_html=True)


# ==================== 차트 함수 ====================

def make_price_trend_chart(df):
    """Interactive price+volume dual-axis chart"""
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(
        x=df["월"], y=df["평균매매가(억)"],
        name="평균매매가", mode="lines+markers",
        line=dict(color="#FF4B4B", width=2)
    ), secondary_y=False)
    fig.add_trace(go.Bar(
        x=df["월"], y=df["거래건수"],
        name="거래건수", opacity=0.3,
        marker_color="#4B8BFF"
    ), secondary_y=True)
    fig.update_layout(
        title="월별 가격 추이 & 거래량",
        hovermode="x unified",
        template="plotly_white",
        height=450
    )
    fig.update_xaxes(title_text="월")
    fig.update_yaxes(title_text="가격 (억원)", secondary_y=False)
    fig.update_yaxes(title_text="거래건수", secondary_y=True)
    return fig


def make_jeonse_rate_chart(df):
    """동별 전세가율 bar chart with reference lines"""
    x_col = "apt_name" if "apt_name" in df.columns else df.columns[0]
    fig = go.Figure()
    colors = ["#FF6B6B" if v > 80 else "#4ECDC4" if v > 60 else "#95E1D3"
              for v in df["전세가율"]]
    fig.add_trace(go.Bar(
        x=df[x_col], y=df["전세가율"],
        marker_color=colors,
        text=df["전세가율"].round(1).astype(str) + "%",
        textposition="outside"
    ))
    fig.add_trace(go.Scatter(
        x=df[x_col], y=[70] * len(df),
        name="안전선 70%", line=dict(dash="dash", color="orange")
    ))
    fig.add_trace(go.Scatter(
        x=df[x_col], y=[80] * len(df),
        name="위험선 80%", line=dict(dash="dash", color="red")
    ))
    fig.update_layout(
        title="단지별 전세가율",
        hovermode="x", template="plotly_white", height=400
    )
    return fig


def make_gap_scatter(df):
    """갭 투자 기회 scatter chart"""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["전세가율"], y=df["갭(억)"],
        mode="markers+text",
        text=df["apt_name"],
        textposition="top center",
        marker=dict(
            size=df["trade_count"] * 2,
            color=df["전세가율"],
            colorscale="RdYlGn_r",
            showscale=True,
            colorbar_title="전세가율 %"
        ),
        hovertemplate=(
            "<b>%{text}</b><br>"
            "전세가율: %{x:.1f}%<br>"
            "갭: %{y:.1f}억<extra></extra>"
        )
    ))
    fig.update_layout(
        title="갭 투자 기회 분석",
        xaxis_title="전세가율 (%)",
        yaxis_title="갭 (억원)",
        template="plotly_white", height=500
    )
    return fig


def make_seasonal_chart(df):
    """월별 계절성 bar chart"""
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["월"].astype(str) + "월",
        y=df["거래건수"],
        marker_color="#4B8BFF",
        text=df["거래건수"],
        textposition="outside"
    ))
    fig.update_layout(
        title="월별 거래 계절성",
        xaxis_title="월",
        yaxis_title="거래건수",
        template="plotly_white",
        height=350
    )
    return fig


# ==================== 데이터 함수 ====================

@st.cache_data(ttl=3600)
def load_sido_list():
    """DB에서 시/도 목록 로드"""
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query(
            "SELECT DISTINCT substr(region, 1, 2) as sido FROM apt_trade ORDER BY sido", conn)
        conn.close()
        sidos = [s for s in df["sido"].unique() if s and len(s.strip()) > 0]
        result = ["서울"] + sorted([s for s in sidos if s != "서울"])
        return result if result else ["서울"]
    except Exception:
        return ["서울"]


@st.cache_data(ttl=3600)
def load_region_list_by_sido(sido=None):
    """시/도 선택 후 시/군/구 목록 로드"""
    try:
        conn = sqlite3.connect(DB_PATH)
        prefix = sido if sido else "서울"
        df = pd.read_sql_query(
            "SELECT DISTINCT region FROM apt_trade WHERE region LIKE ? ORDER BY region",
            conn, params=[f"{prefix}%"])
        conn.close()
        regions = df["region"].tolist()
        return regions if regions else _fallback_seoul_regions()
    except Exception:
        return _fallback_seoul_regions()


def _fallback_seoul_regions():
    districts = get_districts('서울특별시')
    return sorted([f'서울특별시 {d["name"]}' for d in districts])


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
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT dong, ROUND(AVG(price)) as avg_price, COUNT(*) as cnt, ROUND(AVG(area),1) as avg_area "
        "FROM apt_trade WHERE region=? AND dong!='' GROUP BY dong ORDER BY cnt DESC", conn, params=(region,))
    conn.close()
    return df


@st.cache_data(ttl=300)
def get_top_apts(region):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT apt_name, dong, ROUND(AVG(price)) as avg_price, COUNT(*) as cnt, ROUND(AVG(area),1) as avg_area "
        "FROM apt_trade WHERE region=? GROUP BY apt_name ORDER BY cnt DESC LIMIT 20", conn, params=(region,))
    conn.close()
    return df


@st.cache_data(ttl=300)
def get_apt_price_history(region, apt_name):
    """아파트별 가격 이력"""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT deal_date, price, area, floor FROM apt_trade "
        "WHERE region=? AND apt_name=? ORDER BY deal_date",
        conn, params=(region, apt_name))
    conn.close()
    return df


@st.cache_data(ttl=300)
def get_trend(region):
    return get_monthly_trend(region, 12)


@st.cache_data(ttl=300)
def get_jeonse(region):
    return get_jeonse_rate_analysis(region)


@st.cache_data(ttl=300)
def get_chart_paths(region):
    chart_prefix = region.replace(' ', '_')
    today = datetime.now().strftime('%Y%m%d')
    paths = {}
    for name in ['price_trend', 'jeonse_rate', 'gap']:
        p = os.path.join(CHART_DIR, f"{name}_{chart_prefix}_{today}.png")
        if os.path.exists(p):
            paths[name] = p
    return paths


# ==================== 앱 ====================

col_title, col_refresh = st.columns([5, 1])
with col_title:
    st.title("🏠 부동산 전략 시스템")
with col_refresh:
    if st.button("🔄 새로고침"):
        st.cache_data.clear()
        st.rerun()

# 사이드바: 지역 선택
st.sidebar.header("📍 지역 설정")
sido = st.sidebar.selectbox("시/도", load_sido_list())
regions = load_region_list_by_sido(sido)
region = st.sidebar.selectbox("시/군/구", regions)

tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs([
    "📊 개요", "📍 동별", "🏢 단지별", "🔵 전세", "📈 추이",
    "💰 갭 투자", "💡 예산", "📊 고급 분석", "🏆 추천"
])

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
            column_config={"평균가(만원)": st.column_config.NumberColumn(format="%.0f")})
    else:
        st.info("데이터 없음")

# ===== TAB 3: 단지별 =====
with tab3:
    df = get_top_apts(region)
    if not df.empty:
        df['평균가(억)'] = df['avg_price'] / 10000

        search_term = st.text_input("🔍 아파트명 검색", placeholder="예: 래미안, 자이, 푸르지오...")
        if search_term:
            df = df[df['apt_name'].str.contains(search_term, na=False)]

        st.dataframe(df.rename(columns={
            'apt_name': '아파트', 'dong': '동', 'cnt': '거래건수', 'avg_area': '면적(m²)'
        }).drop(columns=['avg_price']),
            use_container_width=True, hide_index=True,
            column_config={"평균가(억)": st.column_config.NumberColumn(format="%.1f")})

        st.subheader("단지별 상세 보기")
        for _, row in df.head(5).iterrows():
            apt = row['apt_name']
            with st.expander(f"📋 {apt} 상세"):
                hist = get_apt_price_history(region, apt)
                if not hist.empty:
                    hist['가격(억)'] = hist['price'] / 10000
                    col_a, col_b = st.columns(2)
                    with col_a:
                        fig_hist = go.Figure()
                        fig_hist.add_trace(go.Scatter(
                            x=hist["deal_date"], y=hist["가격(억)"],
                            mode="markers",
                            marker=dict(color="#FF4B4B", size=6),
                            hovertemplate="%{x}<br>%{y:.2f}억<extra></extra>"
                        ))
                        fig_hist.update_layout(
                            title="실거래가 이력",
                            xaxis_title="거래일",
                            yaxis_title="가격 (억원)",
                            template="plotly_white", height=280
                        )
                        st.plotly_chart(fig_hist, use_container_width=True)
                    with col_b:
                        fig_floor = go.Figure()
                        fig_floor.add_trace(go.Histogram(
                            x=hist["floor"], nbinsx=15,
                            marker_color="#4B8BFF", opacity=0.7,
                            name="층수 분포"
                        ))
                        fig_floor.update_layout(
                            title="층수 분포",
                            xaxis_title="층",
                            yaxis_title="거래건수",
                            template="plotly_white", height=280
                        )
                        st.plotly_chart(fig_floor, use_container_width=True)
                else:
                    st.info("거래 이력 없음")
    else:
        st.info("데이터 없음")

# ===== TAB 4: 전세 =====
with tab4:
    df = get_jeonse(region)
    if df is not None and not df.empty:
        st.metric("평균 전세가율", f"{df['전세가율'].mean():.1f}%")
        st.plotly_chart(make_jeonse_rate_chart(df), use_container_width=True)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("전세 데이터가 충분하지 않습니다")

# ===== TAB 5: 추이 =====
with tab5:
    df = get_trend(region)
    if df is not None and not df.empty:
        df['평균매매가(억)'] = df['평균매매가'] / 10000
        st.plotly_chart(make_price_trend_chart(df), use_container_width=True)
        st.dataframe(df[['월', '거래건수', '평균매매가(억)', '평균면적']], use_container_width=True, hide_index=True)
    else:
        st.info("데이터 없음")

# ===== TAB 6: 갭 투자 =====
with tab6:
    st.subheader("💰 갭 투자 스크리너")
    col1, col2 = st.columns(2)
    with col1:
        min_rate = st.slider("최소 전세가율 (%)", 50, 95, 70)
    with col2:
        max_gap = st.slider("최대 갭 (억원)", 1, 10, 5)
    df = scan_gap_opportunities(min_rate=min_rate, max_rate=100, max_gap=max_gap*10000, min_trades=3)
    if df is not None and not df.empty:
        df['전세가율'] = df['jeonse_rate']
        df['갭(억)'] = (df['gap'] / 10000).round(1)
        df['매매가(억)'] = (df['avg_price'] / 10000).round(1)
        df['전세가(억)'] = (df['avg_deposit'] / 10000).round(1)
        st.plotly_chart(make_gap_scatter(df), use_container_width=True)
        st.dataframe(df[['region', 'apt_name', 'dong', '전세가율', '갭(억)', '매매가(억)', '전세가(억)', 'trade_count']].rename(columns={
            'region': '지역', 'apt_name': '아파트', 'dong': '동', 'trade_count': '거래건수'
        }), use_container_width=True, hide_index=True,
            column_config={
                "전세가율": st.column_config.NumberColumn(format="%.1f%%"),
                "갭(억)": st.column_config.NumberColumn(format="%.1f억"),
                "매매가(억)": st.column_config.NumberColumn(format="%.1f억"),
                "전세가(억)": st.column_config.NumberColumn(format="%.1f억"),
            })
    else:
        st.info("조건에 맞는 단지가 없습니다")

# ===== TAB 7: 예산 로드맵 =====
with tab7:
    st.subheader("💡 예산 기반 지역 추천")
    col1, col2 = st.columns(2)
    with col1:
        budget = st.number_input("예산 (억원)", 1, 50, 5)
    with col2:
        city = st.selectbox("도시", ["서울특별시", "경기도"])
    df = find_regions_by_budget(budget_ok=budget, city=city)
    if df is not None and not df.empty:
        df['매매가(억)'] = (df['avg_price'] / 10000).round(1)
        df['전세가(억)'] = (df['avg_deposit'] / 10000).round(1)
        df['갭(억)'] = (df['gap'] / 10000).round(1)
        st.dataframe(df[['region', '매매가(억)', '전세가(억)', 'jeonse_rate', '갭(억)', 'apt_count', 'trade_count']].rename(columns={
            'region': '지역', 'jeonse_rate': '전세가율(%)', 'apt_count': '단지수', 'trade_count': '거래건수'
        }), use_container_width=True, hide_index=True,
            column_config={
                "매매가(억)": st.column_config.NumberColumn(format="%.1f억"),
                "전세가(억)": st.column_config.NumberColumn(format="%.1f억"),
                "전세가율(%)": st.column_config.NumberColumn(format="%.1f%%"),
                "갭(억)": st.column_config.NumberColumn(format="%.1f억"),
            })
    else:
        st.info(f"예산 {budget}억으로 {city}에서 살 수 있는 지역이 없습니다")

# ===== TAB 8: 고급 분석 =====
with tab8:
    st.subheader("📊 고급 분석")
    st.caption(f"지역: {region}")
    st.divider()

    # 역전세 경보
    try:
        from strategy.jeonse import alert_reverse_jeonse
        alert_msg = alert_reverse_jeonse(threshold=85)
        if alert_msg:
            st.warning(alert_msg.split("\n")[0])
            lines = [l.strip() for l in alert_msg.split("\n")[2:7] if l.strip()]
            for l in lines:
                st.markdown(f"- {l}")
        else:
            st.success("✅ 역전세 위험 없음 (85%↑ 기준)")
    except Exception:
        pass

    sub_a, sub_b, sub_c, sub_d = st.tabs(["🏷️ 평당가", "📅 계절성", "⚠️ 거래공백", "📈 모멘텀"])

    with sub_a:
        df_pyoung = get_pyoung_price(region)
        if df_pyoung is not None and not df_pyoung.empty:
            st.dataframe(df_pyoung.head(20).rename(columns={
                'apt_name': '아파트', 'dong': '동', 'pyoung_price': '평당가(만원)',
                'avg_price': '평균매매가(만원)', 'avg_area': '평균면적(m²)', 'cnt': '거래건수'
            }), use_container_width=True, hide_index=True)
        else:
            st.info("평당가 데이터 없음")

    with sub_b:
        df_season = get_seasonal_pattern(region)
        if df_season is not None and not df_season.empty:
            df_season['월'] = df_season['월'].astype(int)
            st.plotly_chart(make_seasonal_chart(df_season), use_container_width=True)
            peak = df_season.loc[df_season['거래건수'].idxmax()]
            low = df_season.loc[df_season['거래건수'].idxmin()]
            st.info(f"📈 가장 거래 많은 달: **{int(peak['월'])}월** ({peak['거래건수']}건, 평균 {peak['평균매매가']/10000:.1f}억)")
            st.info(f"📉 가장 거래 적은 달: **{int(low['월'])}월** ({low['거래건수']}건, 평균 {low['평균매매가']/10000:.1f}억)")
        else:
            st.info("계절성 데이터 없음")

    with sub_c:
        df_gap = get_trade_gap_alert(months=6)
        if df_gap is not None and not df_gap.empty:
            st.dataframe(df_gap.rename(columns={
                'region': '지역', 'apt_name': '아파트', 'last_trade_date': '마지막거래일',
                'days_since': '경과일', 'last_price': '마지막가격(만원)'
            }), use_container_width=True, hide_index=True)
        else:
            st.info("거래 공백 단지 없음")

    with sub_d:
        df_mom = get_jeonse_momentum(region)
        if df_mom is not None and not df_mom.empty:
            rows = []
            for _, r in df_mom.iterrows():
                arrow = "🔼" if r['전세가율변화'] > 2 else ("🔽" if r['전세가율변화'] < -2 else "➡️")
                rows.append({"아파트": r['apt_name'], "현재전세가율": f"{r['최근전세가율']:.1f}%",
                             "3개월전": f"{r['이전전세가율']:.1f}%", "변화": f"{arrow} {r['전세가율변화']:+.1f}%"})
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("모멘텀 데이터 없음")

    # 타이밍 신호 섹션
    with st.expander("매수/매도 타이밍 신호", expanded=True):
        from strategy.timing import get_timing_signal
        sig = get_timing_signal(region)
        signal_emoji = {"BUY": "🟢", "HOLD": "🟡", "SELL": "🔴"}
        col1, col2, col3 = st.columns(3)
        col1.metric("신호", f"{signal_emoji.get(sig['signal'], '⚪')} {sig['signal']}")
        col2.metric("점수", f"{sig['score']}/100")
        col3.metric("최근거래일", sig.get("last_trade", "-"))
        if sig["reasons"]:
            for r in sig["reasons"]:
                st.write(f"- {r}")

    with st.expander("가격 예측 (3개월)", expanded=False):
        from analysis.prediction import predict_region_price
        pred = predict_region_price(region)
        if "error" in pred:
            st.info(pred["error"])
        else:
            cols = st.columns(3)
            cols[0].metric("현재가", f"{pred['latest_price']/10000:.1f}억")
            cols[1].metric("3개월후 예측", f"{pred['predicted_price']/10000:.1f}억")
            trend_emoji = {"up": "📈", "down": "📉", "flat": "➡️"}
            cols[2].metric("전망", f"{trend_emoji.get(pred['trend'], '➡️')} {pred['predicted_3m_change_pct']:+.1f}%")
            st.caption(f"예측 정확도: {pred['accuracy_note']} | {pred['data_months']}개월 데이터 기반")

# ===== TAB 9: 추천 엔진 =====
with tab9:
    st.subheader("🏆 매매 추천 엔진")
    st.caption("8개 요소 종합 점수화 | ref: DB 최신 데이터 기준")

    col_r1, col_r2, col_r3 = st.columns(3)
    with col_r1:
        st.metric("전세가율", "20%", "낮을수록 고득점")
    with col_r2:
        st.metric("가격추세", "20%", "안정적 상승 선호")
    with col_r3:
        st.metric("평당가매력", "10%", "시세 대비 저평가")

    tab_r1, tab_r2, tab_r3, tab_r4 = st.tabs(["🏆 종합 순위", "🟢 매수 추천", "🔴 매도 경보", "📋 지역 분석"])

    with tab_r1:
        st.subheader("전체 지역 매매 추천 순위")
        with st.spinner("순위 분석 중..."):
            try:
                from strategy.recommender import RecommendationEngine
                engine = RecommendationEngine()
                df_rank = engine.rank_regions(limit=30)
                engine.close()
                if not df_rank.empty:
                    def color_grade(val):
                        if "강력매수" in str(val):
                            return "background-color: #ff4b4b20"
                        elif "매수" in str(val):
                            return "background-color: #00c85320"
                        elif "관망" in str(val):
                            return "background-color: #ffd60020"
                        elif "매도" in str(val):
                            return "background-color: #ff6d0020"
                        return ""
                    st.dataframe(df_rank.style.applymap(color_grade, subset=["등급"]),
                                use_container_width=True, hide_index=True)
                else:
                    st.info("순위 데이터 없음")
            except Exception as e:
                st.error(f"순위 분석 오류: {e}")

    with tab_r2:
        st.subheader("🟢 지금 매수하기 좋은 지역")
        with st.spinner("매수 추천 분석 중..."):
            try:
                from strategy.recommender import RecommendationEngine
                engine = RecommendationEngine()
                df_best = engine.find_best_deals(top_n=10)
                engine.close()
                if not df_best.empty:
                    st.success(f"✅ 매수 추천 지역 {len(df_best)}곳 발견!")
                    st.dataframe(df_best, use_container_width=True, hide_index=True)
                else:
                    st.info("현재 매수 추천 지역이 없습니다 (종합점수 60 미만)")
            except Exception as e:
                st.error(f"매수 추천 오류: {e}")

    with tab_r3:
        st.subheader("🔴 매도 고려 지역")
        with st.spinner("매도 경보 분석 중..."):
            try:
                from strategy.recommender import RecommendationEngine
                engine = RecommendationEngine()
                df_sell = engine.find_sell_alerts(top_n=10)
                engine.close()
                if not df_sell.empty:
                    st.warning(f"⚠️ 매도 고려 지역 {len(df_sell)}곳")
                    st.dataframe(df_sell, use_container_width=True, hide_index=True)
                else:
                    st.info("매도 경보 지역 없음")
            except Exception as e:
                st.error(f"매도 경보 오류: {e}")

    with tab_r4:
        col_a, col_b = st.columns([1, 2])
        with col_a:
            target_region = st.selectbox("분석할 지역", regions, key="rec_region")
        with col_b:
            show_detail = st.button("🔍 분석", type="primary")

        if show_detail or target_region:
            with st.spinner("지역 분석 중..."):
                try:
                    from strategy.recommender import RecommendationEngine
                    engine = RecommendationEngine()
                    result = engine.score_region(target_region)
                    engine.close()

                    st.subheader(f"📍 {result['region']}")
                    rcol1, rcol2, rcol3 = st.columns(3)
                    rcol1.metric("종합점수", f"{result['total_score']}/100")
                    rcol2.metric("등급", result['grade'])
                    rcol3.metric("기준일", result['time'][:10])

                    for name, data in result['factors'].items():
                        bar = data['score'] / 10
                        pct = data['score']
                        if pct >= 70:
                            color = "#00c853"
                        elif pct >= 50:
                            color = "#ffd600"
                        else:
                            color = "#ff4b4b"
                        st.markdown(
                            f"**{name}**: {data['score']}/100 ({data['value']})"
                        )
                        st.progress(data['score'] / 100)

                except Exception as e:
                    st.error(f"분석 오류: {e}")

st.caption(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')} · 데이터 출처: 국토교통부 실거래가 API")
