"""
매매 전략 모듈 - 적정가 분석, 시즌 패턴, 조건 검색
"""

import pandas as pd
from data.database import get_conn
from analysis.statistics import get_apt_detail, print_summary


def analyze_fair_price(apt_name, region=None):
    """특정 아파트 적정 매매가 분석"""
    df = get_apt_detail(apt_name, region)
    if df is None or df.empty:
        print(f"\n❌ '{apt_name}' 거래 내역이 없습니다.")
        return None

    print(f"\n{'='*60}")
    print(f"  🏢 {apt_name} 적정 매매가 분석")
    print(f"{'='*60}")

    # 최근 6개월
    recent = df[df['deal_date'] >= pd.Timestamp.now() - pd.DateOffset(months=6)]
    if not recent.empty:
        avg_price = recent['price'].mean()
        avg_py = recent['price'].mean() * 3.3 / recent['area'].mean()
        print(f"\n  📊 최근 6개월 평균: {avg_price:,.0f}만원 ({avg_py:,.0f}만원/평)")
        print(f"  최고가: {recent['price'].max():,.0f}만원")
        print(f"  최저가: {recent['price'].min():,.0f}만원")
        print(f"  거래건수: {len(recent)}건")
    else:
        print("\n  📭 최근 6개월 거래 내역 없음")
        avg_price = df['price'].mean()
        print(f"  전체 평균: {avg_price:,.0f}만원")

    # 면적별 분석
    print("\n  📐 면적별 가격:")
    for area_group, group in recent.groupby(pd.cut(recent['area'], bins=range(0, 200, 10))):
        if not group.empty:
            a = group['area'].mean()
            p = group['price'].mean()
            print(f"     {a:.0f}m²: {p:,.0f}만원 ({p*3.3/a:,.0f}만원/평, {len(group)}건)")

    # 층별 분석
    print("\n  🏗️ 층별 평균가:")
    for floor_group in ['저층', '중층', '고층']:
        if floor_group == '저층':
            fdf = recent[recent['floor'] <= 5]
        elif floor_group == '중층':
            fdf = recent[(recent['floor'] > 5) & (recent['floor'] <= 15)]
        else:
            fdf = recent[recent['floor'] > 15]
        if not fdf.empty:
            print(f"     {floor_group}({fdf['floor'].min()}~{fdf['floor'].max()}층): {fdf['price'].mean():,.0f}만원 ({len(fdf)}건)")

    return recent


def search_by_condition(region=None, min_price=None, max_price=None, min_area=None, max_area=None):
    """조건별 매물 검색"""
    conn = get_conn()
    query = "SELECT region, apt_name, area, floor, price, deal_date, dong FROM apt_trade WHERE 1=1"
    params = []

    if region:
        query += ' AND region LIKE ?'
        params.append(f'%{region}%')
    if min_price:
        query += ' AND price >= ?'
        params.append(min_price * 10000)
    if max_price:
        query += ' AND price <= ?'
        params.append(max_price * 10000)
    if min_area:
        query += ' AND area >= ?'
        params.append(min_area)
    if max_area:
        query += ' AND area <= ?'
        params.append(max_area)

    query += ' ORDER BY deal_date DESC LIMIT 50'
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()

    if not df.empty:
        df['거래가_억'] = df['price'] / 10000
        print_summary(df, f"🔍 조건 검색 결과 ({len(df)}건)")
    return df


def get_buy_strategy(region, budget_ok=0, area_pyeong=None):
    """
    매매 전략 추천

    Parameters:
        region (str): 지역명
        budget_ok (int): 예산 (억원)
        area_pyeong (tuple): 희망 면적 범위 (평) - 옵션
    """
    print(f"\n{'='*60}")
    print(f"  🎯 매매 전략 분석: {region}")
    if budget_ok > 0:
        print(f"     예산: {budget_ok}억원")
    print(f"{'='*60}")

    conn = get_conn()

    # 1. 예산 내 가능한 단지
    if budget_ok > 0:
        budget_m = budget_ok * 10000
        query = '''
            SELECT region, apt_name, dong, 
                   ROUND(AVG(area), 1) as avg_area,
                   ROUND(AVG(price), 0) as avg_price,
                   ROUND(AVG(price) / NULLIF(AVG(area), 0) * 3.3, 0) as avg_py,
                   COUNT(*) as trade_count,
                   MIN(price) as min_price,
                   MAX(price) as max_price
            FROM apt_trade
            WHERE region LIKE ? AND price <= ?
        '''
        params = [f'%{region}%', budget_m]

        if area_pyeong:
            min_area = area_pyeong[0] * 3.3
            max_area = area_pyeong[1] * 3.3
            query += ' AND area BETWEEN ? AND ?'
            params.extend([min_area, max_area])

        query += ' GROUP BY apt_name ORDER BY avg_price DESC'

        df = pd.read_sql_query(query, conn, params=params)
        conn.close()

        if df.empty:
            print(f"\n  ❌ '{region}'에서 예산 {budget_ok}억원 이하 매물이 없습니다.")
            return None

        print(f"\n  ✅ 예산 내 가능한 단지 ({len(df)}개):")
        for _, row in df.iterrows():
            pct = row['avg_price'] / budget_m * 100
            bar = '█' * int(pct / 5) + '░' * (20 - int(pct / 5))
            print(f"     {row['apt_name']:12s} | {row['avg_price']:>8,.0f}만원({row['avg_price']/10000:.1f}억) | {bar}")
            print(f"             {row['dong']:8s} | {row['avg_area']:.0f}m² | {row['avg_py']:,.0f}만원/평 | {row['trade_count']}건")

        # TOP 3 추천
        top3 = df.nsmallest(3, 'avg_price') if not df.empty else df.head(3)
        print(f"\n  ⭐ TOP 3 추천 (가성비):")
        for i, (_, row) in enumerate(top3.iterrows(), 1):
            print(f"     {i}. {row['apt_name']} - {row['avg_price']/10000:.1f}억 / {row['avg_area']:.0f}m²")

    else:
        conn.close()

    return df if budget_ok > 0 else None


def compare_regions(regions):
    """지역간 매매가 비교"""
    if not regions:
        return

    print(f"\n{'='*60}")
    print(f"  📊 지역간 매매가 비교")
    print(f"{'='*60}")

    conn = get_conn()
    for region in regions:
        query = '''
            SELECT 
                ROUND(AVG(price), 0) as avg_price,
                ROUND(AVG(price) / NULLIF(AVG(area), 0) * 3.3, 0) as avg_py,
                COUNT(*) as cnt,
                ROUND(MIN(price), 0) as min_p,
                ROUND(MAX(price), 0) as max_p
            FROM apt_trade WHERE region LIKE ?
        '''
        df = pd.read_sql_query(query, conn, params=[f'%{region}%'])
        conn.close()

        if not df.empty and df['cnt'].iloc[0] > 0:
            r = df.iloc[0]
            print(f"\n  📍 {region}")
            print(f"     평균: {r['avg_price']/10000:.1f}억 ({r['avg_py']:,.0f}만원/평)")
            print(f"     범위: {r['min_p']/10000:.1f}억 ~ {r['max_p']/10000:.1f}억")
            print(f"     거래: {r['cnt']}건")
        else:
            print(f"\n  📍 {region}: 데이터 없음")
