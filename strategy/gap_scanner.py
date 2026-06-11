"""
갭 투자 스크리너 - 전세가율 기반 갭 투자 기회 탐색
"""

import pandas as pd
from data.database import get_conn

_GAP_SQL = '''
SELECT
    t.region, t.apt_name, t.dong,
    ROUND(AVG(t.area), 1) as avg_area,
    ROUND(AVG(t.price), 0) as avg_price,
    ROUND(AVG(r.deposit), 0) as avg_deposit,
    ROUND(AVG(t.price) - AVG(r.deposit), 0) as gap,
    ROUND(AVG(r.deposit) * 100.0 / NULLIF(AVG(t.price), 0), 1) as jeonse_rate,
    COUNT(*) as trade_count
FROM apt_trade t
JOIN apt_rent r ON t.apt_name = r.apt_name
    AND ABS(t.area - r.area) < 5
    AND t.region = r.region
WHERE t.deal_date >= date("now", "-6 months") AND r.deal_date >= date("now", "-6 months")
GROUP BY t.region, t.apt_name
HAVING COUNT(*) > 2 AND AVG(t.price) > 0
ORDER BY jeonse_rate DESC
'''


def _load_gap_data():
    conn = get_conn()
    df = pd.read_sql_query(_GAP_SQL, conn)
    conn.close()
    return df


def scan_gap_opportunities(min_rate=70, max_rate=80, max_gap=50000, min_trades=5):
    """
    전세가율 70~80%, 갭 5억 이하, 거래 5건 이상인 갭 투자 적정 단지 반환.
    gap, avg_price, avg_deposit 단위: 만원
    """
    df = _load_gap_data()
    if df.empty:
        return df

    mask = (
        (df['jeonse_rate'] >= min_rate) &
        (df['jeonse_rate'] <= max_rate) &
        (df['gap'] <= max_gap) &
        (df['trade_count'] >= min_trades)
    )
    return df[mask].reset_index(drop=True)


def get_gap_investment_summary(region=None):
    """지역별 갭 투자 요약: 평균 갭, 평균 전세가율, 적정 단지 수"""
    df = _load_gap_data()
    if df.empty:
        return pd.DataFrame()

    if region:
        df = df[df['region'].str.contains(region, na=False)]

    summary = (
        df.groupby('region')
        .agg(
            avg_gap=('gap', 'mean'),
            avg_jeonse_rate=('jeonse_rate', 'mean'),
            total_apts=('apt_name', 'nunique'),
            suitable_apts=('apt_name', lambda s: (
                df.loc[s.index, 'jeonse_rate'].between(70, 80) &
                (df.loc[s.index, 'gap'] <= 50000)
            ).sum()),
        )
        .round({'avg_gap': 0, 'avg_jeonse_rate': 1})
        .reset_index()
        .sort_values('avg_jeonse_rate', ascending=False)
    )
    return summary


def print_gap_table(min_rate=70, max_rate=80, max_gap=50000, min_trades=5):
    """갭 투자 기회 단지 테이블 출력 (전세가율 높은 순)"""
    df = scan_gap_opportunities(min_rate, max_rate, max_gap, min_trades)

    if df.empty:
        print("  ⚠  조건에 맞는 단지가 없습니다.")
        return

    col_w = [10, 14, 8, 8, 8, 6, 7]
    header = (
        f"{'지역':<{col_w[0]}} {'단지명':<{col_w[1]}} {'동':<{col_w[2]}}"
        f" {'전세가율':>{col_w[3]}} {'갭(억)':>{col_w[4]}}"
        f" {'매매(억)':>{col_w[5]+2}} {'전세(억)':>{col_w[6]+2}} {'거래':>4}"
    )
    sep = "━" * len(header)

    print(f"\n🔍 갭 투자 적정 단지 — 전세가율 {min_rate}~{max_rate}%, 갭 {max_gap//10000}억 이하")
    print(sep)
    print(header)
    print(sep)

    for _, row in df.iterrows():
        gap_ok = f"{row['gap']/10000:.1f}억"
        jeonse_pct = f"{row['jeonse_rate']:.1f}%"
        avg_price = f"{row['avg_price']/10000:.1f}억"
        avg_dep = f"{row['avg_deposit']/10000:.1f}억"
        print(
            f"{str(row['region']):<{col_w[0]}} "
            f"{str(row['apt_name']):<{col_w[1]}} "
            f"{str(row['dong'] or ''):<{col_w[2]}} "
            f"{jeonse_pct:>{col_w[3]}} "
            f"{gap_ok:>{col_w[4]}} "
            f"{avg_price:>{col_w[5]+2}} "
            f"{avg_dep:>{col_w[6]+2}} "
            f"{row['trade_count']:>4}"
        )
    print(sep)
    print(f"  총 {len(df)}개 단지\n")


def score_gap_risk(df):
    """갭 투자 리스크 스코어링 (낮을수록 안전)

    점수 = 전세가율(40%) + 거래량 안정성(20%) + 가격 변동성(40%)
    """
    if df.empty:
        return df

    max_rate = df["jeonse_rate"].max()
    min_rate = df["jeonse_rate"].min()
    rate_range = max(max_rate - min_rate, 1)

    max_gap = df["gap"].max()
    min_gap = df["gap"].min()
    gap_range = max(max_gap - min_gap, 1)

    max_trades = df["trade_count"].max()
    min_trades = df["trade_count"].min()
    trade_range = max(max_trades - min_trades, 1)

    df["risk_score"] = (
        ((df["jeonse_rate"] - min_rate) / rate_range * 100) * 0.4 +
        ((df["gap"] - min_gap) / gap_range * 100) * 0.2 +
        ((1 - (df["trade_count"] - min_trades) / trade_range) * 100) * 0.4
    ).round(1)

    def risk_level(score):
        if score <= 25:
            return "safe"
        elif score <= 50:
            return "moderate"
        elif score <= 75:
            return "caution"
        else:
            return "danger"

    df["risk_level"] = df["risk_score"].apply(risk_level)
    return df.sort_values("risk_score")


if __name__ == '__main__':
    print_gap_table()
