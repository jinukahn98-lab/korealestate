"""
5호선 6억대 아파트 호갱노노 데이터 일괄 수집
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.hogangnono import (
    search_apts, get_apt_simple, get_room_types,
    get_monthly_reports, get_items, TRADE_TYPE_LABEL
)
from data.database import get_conn
import time

# 5호선 역세권 6억대 단지 hash (검증 완료)
HASHES = {
    # 강서구 방화역
    '18Hb3': ('방화5단지', '강서구 방화동'),
    '18tc5': ('방화2단지', '강서구 방화동'),
    '19wb4': ('방화삼정그린코아(방화그린)', '강서구 방화동'),
    '18uc9': ('마곡중앙하이츠', '강서구 방화동'),
    '19k9a': ('마곡서광(치현마을)', '강서구 방화동'),
    '19ta7': ('마곡한숲대림', '강서구 방화동'),
    
    # 강서구 등촌동 (9호선이지만 5호선 화곡역 도보 가능)
    '10Y71': ('등촌주공5단지', '강서구 등촌동'),
    '11fa9': ('등촌주공11단지', '강서구 등촌동'),
    
    # 강서구 화곡/우장산역
    '14k74': ('초록', '강서구 화곡동'),
    '13E5c': ('우장산휴먼빌', '강서구 화곡동'),
    '18qad': ('길훈', '강서구 마곡동'),
    
    # 동대문구 답십리역
    'eN41': ('동서울한양', '동대문구 답십리동'),
    'eMb6': ('동답한신', '동대문구 답십리동'),
    'eYf8': ('우성그린', '동대문구 답십리동'),
    'ez9f': ('전농우성', '동대문구 전농동'),

    # 강동구 길동/천호
    'eNYxL': ('한일시티타워', '강동구 길동'),
    'de4F': ('동아(상일동)', '강동구 상일동'),
    
    # 영등포구 신길
    'bQV6': ('성원(650)', '영등포구 대림동'),
    '4SO6b': ('현대3차(대림)', '영등포구 대림동'),
}

# 누락된 단지 추가 검색
EXTRA = {
    '장미': '강서구 방화동',
    '방화그린': '강서구 방화동',
    '청솔(강서)': '강서구 방화동',
    '신동아(방화)': '강서구 방화동',
    '삼성꽃마을': '강서구 방화동',
    '대림e편한세상(화곡)': '강서구 화곡동',
    '현대3차(영등포)': '영등포구 대림동',
    '늘푸른(강동)': '강동구 천호동',
    '한화오벨리스크(마포)': '마포구 도화동',
}

conn = get_conn()
cur = conn.cursor()
total_apts = 0
total_trades = 0
total_items = 0

# 1) 기존 hash로 수집
for apt_hash, (apt_name, region) in HASHES.items():
    print(f'\n[{apt_hash}] {apt_name} ({region})')
    
    # 기본 정보 저장
    info = get_apt_simple(apt_hash)
    if info:
        cur.execute('''
            INSERT OR IGNORE INTO hogang_apts
            (apt_hash, apt_name, address, road_address, region_code, lat, lng, household, trade_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            apt_hash, info.get('name', apt_name),
            info.get('address', ''), info.get('roadAddress', ''),
            info.get('regionCode', ''), info.get('lat'), info.get('lng'),
            info.get('areaNo', 0), info.get('areaNo', 0)
        ))
        if cur.rowcount > 0:
            total_apts += 1
    
    # 평형 정보
    rts = get_room_types(apt_hash)
    print(f'   평형: {len(rts)}종')
    
    # 실거래가
    for area_idx, rt in enumerate(rts[:3]):
        area_no = area_idx + 1
        rt_name = rt.get('zigbangRoomType', f'area{area_no}')
        
        for tt, label in TRADE_TYPE_LABEL.items():
            reports = get_monthly_reports(apt_hash, tt, area_no)
            if not reports:
                continue
                
            for month in reports:
                trade_date = (month.get('date', '') or '')[:10].replace('T', ' ')
                for trade in month.get('trades', []):
                    price = trade.get('price') or month.get('averagePrice', 0)
                    if not price:
                        continue
                    floor = trade.get('floor', 0)
                    day = trade.get('day', 1)
                    category = trade.get('category', tt + 1)
                    is_lower = 1 if trade.get('isLowerFloor') else 0
                    
                    try:
                        dt = f"{trade_date[:7]}-{day:02d}" if trade_date and day else trade_date
                    except:
                        dt = trade_date
                    
                    cur.execute('''
                        INSERT OR IGNORE INTO hogang_trades
                        (apt_hash, apt_name, area_no, room_type, trade_type,
                         trade_date, price, floor, category, is_lower_floor)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (apt_hash, apt_name, area_no, rt_name, tt,
                          dt, int(price), floor, category, is_lower))
                    if cur.rowcount > 0:
                        total_trades += 1
            
            time.sleep(0.1)
    
    conn.commit()
    time.sleep(0.3)

# 2) 추가 검색
print('\n\n=== 추가 검색 ===')
for search_term, expected_region in EXTRA.items():
    apts = search_apts(search_term)
    found = None
    for apt in apts:
        if expected_region in apt.get('address', ''):
            found = apt
            break
    
    if not found and apts:
        found = apts[0]
    
    if found and found['id'] not in HASHES:
        apt_hash = found['id']
        apt_name = found['name']
        print(f'\n[추가] {apt_name} ({found.get("address","")}) hash={apt_hash}')
        
        info = get_apt_simple(apt_hash)
        if info:
            cur.execute('''
                INSERT OR IGNORE INTO hogang_apts
                (apt_hash, apt_name, address, road_address, region_code, lat, lng, household, trade_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (apt_hash, apt_name, found.get('address',''), '',
                  found.get('region_code',''), found.get('lat'), found.get('lng'), 0, found.get('trade_count',0)))
            if cur.rowcount > 0:
                total_apts += 1
        
        rts = get_room_types(apt_hash)
        for area_idx, rt in enumerate(rts[:3]):
            area_no = area_idx + 1
            rt_name = rt.get('zigbangRoomType', f'area{area_no}')
            for tt, label in TRADE_TYPE_LABEL.items():
                reports = get_monthly_reports(apt_hash, tt, area_no)
                if not reports:
                    continue
                for month in reports:
                    trade_date = (month.get('date', '') or '')[:10].replace('T', ' ')
                    for trade in month.get('trades', []):
                        price = trade.get('price') or month.get('averagePrice', 0)
                        if not price:
                            continue
                        floor = trade.get('floor', 0)
                        day = trade.get('day', 1)
                        category = trade.get('category', tt + 1)
                        is_lower = 1 if trade.get('isLowerFloor') else 0
                        try:
                            dt = f"{trade_date[:7]}-{day:02d}" if trade_date and day else trade_date
                        except:
                            dt = trade_date
                        cur.execute('''
                            INSERT OR IGNORE INTO hogang_trades
                            (apt_hash, apt_name, area_no, room_type, trade_type,
                             trade_date, price, floor, category, is_lower_floor)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (apt_hash, apt_name, area_no, rt_name, tt,
                              dt, int(price), floor, category, is_lower))
                        if cur.rowcount > 0:
                            total_trades += 1
                time.sleep(0.1)
        
        conn.commit()
        time.sleep(0.5)

conn.close()
print(f'\n✅ 5호선 6억대 단지 수집 완료!')
print(f'   단지: {total_apts}건 / 실거래: {total_trades}건')
