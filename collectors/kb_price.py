"""
KB부동산 데이터허브 수집 모듈 (PublicDataReader)

PublicDataReader의 Kbland 클래스를 사용하여 KB부동산 데이터 수집.
API 키 불필요 — 내부 웹 API를 래핑한 라이브러리.

지원 데이터:
  - 평균매가 (시도/강남11/강북14)
  - 전세가율
  - ㎡당 평균매매가
  - 중위매매가
  - 매수우위지수
  - KB선도아파트50 지수
"""

from datetime import datetime


# ─── KB 데이터 조회 ──────────────────────────────────


def get_avg_price(region_code='1100000000', item_type='01', trade_type='01'):
    """
    KB 평균매매가/전세가 조회
    
    Args:
        region_code: 지역코드 (1100000000=서울, 1B0000=강남11, 1A0000=강북14, 4100000000=경기)
        item_type: 01=아파트, 08=연립, 09=단독, 98=주택종합
        trade_type: 01=매매, 02=전세
    
    Returns:
        DataFrame or None
    """
    try:
        from PublicDataReader import Kbland
        kb = Kbland()
        df = kb.get_average_price(
            매물종별구분=item_type,
            매매전세코드=trade_type,
        )
        if df is not None and not df.empty:
            # 해당 지역코드 필터
            filtered = df[df['지역코드'] == region_code]
            if not filtered.empty:
                return filtered
            return df  # 전체 반환
        return None
    except Exception as e:
        print(f'  ⚠️ KB 평균가 조회 실패: {e}')
        return None


def get_jeonse_rate(item_type='01'):
    """
    KB 전세가율 조회
    
    Returns:
        DataFrame (지역코드, 지역명, 날짜, 전세가격비율)
    """
    try:
        from PublicDataReader import Kbland
        kb = Kbland()
        df = kb.get_jeonse_price_ratio(매물종별구분=item_type)
        return df
    except Exception as e:
        print(f'  ⚠️ KB 전세가율 조회 실패: {e}')
        return None


def get_market_trend():
    """
    KB 매수우위지수 조회 (시장 심리)
    
    Returns:
        DataFrame (지역코드, 지역명, 날짜, 매수우위지수, 매수자많음% 등)
    """
    try:
        from PublicDataReader import Kbland
        kb = Kbland()
        df = kb.get_market_trend(메뉴코드='01', 월간주간구분코드='01')
        return df
    except Exception as e:
        print(f'  ⚠️ KB 매수우위지수 조회 실패: {e}')
        return None


def get_price_index(item_type='01', trade_type='01'):
    """
    KB 가격지수 (2019=100 기준)
    
    Args:
        item_type: 01=아파트
        trade_type: 01=매매, 02=전세
    
    Returns:
        DataFrame
    """
    try:
        from PublicDataReader import Kbland
        kb = Kbland()
        df = kb.get_price_index(
            월간주간구분코드='01',
            매물종별구분=item_type,
            매매전세코드=trade_type,
        )
        return df
    except Exception as e:
        print(f'  ⚠️ KB 가격지수 조회 실패: {e}')
        return None


def get_lead_50_index():
    """KB 선도아파트 50 지수"""
    try:
        from PublicDataReader import Kbland
        kb = Kbland()
        df = kb.get_lead_apartment_50_index()
        return df
    except Exception as e:
        print(f'  ⚠️ KB 선도50 지수 조회 실패: {e}')
        return None


# ─── KB 데이터 -> DB 저장 ──────────────────────────


def save_kb_data_to_db(df, data_type, conn=None):
    """
    KB 데이터를 kb_price 테이블에 저장
    
    Args:
        df: DataFrame
        data_type: 'avg_price', 'jeonse_rate', 'market_trend', 'price_index'
        conn: DB connection (없으면 새로 생성)
    
    Returns:
        int: 저장 건수
    """
    if df is None or df.empty:
        return 0
    
    if conn is None:
        from data.database import get_conn
        conn = get_conn()
    
    cur = conn.cursor()
    count = 0
    
    for _, row in df.iterrows():
        try:
            region_code = str(row.get('지역코드', ''))
            region_name = str(row.get('지역명', ''))
            date_str = str(row.get('날짜', ''))[:10]
            
            if data_type == 'avg_price':
                price = float(row.get('평균가격', 0) or 0)
                cur.execute('''
                    INSERT OR REPLACE INTO kb_price
                    (region, apt_name, price_type, avg_price, low_price, high_price, collected_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (f'{region_code} ({region_name})', data_type, 'avg_price',
                      price, 0, 0, date_str))
            elif data_type == 'jeonse_rate':
                rate = float(row.get('전세가격비율', 0) or 0)
                cur.execute('''
                    INSERT OR REPLACE INTO kb_price
                    (region, apt_name, price_type, avg_price, low_price, high_price, collected_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (f'{region_code} ({region_name})', data_type, 'jeonse_rate',
                      rate, 0, 0, date_str))
            elif data_type == 'market_trend':
                trend = float(row.get('매수우위지수', 0) or 0)
                cur.execute('''
                    INSERT OR REPLACE INTO kb_price
                    (region, apt_name, price_type, avg_price, low_price, high_price, collected_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (f'{region_code} ({region_name})', data_type, 'market_trend',
                      trend, 0, 0, date_str))
            elif data_type == 'price_index':
                index_val = float(row.get('가격지수', 0) or 0)
                cur.execute('''
                    INSERT OR REPLACE INTO kb_price
                    (region, apt_name, price_type, avg_price, low_price, high_price, collected_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (f'{region_code} ({region_name})', data_type, 'price_index',
                      index_val, 0, 0, date_str))
            
            if cur.rowcount > 0:
                count += 1
        except Exception as e:
            pass
    
    conn.commit()
    if conn:
        pass  # 호출자에서 close
    return count


# ─── 통합 수집 ──────────────────────────────────────


def collect_all_kb():
    """KB 전체 데이터 수집 및 DB 저장"""
    print('🏢 KB부동산 데이터 수집 시작...')
    from data.database import get_conn
    conn = get_conn()
    total = 0
    
    # 1) 평균매매가
    print('  📊 평균매매가...')
    df = get_avg_price()
    if df is not None:
        n = save_kb_data_to_db(df, 'avg_price', conn)
        total += n
        print(f'    → {n}건 저장')
    
    # 2) 전세가율
    print('  📊 전세가율...')
    df = get_jeonse_rate()
    if df is not None:
        n = save_kb_data_to_db(df, 'jeonse_rate', conn)
        total += n
        print(f'    → {n}건 저장')
    
    # 3) 매수우위지수
    print('  📊 매수우위지수...')
    df = get_market_trend()
    if df is not None:
        n = save_kb_data_to_db(df, 'market_trend', conn)
        total += n
        print(f'    → {n}건 저장')
    
    conn.close()
    print(f'  ✅ KB 총 {total}건 저장 완료')
    return total


# ─── CLI 테스트 ─────────────────────────────────────


if __name__ == '__main__':
    # KB 데이터 조회 테스트
    print('=== KB 평균매매가 (서울, 최근) ===')
    df = get_avg_price()
    if df is not None:
        seoul = df[df['지역코드'] == '1100000000']
        if not seoul.empty:
            print(seoul.tail(5).to_string(index=False))
    
    print('\n=== KB 전세가율 ===')
    df = get_jeonse_rate()
    if df is not None:
        for code in ['1100000000', '1B0000', '1A0000', '4100000000']:
            rd = df[df['지역코드'] == code]
            if not rd.empty:
                last = rd.iloc[-1]
                print(f'  {last["지역명"]:10s} 전세가율 {last["전세가격비율"]:.1f}%')
    
    print('\n=== KB 매수우위지수 ===')
    df = get_market_trend()
    if df is not None:
        for code in ['1100000000', '1B0000', '1A0000']:
            rd = df[df['지역코드'] == code]
            if not rd.empty:
                last = rd.iloc[-1]
                print(f'  {last["지역명"]:10s} 매수우위 {last["매수우위지수"]:.1f}')

