#!/usr/bin/env python3
"""MOLIT 역대 실거래가 일괄 수집 스크립트 (2019~2023)"""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from collectors.molit import fetch_trades, fetch_rents
from data.database import save_apt_trades, save_apt_rents
from data.legal_dong_codes import get_all_regions

YEAR_RANGE = range(2019, 2024)
TARGET_REGIONS = [
    # 서울 25개구
    ('11680', '서울특별시 강남구'), ('11740', '서울특별시 강동구'),
    ('11305', '서울특별시 강북구'), ('11405', '서울특별시 강서구'),
    ('11620', '서울특별시 관악구'), ('11530', '서울특별시 광진구'),
    ('11545', '서울특별시 구로구'), ('11560', '서울특별시 금천구'),
    ('11350', '서울특별시 노원구'), ('11320', '서울특별시 도봉구'),
    ('11230', '서울특별시 동대문구'), ('11590', '서울특별시 동작구'),
    ('11440', '서울특별시 마포구'), ('11290', '서울특별시 서대문구'),
    ('11650', '서울특별시 서초구'), ('11710', '서울특별시 성동구'),
    ('11215', '서울특별시 성북구'), ('11700', '서울특별시 송파구'),
    ('11470', '서울특별시 양천구'), ('11570', '서울특별시 영등포구'),
    ('11170', '서울특별시 용산구'), ('11380', '서울특별시 은평구'),
    ('11110', '서울특별시 종로구'), ('11140', '서울특별시 중구'),
    ('11260', '서울특별시 중랑구'),
]

def collect_historical(data_type='trade'):
    total = 0
    for year in YEAR_RANGE:
        for month in range(1, 13):
            ym = f'{year}{month:02d}'
            for lawd_cd, region_name in TARGET_REGIONS:
                try:
                    if data_type == 'trade':
                        df = fetch_trades(lawd_cd, ym)
                        if df is not None:
                            saved = save_apt_trades(df, lawd_cd, region_name)
                            total += saved
                    else:
                        df = fetch_rents(lawd_cd, ym)
                        if df is not None:
                            saved = save_apt_rents(df, lawd_cd, region_name)
                            total += saved
                    time.sleep(0.3)
                except Exception as e:
                    print(f'  ⚠ {region_name} {ym} 오류: {e}')
    return total

if __name__ == '__main__':
    data_type = sys.argv[1] if len(sys.argv) > 1 else 'trade'
    print(f'📡 역대 {SALES_TYPE_NAMES.get(data_type, data_type)} 데이터 수집 시작...')
    print(f'   대상: {len(TARGET_REGIONS)}개 지역, {len(list(YEAR_RANGE))}년 (2019~2023)')
    total = collect_historical(data_type)
    print(f'\n✅ 완료! 총 {total}건 저장됨')
    
try:
    from collectors.molit import SALES_TYPE_NAMES
except:
    pass
