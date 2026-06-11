"""
PublicDataReader 기반 국토교통부 실거래가 수집기
- 매매: RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade
- 전월세: RTMSDataSvcAptRent/getRTMSDataSvcAptRent
"""

from PublicDataReader import TransactionPrice
from PublicDataReader.transaction.rtms import RTMS
import pandas as pd
import os
from dotenv import load_dotenv

load_dotenv()

# 올바른 non-Dev 엔드포인트
TRADE_URL = "http://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade"
RENT_URL = "http://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent"


class MolitReader:
    """PublicDataReader를 활용한 MOLIT 실거래가 수집 (non-Dev)"""

    def __init__(self):
        self.service_key = os.getenv('MOLIT_API_KEY', '')
        if not self.service_key:
            self.service_key = 'e3d185a7422610ceceef0b20d8d1af717b7ecaad39c5a995ac037a935eef3cc3'

    def _fetch(self, url, lawd_cd, year_month):
        """공통 API 호출"""
        import requests
        import time

        params = {
            'serviceKey': self.service_key,
            'LAWD_CD': lawd_cd,
            'DEAL_YMD': str(year_month),
            'pageNo': 1,
            'numOfRows': '9999',
            '_type': 'json',
        }

        try:
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code != 200:
                print(f"  ⚠ HTTP {resp.status_code}")
                return None

            data = resp.json()
            header = data['response']['header']
            if header['resultCode'] != '00':
                print(f"  ⚠ API 오류: {header['resultMsg']}")
                return None

            items = data['response']['body'].get('items', {}).get('item', [])
            if isinstance(items, dict):
                items = [items]
            if not items:
                print(f"  📭 {year_month}: 데이터 없음")
                return None

            time.sleep(0.2)
            return items

        except Exception as e:
            print(f"  ⚠ 오류: {e}")
            return None

    def fetch_trades(self, lawd_cd, year_month):
        """매매 실거래가 조회"""
        items = self._fetch(TRADE_URL, lawd_cd, year_month)
        if not items:
            return None

        df = pd.DataFrame(items)
        df.columns = {
            'sggCd': '법정동시군구코드', 'umdNm': '법정동', 'aptNm': '단지명',
            'excluUseAr': '전용면적', 'dealYear': '계약년도', 'dealMonth': '계약월',
            'dealDay': '계약일', 'dealAmount': '거래금액', 'floor': '층',
            'buildYear': '건축년도', 'jibun': '지번', 'roadNm': '도로명',
            'dealingGbn': '거래유형', 'aptDong': '동',
        }.get  # partial rename
        return df

    def fetch_rents(self, lawd_cd, year_month):
        """전월세 실거래가 조회"""
        items = self._fetch(RENT_URL, lawd_cd, year_month)
        if not items:
            return None
        df = pd.DataFrame(items)
        # 전월세는 PublicDataReader로 (이미 잘 됨)
        from PublicDataReader import TransactionPrice
        api = TransactionPrice(service_key=self.service_key)
        return api.get_data('아파트', '전월세', lawd_cd, str(year_month))

    def collect_months(self, lawd_cd, months=6, data_type='rent'):
        """최근 N개월 데이터 수집"""
        from datetime import datetime
        today = datetime.now()
        all_data = []

        for m in range(months):
            ym = today.year * 100 + today.month - m
            year = ym // 100
            month = ym % 100
            if month == 0:
                year -= 1
                month = 12
            ym_str = f"{year}{month:02d}"

            if data_type == 'trade':
                df = self.fetch_trades(lawd_cd, ym_str)
            else:
                df = self.fetch_rents(lawd_cd, ym_str)

            if df is not None:
                # 컬럼명 통일 (PublicDataReader 한글 패턴)
                all_data.append(df)

        if all_data:
            return pd.concat(all_data, ignore_index=True)
        return None
