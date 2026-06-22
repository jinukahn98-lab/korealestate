#!/usr/bin/env python3
"""서울 전 지역 + 주요 도시 부동산 데이터 일괄 수집"""
import requests
import pandas as pd
import time
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from data.database import save_apt_trades, save_apt_rents, init_db
from data.legal_dong_codes import get_all_regions

KEY = 'e3d185a7422610ceceef0b20d8d1af717b7ecaad39c5a995ac037a935eef3cc3'

# 서울 25개구 법정동코드
SEOUL = {
    '11110': '종로구', '11140': '중구', '11170': '용산구',
    '11200': '성동구', '11215': '광진구', '11230': '동대문구',
    '11260': '중랑구', '11290': '성북구', '11305': '강북구',
    '11320': '도봉구', '11350': '노원구', '11380': '은평구',
    '11410': '서대문구', '11440': '마포구', '11470': '양천구',
    '11500': '강서구', '11530': '구로구', '11545': '금천구',
    '11560': '영등포구', '11590': '동작구', '11620': '관악구',
    '11650': '서초구', '11680': '강남구', '11710': '송파구',
    '11740': '강동구',
}

# 주요 지역
MAJOR = {
    # 경기
    '41111': '수원시 장안구', '41113': '수원시 권선구',
    '41115': '수원시 팔달구', '41117': '수원시 영통구',
    '41131': '성남시 수정구', '41133': '성남시 중원구', '41135': '성남시 분당구',
    '41150': '의정부시', '41171': '안양시 만안구', '41173': '안양시 동안구',
    '41190': '부천시', '41210': '광명시', '41220': '평택시',
    '41271': '안산시 상록구', '41273': '안산시 단원구',
    '41281': '고양시 덕양구', '41285': '고양시 일산동구', '41287': '고양시 일산서구',
    '41290': '과천시', '41310': '구리시', '41320': '남양주시',
    '41350': '오산시', '41360': '시흥시', '41370': '군포시',
    '41380': '의왕시', '41390': '하남시', '41410': '용인시 처인구',
    '41411': '용인시 수지구', '41413': '용인시 기흥구',
    '41430': '파주시', '41450': '이천시', '41460': '안성시',
    '41480': '화성시', '41500': '광주시', '41550': '양주시',
    '41570': '포천시', '41610': '여주시',
    # 부산
    '26230': '부산진구', '26350': '해운대구', '26290': '남구',
    '26410': '금정구', '26500': '수영구',
    # 인천
    '28200': '연수구', '28245': '계양구', '28237': '부평구',
    '28260': '서구', '28140': '동구',
    # 대구
    '27260': '수성구', '27230': '북구', '27200': '남구',
    # 대전
    '30200': '유성구', '30170': '서구', '30140': '중구',
    # 광주
    '29170': '북구', '29155': '남구', '29200': '광산구',
    # 세종
    '36110': '세종특별자치시',
}

TRADE_URL = 'http://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade'
RENT_URL = 'http://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent'

from datetime import datetime

def _month_range(start_ym='202001'):
    """Generate YYYYMM list from start_ym to current month"""
    now = datetime.now()
    months = []
    y, m = int(start_ym[:4]), int(start_ym[4:6])
    while (y, m) <= (now.year, now.month):
        months.append(f'{y}{m:02d}')
        m += 1
        if m > 12:
            y += 1
            m = 1
    return months

MONTHS = _month_range('202001')

def fetch(url, label, code, region_name, months, save_fn):
    total = 0
    for ym in months:
        try:
            r = requests.get(url, params={
                'serviceKey': KEY, 'LAWD_CD': code, 'DEAL_YMD': ym,
                'pageNo': 1, 'numOfRows': '9999', '_type': 'json'
            }, timeout=30)
            if r.status_code == 200:
                body = r.json()['response']['body']
                items = body.get('items', {}).get('item', [])
                if isinstance(items, dict): items = [items]
                if items:
                    count = save_fn(pd.DataFrame(items), code, region_name)
                    total += count if count else 0
                else:
                    print(f'  📭 {ym}: 데이터 없음')
        except Exception as e:
            print(f'  ⚠ {label} {ym}: {str(e)[:60]}')
        time.sleep(0.2)
    return total

def run():
    print('╔' + '═'*58 + '╗')
    print('║   🏠 전국 부동산 데이터 일괄 수집                    ║')
    print('╚' + '═'*58 + '╝')

    init_db()

    PREFIX = {
        '11': '서울특별시', '41': '경기도', '26': '부산광역시',
        '27': '대구광역시', '28': '인천광역시', '29': '광주광역시',
        '30': '대전광역시', '36': '세종특별자치시',
    }
    all_regions = {}
    all_regions.update(SEOUL)
    all_regions.update(MAJOR)

    total_t = total_r = 0
    i = 0
    for code, name in all_regions.items():
        i += 1
        prefix = PREFIX.get(code[:2], '')
        region_name = f'{prefix} {name}' if prefix else name
        print(f'\n[{i}/{len(all_regions)}] {region_name} ({code})')

        t = fetch(TRADE_URL, '매매', code, region_name, MONTHS, save_apt_trades)
        total_t += t
        r = fetch(RENT_URL, '전월세', code, region_name, MONTHS[:3], save_apt_rents)
        total_r += r
        print(f'   ✅ 매매 {t}건 / 전월세 {r}건')

    print(f'\n{"="*60}')
    print(f'  🏆 수집 완료! 전체: 매매 {total_t:,}건 / 전월세 {total_r:,}건')
    print(f'  📍 총 {len(all_regions)}개 지역')
    print(f'{"="*60}')

if __name__ == '__main__':
    run()
