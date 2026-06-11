"""
예산 기반 지역 추천 모듈
"""

import pandas as pd
from data.database import get_conn


def find_regions_by_budget(budget_ok, city="서울특별시"):
    """
    예산(억원) 내에서 살 수 있는 구/군 목록 반환.
    평균 매매가 < budget_ok 조건. 전세가율 낮은 순(안정성) 정렬.
    """
    budget_man = budget_ok * 10000  # 만원 단위 변환

    conn = get_conn()
    query = '''
        SELECT
            t.region,
            ROUND(AVG(t.price), 0)               AS avg_price,
            ROUND(AVG(r.deposit), 0)              AS avg_deposit,
            ROUND(AVG(r.deposit) * 100.0
                  / NULLIF(AVG(t.price), 0), 1)   AS jeonse_rate,
            ROUND(AVG(t.price) - AVG(r.deposit), 0) AS gap,
            COUNT(DISTINCT t.apt_name)            AS apt_count,
            COUNT(*)                              AS trade_count
        FROM apt_trade t
        JOIN apt_rent r ON t.apt_name = r.apt_name
            AND ABS(t.area - r.area) < 5
            AND t.region = r.region
        WHERE t.region LIKE ?
        GROUP BY t.region
        HAVING AVG(t.price) < ? AND AVG(t.price) > 0
        ORDER BY jeonse_rate ASC
    '''
    df = pd.read_sql_query(query, conn, params=[f'%{city}%', budget_man])
    conn.close()
    return df


def compare_buy_vs_jeonse(region, budget_ok):
    """
    특정 지역에서 매수 vs 전세 비교.
    budget_ok: 억원
    반환 dict:
      avg_price, avg_deposit, gap (만원)
      jeonse_rate (%)
      monthly_yield (%) — 월세 전환 시 갭 대비 연수익률 추정
    """
    budget_man = budget_ok * 10000

    conn = get_conn()
    query = '''
        SELECT
            ROUND(AVG(t.price), 0)               AS avg_price,
            ROUND(AVG(r.deposit), 0)              AS avg_deposit,
            ROUND(AVG(t.price) - AVG(r.deposit), 0) AS gap,
            ROUND(AVG(r.deposit) * 100.0
                  / NULLIF(AVG(t.price), 0), 1)   AS jeonse_rate,
            ROUND(AVG(r.rent), 0)                 AS avg_monthly_rent,
            COUNT(*)                              AS trade_count
        FROM apt_trade t
        JOIN apt_rent r ON t.apt_name = r.apt_name
            AND ABS(t.area - r.area) < 5
            AND t.region = r.region
        WHERE t.region LIKE ?
    '''
    row = pd.read_sql_query(query, conn, params=[f'%{region}%']).iloc[0]
    conn.close()

    avg_price  = row['avg_price'] or 0
    avg_dep    = row['avg_deposit'] or 0
    gap        = row['gap'] or 0
    rate       = row['jeonse_rate'] or 0
    monthly    = row['avg_monthly_rent'] or 0

    # 월세 전환 수익률: (월세 × 12) / 갭
    monthly_yield = round(monthly * 12 / gap * 100, 2) if gap > 0 and monthly > 0 else 0.0

    result = {
        'region':        region,
        'budget_ok':     budget_ok,
        'avg_price':     avg_price,
        'avg_deposit':   avg_dep,
        'gap':           gap,
        'jeonse_rate':   rate,
        'monthly_yield': monthly_yield,
        'can_buy':       avg_price <= budget_man,
        'can_jeonse':    avg_dep   <= budget_man,
    }

    _print_comparison(result)
    return result


def _print_comparison(r):
    print(f"\n{'='*50}")
    print(f"  📊 매수 vs 전세 비교: {r['region']}")
    print(f"{'='*50}")
    print(f"  예산       : {r['budget_ok']:.1f}억")
    print(f"  평균 매매가: {r['avg_price']/10000:.1f}억  "
          f"{'✅ 가능' if r['can_buy'] else '❌ 초과'}")
    print(f"  평균 전세  : {r['avg_deposit']/10000:.1f}억  "
          f"{'✅ 가능' if r['can_jeonse'] else '❌ 초과'}")
    print(f"  갭         : {r['gap']/10000:.1f}억")
    print(f"  전세가율   : {r['jeonse_rate']:.1f}%")
    if r['monthly_yield']:
        print(f"  월세전환수익: {r['monthly_yield']:.2f}% (연, 갭 대비)")
    print(f"{'='*50}\n")


def print_budget_regions(budget_ok, city="서울특별시", top=10):
    """예산 기반 지역 추천 테이블 출력"""
    df = find_regions_by_budget(budget_ok, city)

    if df.empty:
        print(f"  ⚠  {city}에서 예산 {budget_ok}억 이내 지역을 찾을 수 없습니다.")
        return

    print(f"\n🎯 예산 {budget_ok}억으로 가능한 {city} 입지 TOP {min(top, len(df))}")
    print("━" * 55)
    for i, (_, row) in enumerate(df.head(top).iterrows(), 1):
        print(
            f" {i:2}. {str(row['region']):<14} | "
            f"평균 {row['avg_price']/10000:.1f}억 | "
            f"전세 {row['avg_deposit']/10000:.1f}억 | "
            f"갭 {row['gap']/10000:.1f}억 | "
            f"전세가율 {row['jeonse_rate']:.0f}%"
        )
    print("━" * 55 + "\n")


if __name__ == '__main__':
    print_budget_regions(5)
