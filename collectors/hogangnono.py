"""
호갱노노(Hogangnono) 공개 API 수집기

호갱노노 웹(https://hogangnono.com)에서 사용하는 내부 API를 통해
아파트 실거래가, 현재 매물, 평형 정보 등을 수집한다.

엔드포인트 (Base: https://hogangnono.com/api/v2):
  GET /searches/suggestions/new?query=검색어   - 단지 검색 (고유 hash ID 획득)
  GET /apts/{aptHash}/simple                   - 단지 기본 정보
  GET /apts/{aptHash}/room-types               - 평형 목록 (areaNo 매핑)
  GET /apts/{aptHash}/monthly-reports?tradeType=N&areaNo=N  - 월별 실거래가
  GET /apts/{aptHash}/items                    - 현재 매물
  GET /apts/{aptHash}/trade-real               - 실거래 상세
"""
import requests
import time
import json
from datetime import datetime
from typing import Optional

BASE_URL = "https://hogangnono.com/api/v2"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Referer': 'https://hogangnono.com/',
    'Origin': 'https://hogangnono.com',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
}

# TradeType enum: 0=매매, 1=전세, 2=월세
TRADE_TYPE_SALE = 0
TRADE_TYPE_DEPOSIT = 1  # 전세
TRADE_TYPE_RENT = 2     # 월세

TRADE_TYPE_LABEL = {
    TRADE_TYPE_SALE: '매매',
    TRADE_TYPE_DEPOSIT: '전세',
    TRADE_TYPE_RENT: '월세',
}

# ─── 기본 API 호출 ─────────────────────────────────


def _get(path, params=None, retries=3):
    """호갱노노 API GET 요청"""
    url = f"{BASE_URL}{path}"
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if data.get('status') == 'success':
                    return data.get('data')
                # 에러 메시지 로깅
                err = data.get('error', 'unknown')
                msg = data.get('message', '')
                if attempt < retries - 1:
                    time.sleep(1)
                    continue
                return None
            elif r.status_code == 429:
                time.sleep(3 * (attempt + 1))
                continue
            else:
                if attempt < retries - 1:
                    time.sleep(1)
                    continue
                return None
        except requests.exceptions.Timeout:
            if attempt < retries - 1:
                time.sleep(2)
                continue
            return None
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(1)
                continue
            return None
    return None


# ─── 검색 ──────────────────────────────────────────


def search_apts(query: str) -> list:
    """
    아파트 검색 (검색어로 hash ID 획득)
    
    Returns:
        list: [{'id': 'aptHash', 'name': '단지명', 'address': '주소',
                'region_code': '1123010500', 'lat': ..., 'lng': ...,
                'household': 세대수, 'trade_count': 거래량}, ...]
    """
    data = _get('/searches/suggestions/new', {'query': query})
    if not data:
        return []
    apts = []
    for apt in (data.get('matched', {}).get('apt', {}).get('list', [])):
        apts.append({
            'id': apt.get('id'),
            'name': apt.get('name'),
            'address': apt.get('address'),
            'road_address': apt.get('road_address'),
            'region_code': apt.get('region_code'),
            'lat': apt.get('lat', apt.get('location', {}).get('lat')),
            'lng': apt.get('lng', apt.get('location', {}).get('lon')),
            'household': apt.get('household', 0),
            'trade_count': apt.get('trade_count', 0),
            'type': apt.get('type', 0),
        })
    return apts


# ─── 단지 정보 ─────────────────────────────────────


def get_apt_simple(apt_hash: str) -> Optional[dict]:
    """단지 기본 정보"""
    return _get(f'/apts/{apt_hash}/simple')


def get_room_types(apt_hash: str) -> list:
    """평형 목록"""
    data = _get(f'/apts/{apt_hash}/room-types')
    if not data:
        return []
    return data.get('zigbangRoomTypes', [])


def get_dong_list(apt_hash: str) -> list:
    """동 목록 (동별 정보)"""
    data = _get(f'/apts/{apt_hash}/dongs')
    if not data:
        return []
    return data.get('dongList', [])


# ─── 실거래가 ───────────────────────────────────────


def get_monthly_reports(apt_hash: str, trade_type: int = 0, area_no: int = 1):
    """
    평형별 월별 실거래가
    
    Args:
        apt_hash: 아파트 고유 hash
        trade_type: 0=매매, 1=전세, 2=월세
        area_no: 평형 번호 (room-types에서 확인)
    
    Returns:
        list: [{'date': '2026-05-31T15:00:00.000Z', 'minPrice': ..., 'maxPrice': ...,
                'averagePrice': ..., 'volume': 거래수, 
                'trades': [{'price': ..., 'floor': ..., 'day': ..., 'category': 1}, ...]}, ...]
    """
    data = _get(f'/apts/{apt_hash}/monthly-reports', {
        'tradeType': trade_type,
        'areaNo': area_no,
    })
    if not data:
        return []
    # shortTermReport: 최근 3년, longTermReport: 3~10년
    return data.get('shortTermReport', [])


def get_all_trade_types(apt_hash: str, area_no: int = 1):
    """매매/전세/월세 실거래가 모두 수집"""
    result = {}
    for tt, label in TRADE_TYPE_LABEL.items():
        reports = get_monthly_reports(apt_hash, tt, area_no)
        if reports:
            result[label] = reports
        time.sleep(0.3)
    return result


# ─── 현재 매물 ─────────────────────────────────────


def get_items(apt_hash: str) -> list:
    """현재 매물 (직방 연동)"""
    data = _get(f'/apts/{apt_hash}/items')
    if not data:
        return []
    items = data.get('items', [])
    # items가 dict 형태일 수도 있음
    if isinstance(items, dict):
        items = items.get('list', [])
    return items


# ─── 고수준 수집 함수 ─────────────────────────────


def collect_apt_complete(apt_hash: str, apt_name: str = '', max_areas: int = 5):
    """
    단지 1개의 전체 데이터 수집
    
    Returns:
        dict: {
            'info': {...},          # get_apt_simple 결과
            'room_types': [...],    # 평형 목록
            'trades': {             # trade_type_label -> [월별리포트]
                '매매': [...],
                '전세': [...],
                '월세': [...],
            },
            'items': [...]          # 현재 매물
        }
    """
    result = {'info': None, 'room_types': [], 'trades': {}, 'items': []}
    
    # 기본 정보
    info = get_apt_simple(apt_hash)
    if not info:
        return result
    result['info'] = info
    
    # 평형 정보
    rts = get_room_types(apt_hash)
    result['room_types'] = rts
    
    # 첫 N개 평형의 실거래가 수집
    for i, rt in enumerate(rts[:max_areas]):
        area_no = i + 1  # room_types는 0-index지만 areaNo는 1부터
        zigbang_id = rt.get('zigbangRoomTypeId')
        rt_name = rt.get('zigbangRoomType', f'평형{area_no}')
        
        for tt, label in TRADE_TYPE_LABEL.items():
            reports = get_monthly_reports(apt_hash, tt, area_no)
            if reports:
                if label not in result['trades']:
                    result['trades'][label] = {}
                result['trades'][label][rt_name] = {
                    'area_no': area_no,
                    'zigbang_id': zigbang_id,
                    'reports': reports,
                }
            time.sleep(0.15)  # rate limit 방지
        time.sleep(0.3)
    
    # 현재 매물
    items = get_items(apt_hash)
    result['items'] = items
    
    return result


def collect_region_apts(region_name: str, limit: int = 30):
    """
    특정 지역의 아파트 목록을 검색해서 전체 데이터 수집
    
    Args:
        region_name: '강서구', '답십리동' 등
        limit: 수집할 아파트 수
    
    Returns:
        list: 수집 결과 리스트
    """
    results = []
    
    # 1) 지역명으로 아파트 검색
    apts = search_apts(region_name)
    
    # 해당 지역만 필터링
    filtered = [apt for apt in apts if region_name in apt.get('address', '')]
    filtered = filtered[:limit]
    
    print(f"🔍 '{region_name}' 검색: {len(apts)}건 → {len(filtered)}건 필터링")
    
    # 2) 각 아파트 전체 데이터 수집
    for i, apt in enumerate(filtered):
        print(f"  [{i+1}/{len(filtered)}] {apt['name']} ({apt.get('address','')})")
        data = collect_apt_complete(apt['id'], apt['name'])
        data['search_info'] = apt
        results.append(data)
        time.sleep(1)
    
    return results


# ─── CLI 직접 실행 ─────────────────────────────────

if __name__ == '__main__':
    import sys
    import argparse
    parser = argparse.ArgumentParser(description='호갱노노 수집기')
    parser.add_argument('command', choices=['search', 'apt', 'region', 'items'],
                        help='search: 단지 검색 | apt: 단지 상세 | region: 지역 전체 | items: 현재매물')
    parser.add_argument('--query', '-q', help='검색어')
    parser.add_argument('--hash', '-H', help='아파트 hash ID')
    parser.add_argument('--area', '-a', type=int, default=1, help='areaNo (1부터)')
    parser.add_argument('--limit', '-l', type=int, default=10, help='최대 수집 수')
    parser.add_argument('--trade-type', '-t', type=int, default=0,
                        choices=[0, 1, 2], help='0=매매 1=전세 2=월세')
    
    args = parser.parse_args()
    
    if args.command == 'search':
        if not args.query:
            print('❌ --query (-q) 필수')
            sys.exit(1)
        apts = search_apts(args.query)
        print(f'🔍 검색 결과 ({len(apts)}건):')
        for apt in apts:
            region_code = apt.get('region_code', '')
            lat = apt.get('lat', 0)
            lng = apt.get('lng', 0)
            print(f'  [{apt["id"]}] {apt["name"]}')
            print(f'    주소: {apt["address"]}')
            print(f'    세대: {apt["household"]}  거래: {apt["trade_count"]}건')
            print(f'    code: {region_code}  좌표: {lat:.5f}, {lng:.5f}')
            print()
    
    elif args.command == 'apt':
        if not args.hash:
            print('❌ --hash (-H) 필수')
            sys.exit(1)
        data = collect_apt_complete(args.hash, max_areas=args.area)
        
        info = data.get('info')
        if info:
            print(f'🏢 {info.get("name", "?")}')
            print(f'  주소: {info.get("address", "?")}')
            print(f'  도로명: {info.get("roadAddress", "?")}')
            print(f'  GPS: {info.get("lat")}, {info.get("lng")}')
        
        rts = data.get('room_types', [])
        print(f'\n📐 평형 ({len(rts)}종):')
        for i, rt in enumerate(rts):
            print(f'  [{i+1}] {rt.get("zigbangRoomType", "?")} (id: {rt.get("zigbangRoomTypeId")})')
        
        print(f'\n💰 현재 매물: {len(data.get("items", []))}건')
        
        for label, area_data in data.get('trades', {}).items():
            for rt_name, td in area_data.items():
                reports = td.get('reports', [])
                if reports:
                    latest = reports[-1]
                    print(f'\n📊 {label} - {rt_name}:')
                    print(f'  최근: {latest.get("averagePrice", 0)/10000:.1f}억'
                          f'  (min: {latest.get("minPrice", 0)/10000:.1f}'
                          f'  max: {latest.get("maxPrice", 0)/10000:.1f})'
                          f'  거래: {latest.get("volume", 0)}건')
    
    elif args.command == 'region':
        if not args.query:
            print('❌ --query (-q) 필수 (지역명)')
            sys.exit(1)
        results = collect_region_apts(args.query, limit=args.limit)
        print(f'\n✅ 총 {len(results)}개 단지 수집 완료')
    
    elif args.command == 'items':
        if not args.hash:
            print('❌ --hash (-H) 필수')
            sys.exit(1)
        items = get_items(args.hash)
        print(f'📦 현재 매물 ({len(items)}건):')
        for item in items[:20]:
            print(f'  {item.get("title","?")} / {item.get("price","?")}만원'
                  f' / {item.get("area","?")}㎡ / {item.get("floor","?")}층'
                  f' / {item.get("sales_type","?")}')
