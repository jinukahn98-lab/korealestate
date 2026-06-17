"""
부동산 데이터 자동 수집 스크립트 (cron 용)
실행: python scripts/collect_all.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))
from data.database import init_db, save_apt_trades, save_apt_rents
from data.legal_dong_codes import save_to_db, get_all_regions
import requests, time
import pandas as pd
from datetime import datetime

KEY = os.getenv("MOLIT_API_KEY", "")
TRADE_URL = 'https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade'
RENT_URL = 'https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent'

# 수집할 주요 지역 (서울/경기/부산 핵심 지역)
TARGET_REGIONS = {
    '11680': '서울특별시 강남구', '11650': '서울특별시 서초구', '11710': '서울특별시 송파구',
    '11740': '서울특별시 강동구', '11440': '서울특별시 마포구', '11170': '서울특별시 용산구',
    '11620': '서울특별시 관악구', '11500': '서울특별시 강서구', '11230': '서울특별시 동대문구',
    '11590': '서울특별시 동작구', '11380': '서울특별시 은평구',
    '41135': '경기도 성남시 분당구', '41117': '경기도 수원시 영통구',
    '41480': '경기도 화성시', '41273': '경기도 안산시 단원구',
    '26350': '부산광역시 해운대구', '26410': '부산광역시 금정구',
    '27260': '대구광역시 수성구', '30200': '대전광역시 유성구',
}

def collect_region(url, label, code, name, months, save_fn):
    total = 0
    for ym in months:
        params = {'serviceKey': KEY, 'LAWD_CD': code, 'DEAL_YMD': ym, 'pageNo': 1, 'numOfRows': '9999', '_type': 'json'}
        try:
            r = requests.get(url, params=params, timeout=30)
            if r.status_code == 200:
                items = r.json()['response']['body'].get('items', {}).get('item', [])
                if isinstance(items, dict): items = [items]
                if items:
                    df = pd.DataFrame(items)
                    c = save_fn(df, code, name)
                    total += c
            time.sleep(0.3)
        except:
            pass
    return total

def run():
    print(f'🏠 부동산 데이터 수집 시작 ({datetime.now().strftime("%Y-%m-%d %H:%M")})')
    init_db()
    save_to_db()

    now = datetime.now()
    months = []
    for i in range(6):
        ym = now.year * 100 + now.month - i
        y = ym // 100
        m = ym % 100
        if m == 0: y -= 1; m = 12
        months.append(f'{y}{m:02d}')

    for code, name in TARGET_REGIONS.items():
        print(f'\n📍 {name} ({code})')
        t = collect_region(TRADE_URL, '매매', code, name, months, save_apt_trades)
        r = collect_region(RENT_URL, '전월세', code, name, months, save_apt_rents)
        print(f'  매매 {t}건 + 전월세 {r}건')

    print(f'\n✅ 수집 완료! ({datetime.now().strftime("%Y-%m-%d %H:%M")})')

if __name__ == '__main__':
    run()
