"""
직방(Zigbang) 현재 매물 수집기
- POST https://apis.zigbang.com/v2/items/list (geohash 기반)
- 현재 매매/전세/월세 매물 정보 수집
"""

import requests
import time
import geohash2
from datetime import datetime


GEOHASH_PRECISION = 6  # 동 단위 정밀도

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Origin': 'https://www.zigbang.com',
    'Referer': 'https://www.zigbang.com/',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
}

SALES_TYPE_MAP = {
    'sale': '매매',
    'jeonse': '전세',
    'wolse': '월세',
}

SERVICE_TYPES = ['apartment']


def geohash_encode(lat, lng, precision=GEOHASH_PRECISION):
    """위경도를 geohash로 인코딩"""
    return geohash2.encode(lat, lng, precision=precision)


def fetch_items_by_geohash(geohash, sales_types=None):
    """
    Geohash 기반 직방 매물 조회 (v2 endpoint)

    Parameters:
        geohash (str): geohash 문자열
        sales_types (list): 매물 유형 ['sale', 'jeonse', 'wolse']

    Returns:
        list: 매물 목록
    """
    if sales_types is None:
        sales_types = ['sale', 'jeonse', 'wolse']

    url = "https://apis.zigbang.com/v2/items/list"

    payload = {
        "geo": {"geohash": geohash},
        "service_type[]": SERVICE_TYPES,
        "sales_type[]": sales_types,
        "item_type": "apartment",
    }

    try:
        resp = requests.post(url, json=payload, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"  ⚠ 직방 API HTTP {resp.status_code}")
            return []

        data = resp.json()
        items = data.get('items', [])
        print(f"  📍 geohash={geohash}: {len(items)}개 매물")
        return items

    except requests.exceptions.RequestException as e:
        print(f"  ⚠ 직방 API 네트워크 오류: {e}")
        return []
    except Exception as e:
        print(f"  ⚠ 직방 API 파싱 오류: {e}")
        return []


def fetch_items_by_bounds(lat_min, lat_max, lng_min, lng_max, sales_types=None):
    """
    영역(bounds) 기반 직방 매물 조회 (다중 geohash)

    Parameters:
        lat_min, lat_max, lng_min, lng_max (float): 위경도 영역
        sales_types (list): 매물 유형

    Returns:
        list: 매물 목록
    """
    if sales_types is None:
        sales_types = ['sale', 'jeonse']

    center_lat = (lat_min + lat_max) / 2
    center_lng = (lng_min + lng_max) / 2
    geohash = geohash_encode(center_lat, center_lng, precision=6)

    return fetch_items_by_geohash(geohash, sales_types)


def search_by_dong(dong_name, sales_types=None):
    """
    동 이름으로 매물 검색 (주요 지역 위경도 매핑)

    Parameters:
        dong_name (str): 동 이름 (예: '압구정', '잠실')
        sales_types (list): 매물 유형
    """
    DONG_COORDS = {
        '압구정': (37.530, 127.035),
        '청담': (37.524, 127.048),
        '삼성': (37.514, 127.060),
        '대치': (37.525, 127.063),
        '역삼': (37.500, 127.036),
        '논현': (37.511, 127.025),
        '신사': (37.524, 127.020),
        '서초': (37.483, 127.032),
        '잠원': (37.513, 127.011),
        '반포': (37.503, 127.011),
        '잠실': (37.514, 127.100),
        '송파': (37.514, 127.122),
        '가락': (37.497, 127.121),
        '문정': (37.486, 127.121),
        '마포': (37.563, 126.908),
        '여의도': (37.522, 126.928),
        '용산': (37.531, 126.978),
        '광화문': (37.571, 126.976),
        '종로': (37.573, 126.979),
        '판교': (37.395, 127.110),
        '분당': (37.376, 127.113),
        '일산': (37.682, 126.770),
        '평촌': (37.391, 126.963),
        '부산해운대': (35.163, 129.164),
        '부산센텀': (35.170, 129.130),
        '인천송도': (37.381, 126.656),
        '대전둔산': (36.352, 127.377),
        '대구수성': (35.856, 128.631),
    }

    dong_name = dong_name.strip()
    if dong_name in DONG_COORDS:
        lat, lng = DONG_COORDS[dong_name]
        print(f"\n📍 {dong_name} 매물 검색 (위도={lat}, 경도={lng})")
        gh = geohash_encode(lat, lng)
        return fetch_items_by_geohash(gh, sales_types)
    else:
        print(f"  ⚠ '{dong_name}'에 대한 좌표가 없습니다.")
        print(f"  사용 가능: {', '.join(DONG_COORDS.keys())}")
        return []


def fetch_item_detail(item_id):
    """개별 매물 상세 정보 조회"""
    url = f"https://apis.zigbang.com/v2/items/{item_id}"
    detail_headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Referer': f'https://www.zigbang.com/items/{item_id}',
    }
    try:
        resp = requests.get(url, headers=detail_headers, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except:
        pass
    return None


def collect_zigbang_items(lat, lng, sales_types=None):
    """
    편의 함수: 위경도로 직방 매물 수집

    Parameters:
        lat (float): 위도
        lng (float): 경도
        sales_types (list): 매물 유형

    Returns:
        list: 가공된 매물 정보 리스트
    """
    if sales_types is None:
        sales_types = ['sale', 'jeonse']

    gh = geohash_encode(lat, lng)
    print(f"🔍 Geohash: {gh} (위도={lat}, 경도={lng})")

    items = fetch_items_by_geohash(gh, sales_types)

    if not items:
        print("  ❌ 수집된 매물이 없습니다.")
        return []

    # 필드 정리
    processed = []
    for item in items:
        pi = {
            'item_id': str(item.get('item_id', '')),
            'title': item.get('title', ''),
            'sales_type': SALES_TYPE_MAP.get(item.get('sales_type', ''), item.get('sales_type', '')),
            'deposit': int(item.get('deposit', 0) or 0),
            'rent': int(item.get('rent', 0) or 0),
            'price': int(item.get('price', 0) or 0),
            'area': float(item.get('area', 0) or 0) if item.get('area') else 0,
            'floor': int(item.get('floor', 0) or 0),
            'lat': float(item.get('lat', 0)),
            'lng': float(item.get('lng', 0)),
            'address': item.get('address', ''),
        }
        processed.append(pi)

    by_type = {}
    for p in processed:
        st = p['sales_type']
        by_type[st] = by_type.get(st, 0) + 1

    print(f"  ✅ 총 {len(processed)}개 매물 수집 완료")
    for t, c in by_type.items():
        print(f"     - {t}: {c}개")

    return processed
