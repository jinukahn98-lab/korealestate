"""
리포트 생성 모듈 - 주간/월간 부동산 리포트
"""

from datetime import datetime, timedelta
from data.database import get_conn, get_db_stats
from analysis.statistics import (
    get_region_trade_summary, get_monthly_trend, 
    get_jeonse_rate_analysis, get_hot_areas
)
from analysis.indicators import get_yield_analysis, get_reverse_jeonse_risk


def generate_weekly_report(region):
    """주간 부동산 리포트 생성"""
    today = datetime.now()
    week_ago = today - timedelta(days=7)

    print(f"\n{'='*60}")
    print(f"  📋 주간 부동산 리포트")
    print(f"  📍 {region} | {today.strftime('%Y년 %m월 %d일')}")
    print(f"{'='*60}")

    conn = get_conn()

    # 1. 최근 거래 동향
    cur = conn.cursor()
    cur.execute('''
        SELECT COUNT(*) as cnt, ROUND(AVG(price), 0) as avg_p
        FROM apt_trade 
        WHERE region LIKE ? AND deal_date >= ?
    ''', [f'%{region}%', week_ago.strftime('%Y-%m-%d')])
    row = cur.fetchone()
    if row and row[0] > 0:
        print(f"\n  📊 이번주 거래: {row[0]}건 | 평균가: {row[1]:,.0f}만원 ({row[1]/10000:.1f}억)")
    else:
        print(f"\n  📊 이번주 신규 거래 없음")

    # 2. 이번달 누적
    month_start = today.replace(day=1)
    cur.execute('''
        SELECT COUNT(*) as cnt, ROUND(AVG(price), 0) as avg_p
        FROM apt_trade 
        WHERE region LIKE ? AND deal_date >= ?
    ''', [f'%{region}%', month_start.strftime('%Y-%m-%d')])
    row = cur.fetchone()
    if row and row[0] > 0:
        print(f"  📅 이번달 누적: {row[0]}건 | 평균가: {row[1]:,.0f}만원")

    # 3. 최근 거래 TOP 10
    cur.execute('''
        SELECT apt_name, area, price, floor, deal_date
        FROM apt_trade 
        WHERE region LIKE ? 
        ORDER BY deal_date DESC LIMIT 10
    ''', [f'%{region}%'])
    trades = cur.fetchall()
    if trades:
        print(f"\n  🏢 최근 거래 TOP 10")
        print(f"  {'아파트':12s} {'면적':>5s} {'가격':>10s} {'층':>3s} {'일자':>10s}")
        print(f"  {'-'*45}")
        for t in trades:
            price = f"{t[2]/10000:.1f}억" if t[2] > 10000 else f"{t[2]:,.0f}만"
            print(f"  {t[0]:12s} {t[1]:>5.0f} {price:>10s} {t[3]:>3d} {t[4]:>10s}")

    # 4. 전세가율
    cur.execute('''
        SELECT r.apt_name, ROUND(AVG(r.deposit), 0), ROUND(AVG(t.price), 0)
        FROM apt_rent r
        JOIN apt_trade t ON r.apt_name = t.apt_name AND ABS(r.area - t.area) < 5
        WHERE r.region LIKE ?
        GROUP BY r.apt_name
        HAVING COUNT(*) > 2
        ORDER BY AVG(r.deposit) * 100.0 / AVG(t.price) DESC
        LIMIT 5
    ''', [f'%{region}%'])
    jeonse = cur.fetchall()
    if jeonse:
        print(f"\n  🔵 전세가율 TOP 5")
        for j in jeonse:
            rate = j[1] * 100 / j[2] if j[2] > 0 else 0
            print(f"     {j[0]}: {rate:.1f}% | 전세 {j[1]/10000:.1f}억 / 매매 {j[2]/10000:.1f}억")

    conn.close()
    print(f"\n{'='*60}")


def generate_monthly_report(region):
    """월간 부동산 리포트 생성"""
    today = datetime.now()

    print(f"\n{'='*60}")
    print(f"  📋 월간 부동산 리포트")
    print(f"  📍 {region} | {today.strftime('%Y년 %m월')}")
    print(f"{'='*60}")

    # 기본 통계
    summary = get_region_trade_summary(region)
    if summary is not None and not summary.empty:
        r = summary.iloc[0]
        print(f"\n  📊 거래량: {r['거래건수']}건")
        print(f"     평균 매매가: {r['평균매매가']/10000:.1f}억")
        print(f"     평당가: {r['평당가']*3.3/3.3:,.0f}만원/평")
        print(f"     가격범위: {r['최저가']/10000:.1f}억 ~ {r['최고가']/10000:.1f}억")

    # 월별 추이
    trend = get_monthly_trend(region, 12)
    if trend is not None and not trend.empty:
        print(f"\n  📈 최근 12개월 추이")
        for _, row in trend.tail(6).iterrows():
            print(f"     {row['월']}: {row['평균매매가']/10000:.1f}억 ({row['거래건수']}건)")

    # 전세가율
    jeonse = get_jeonse_rate_analysis(region)
    if jeonse is not None and not jeonse.empty:
        avg_rate = jeonse['전세가율'].mean()
        print(f"\n  🔵 평균 전세가율: {avg_rate:.1f}%")

    # 역전세 위험
    risk = get_reverse_jeonse_risk(region)
    if risk is not None and not risk.empty:
        print(f"\n  🚨 역전세 위험 단지: {len(risk)}개")

    # DB 통계
    db_stats = get_db_stats()
    print(f"\n  💾 DB 현황")
    print(f"     매매: {db_stats.get('apt_trade', 0):,}건")
    print(f"     전월세: {db_stats.get('apt_rent', 0):,}건")
    print(f"     직방매물: {db_stats.get('zigbang_items', 0):,}건")

    print(f"\n{'='*60}")


def generate_summary_report():
    """전체 시장 요약 리포트"""
    db_stats = get_db_stats()
    total_trades = db_stats.get('apt_trade', 0)

    print(f"\n{'='*60}")
    print(f"  📋 부동산 시장 종합 리포트")
    print(f"  🕐 {datetime.now().strftime('%Y년 %m월 %d일 %H:%M')}")
    print(f"{'='*60}")
    print(f"\n  💾 데이터 현황")
    print(f"     아파트 매매: {total_trades:,}건")
    print(f"     아파트 전월세: {db_stats.get('apt_rent', 0):,}건")
    print(f"     직방 현재매물: {db_stats.get('zigbang_items', 0):,}건")

    if total_trades > 0:
        conn = get_conn()
        # 지역별 거래량 TOP
        df = pd.read_sql_query('''
            SELECT region, COUNT(*) as cnt, ROUND(AVG(price), 0) as avg_p
            FROM apt_trade GROUP BY region ORDER BY cnt DESC LIMIT 10
        ''', conn)
        if not df.empty:
            print(f"\n  📊 지역별 거래량 TOP 10")
            for _, r in df.iterrows():
                print(f"     {r['region']}: {r['cnt']}건 (평균 {r['avg_p']/10000:.1f}억)")

        # 거래많은 단지 TOP
        df2 = pd.read_sql_query('''
            SELECT apt_name, region, COUNT(*) as cnt
            FROM apt_trade GROUP BY apt_name ORDER BY cnt DESC LIMIT 10
        ''', conn)
        if not df2.empty:
            print(f"\n  🏢 거래 활발 단지 TOP 10")
            for _, r in df2.iterrows():
                print(f"     {r['apt_name']} ({r['region']}): {r['cnt']}건")
        conn.close()

    print(f"\n{'='*60}")

import pandas as pd
