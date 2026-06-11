"""
국토교통부(MOLIT) 실거래가 API 수집기
- 아파트매매 실거래자료: getRTMSDataSvcAptTrade
- 아파트 전월세 실거래자료: getRTMSDataSvcAptRent
"""

import requests
import pandas as pd
import time
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

MOLIT_BASE = "https://apis.data.go.kr/1613000"

SERVICE_KEYS = {
    'trade': 'RTMSDataSvcAptTrade',
    'rent': 'RTMSDataSvcAptRent',
}

SALES_TYPE_NAMES = {
    'trade': '매매',
    'rent': '전월세',
}

FIELD_MAP = {
    'trade': {
        '아파트': 'aptName', '법정동': 'umdNm', '전용면적': 'excluUseAr',
        '층': 'floor', '거래금액': 'dealAmount', '건축년도': 'buildYear',
        '년': 'dealYear', '월': 'dealMonth', '일': 'dealDay',
        '도로명': 'roadNm', '거래유형': 'rletTpNm',
        '거래일': None,  # 합성
    },
    'rent': {
        '아파트': 'aptName', '법정동': 'umdNm', '전용면적': 'excluUseAr',
        '층': 'floor', '보증금': 'rentArea', '월세': 'mthRent',
        '건축년도': 'buildYear', '년': 'dealYear', '월': 'dealMonth', '일': 'dealDay',
        '전월세구분': 'jrsdRentGtn', '도로명': 'roadNm',
        '거래일': None,
    }
}


def get_service_key():
    """API 키 조회"""
    key = os.getenv('MOLIT_API_KEY', '')
    if not key:
        key = os.getenv('MOLIT_API_KEY', '')
    return key


def _parse_amount(amount_str):
    """금액 문자열을 숫자로 변환 (예: '12,300' -> 12300)"""
    if not amount_str:
        return 0
    return int(amount_str.replace(',', '').strip())


def _build_deal_date(row):
    """년월일을 조합하여 거래일 문자열 생성"""
    y = str(int(row.get('년', 0)))
    m = str(int(row.get('월', 0))).zfill(2)
    d = str(int(row.get('일', 0))).zfill(2)
    return f"{y}-{m}-{d}"


def fetch_trades(lawd_cd, deal_ymd, service_key=None, max_pages=5):
    """
    아파트 매매 실거래가 조회

    Parameters:
        lawd_cd (str): 법정동코드 5자리
        deal_ymd (str): 거래년월 (예: '202506')
        service_key (str): API 키 (없으면 환경변수에서 로드)
        max_pages (int): 최대 페이지 수

    Returns:
        pd.DataFrame: 실거래가 데이터프레임
    """
    if not service_key:
        service_key = get_service_key()

    if not service_key:
        print("❌ MOLIT_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
        print("   공공데이터포털(www.data.go.kr)에서 API 키를 발급받아 .env에 설정:")
        print("   MOLIT_API_KEY=your_decoding_key_here")
        return None

    url = f"{MOLIT_BASE}/{SERVICE_KEYS['trade']}"

    all_items = []

    for page in range(1, max_pages + 1):
        params = {
            'serviceKey': service_key,
            'pageNo': str(page),
            'numOfRows': '100',
            'LAWD_CD': lawd_cd,
            'DEAL_YMD': deal_ymd,
            '_type': 'json',
        }

        try:
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code != 200:
                print(f"  ⚠ HTTP 오류: {resp.status_code}")
                break

            data = resp.json()
            header = data['response']['header']

            if header['resultCode'] != '00':
                print(f"  ⚠ API 오류: {header['resultMsg']}")
                break

            body = data['response']['body']
            items = body.get('items', {}).get('item', [])

            if not items:
                if page == 1:
                    print(f"  📭 {deal_ymd} {lawd_cd} 지역 거래 데이터 없음")
                break

            if isinstance(items, dict):
                items = [items]

            all_items.extend(items)
            total = body.get('totalCount', 0)
            print(f"  📄 페이지 {page}: {len(items)}건 (누적 {len(all_items)}건)")

            if page * 100 >= total:
                break

            time.sleep(0.3)

        except requests.exceptions.RequestException as e:
            print(f"  ⚠ 네트워크 오류: {e}")
            break
        except Exception as e:
            print(f"  ⚠ 파싱 오류: {e}")
            break

    if not all_items:
        return None

    # 데이터프레임 변환
    df = pd.DataFrame(all_items)

    # 컬럼명 한글화 및 타입 변환
    field_names = FIELD_MAP['trade']
    rename_map = {v: k for k, v in field_names.items() if v}

    result = pd.DataFrame()
    for kor, eng in rename_map.items():
        if eng in df.columns:
            result[kor] = df[eng]

    # 거래금액 변환 (만원 단위 문자열 -> 숫자)
    if '거래금액' in result.columns:
        result['거래금액'] = result['거래금액'].astype(str).apply(_parse_amount)

    # 면적 변환
    if '전용면적' in result.columns:
        result['전용면적'] = pd.to_numeric(result['전용면적'], errors='coerce')

    # 층 변환
    if '층' in result.columns:
        result['층'] = pd.to_numeric(result['층'], errors='coerce').fillna(0).astype(int)

    # 거래일 생성
    for col in ['년', '월', '일']:
        if col not in result.columns and col in df.columns:
            result[col] = df[col]

    if all(c in result.columns for c in ['년', '월', '일']):
        result['거래일'] = result.apply(_build_deal_date, axis=1)
    elif all(c in df.columns for c in ['dealYear', 'dealMonth', 'dealDay']):
        result['년'] = df['dealYear']
        result['월'] = df['dealMonth']
        result['일'] = df['dealDay']
        result['거래일'] = result.apply(_build_deal_date, axis=1)

    print(f"  ✅ 총 {len(result)}건 매매 데이터 수집 완료")
    return result


def fetch_rents(lawd_cd, deal_ymd, service_key=None, max_pages=5):
    """
    아파트 전월세 실거래가 조회

    Parameters:
        lawd_cd (str): 법정동코드 5자리
        deal_ymd (str): 거래년월 (예: '202506')
        service_key (str): API 키
        max_pages (int): 최대 페이지 수

    Returns:
        pd.DataFrame: 전월세 데이터프레임
    """
    if not service_key:
        service_key = get_service_key()

    if not service_key:
        print("❌ MOLIT_API_KEY가 설정되지 않았습니다.")
        return None

    url = f"{MOLIT_BASE}/{SERVICE_KEYS['rent']}"

    all_items = []

    for page in range(1, max_pages + 1):
        params = {
            'serviceKey': service_key,
            'pageNo': str(page),
            'numOfRows': '100',
            'LAWD_CD': lawd_cd,
            'DEAL_YMD': deal_ymd,
            '_type': 'json',
        }

        try:
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code != 200:
                print(f"  ⚠ HTTP 오류: {resp.status_code}")
                break

            data = resp.json()
            header = data['response']['header']

            if header['resultCode'] != '00':
                print(f"  ⚠ API 오류: {header['resultMsg']}")
                break

            body = data['response']['body']
            items = body.get('items', {}).get('item', [])

            if not items:
                if page == 1:
                    print(f"  📭 {deal_ymd} {lawd_cd} 지역 전월세 데이터 없음")
                break

            if isinstance(items, dict):
                items = [items]

            all_items.extend(items)
            total = body.get('totalCount', 0)
            print(f"  📄 페이지 {page}: {len(items)}건 (누적 {len(all_items)}건)")

            if page * 100 >= total:
                break

            time.sleep(0.3)

        except Exception as e:
            print(f"  ⚠ 오류: {e}")
            break

    if not all_items:
        return None

    df = pd.DataFrame(all_items)

    field_names = FIELD_MAP['rent']
    rename_map = {v: k for k, v in field_names.items() if v}

    result = pd.DataFrame()
    for kor, eng in rename_map.items():
        if eng in df.columns:
            result[kor] = df[eng]

    # 보증금/월세 변환
    for col in ['보증금', '월세']:
        if col in result.columns:
            result[col] = result[col].astype(str).apply(_parse_amount)

    if '전용면적' in result.columns:
        result['전용면적'] = pd.to_numeric(result['전용면적'], errors='coerce')
    if '층' in result.columns:
        result['층'] = pd.to_numeric(result['층'], errors='coerce').fillna(0).astype(int)

    for col in ['년', '월', '일']:
        if col not in result.columns and col in df.columns:
            result[col] = df[col]

    if all(c in result.columns for c in ['년', '월', '일']):
        result['거래일'] = result.apply(_build_deal_date, axis=1)
    elif all(c in df.columns for c in ['dealYear', 'dealMonth', 'dealDay']):
        result['년'] = df['dealYear']
        result['월'] = df['dealMonth']
        result['일'] = df['dealDay']
        result['거래일'] = result.apply(_build_deal_date, axis=1)

    print(f"  ✅ 총 {len(result)}건 전월세 데이터 수집 완료")
    return result


def collect_recent_months(lawd_cd, months=6, data_type='trade'):
    """최근 N개월치 데이터 수집"""
    today = datetime.now()
    all_data = []

    for m in range(months):
        ym = today.year * 100 + today.month - m
        year = ym // 100
        month = ym % 100
        if month == 0:
            year -= 1
            month = 12
        deal_ymd = f"{year}{month:02d}"
        print(f"\n📅 {year}년 {month}월 데이터 수집중...")

        if data_type == 'trade':
            df = fetch_trades(lawd_cd, deal_ymd)
        else:
            df = fetch_rents(lawd_cd, deal_ymd)

        if df is not None and not df.empty:
            all_data.append(df)

    if all_data:
        return pd.concat(all_data, ignore_index=True)
    return None
