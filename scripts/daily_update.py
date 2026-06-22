#!/usr/bin/env python3
"""
부동산 데일리 업데이트 스크립트
1. 스마트 데이터 수집 (DB 최신일 이후만)
2. 분석 실행 (ranking + score)
3. 위키 저장 (daily-briefing/YYYY-MM-DD.md)
4. 브리핑 문자열 출력
"""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))
from datetime import datetime
import requests, pandas as pd

KEY = os.getenv("MOLIT_API_KEY", "e3d185a7422610ceceef0b20d8d1af717b7ecaad39c5a995ac037a935eef3cc3")
TRADE_URL = 'http://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade'
RENT_URL = 'http://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent'

# 서울 25개구 + 주요도시 (수집용)
REGIONS = {
    '11110':'종로구','11140':'중구','11170':'용산구','11200':'성동구','11215':'광진구',
    '11230':'동대문구','11260':'중랑구','11290':'성북구','11305':'강북구','11320':'도봉구',
    '11350':'노원구','11380':'은평구','11410':'서대문구','11440':'마포구','11470':'양천구',
    '11500':'강서구','11530':'구로구','11545':'금천구','11560':'영등포구','11590':'동작구',
    '11620':'관악구','11650':'서초구','11680':'강남구','11710':'송파구','11740':'강동구',
    '41135':'성남시 분당구','41117':'수원시 영통구','41480':'화성시','41273':'안산시 단원구',
    '41281':'고양시 덕양구','41411':'용인시 수지구','26350':'해운대구','27260':'수성구',
    '30200':'유성구','36110':'세종특별자치시'
}
PREFIX = {'11':'서울특별시','41':'경기도','26':'부산광역시','27':'대구광역시',
          '28':'인천광역시','29':'광주광역시','30':'대전광역시','36':'세종특별자치시'}

# 목표 데이터 기간
TARGET_START = '2020-01'        # 수집 시작년월 (YYYY-MM)

def smart_collect():
    """DB 내 전체 월 체크 → 빈 구간 포함 모두 수집"""
    from data.database import get_conn, save_apt_trades, save_apt_rents, init_db
    init_db()
    conn = get_conn()
    
    # DB에 존재하는 전체 월 리스트
    trade_months = set(r[0] for r in conn.execute(
        "SELECT DISTINCT substr(deal_date,1,7) FROM apt_trade WHERE deal_date IS NOT NULL"
    ).fetchall())
    rent_months = set(r[0] for r in conn.execute(
        "SELECT DISTINCT substr(deal_date,1,7) FROM apt_rent WHERE deal_date IS NOT NULL"
    ).fetchall())
    
    # 전체 범위: target_start ~ 현재월
    min_ym = TARGET_START
    conn.close()
    
    now = datetime.now()
    current_ym = f'{now.year}-{now.month:02d}'
    
    # 누락된 월 찾기 (min_ym ~ current_ym 중 DB에 없는 월)
    missing_months = []
    ym = min_ym
    while ym <= current_ym:
        if ym not in trade_months or ym not in rent_months:
            if ym not in missing_months:
                missing_months.append(ym)
        # next month
        y, m = int(ym[:4]), int(ym[5:7])
        m += 1
        if m > 12: y += 1; m = 1
        ym = f'{y}-{m:02d}'
    
    if not missing_months:
        return 0, "✅ 전체 월 데이터 완료"
    
    months_short = [m.replace('-','') for m in missing_months]
    print(f"  📡 대상 기간: {TARGET_START} ~ {current_ym} ({len(missing_months)}개월 누락)")
    print(f"  📡 누락 월: {missing_months[:10]}{'...' if len(missing_months)>10 else ''}")
    
    total = 0
    for code, name in REGIONS.items():
        prefix = PREFIX.get(code[:2], '')
        rname = f'{prefix} {name}' if prefix else name
        for ym in months_short:
            for url, label, save_fn in [(TRADE_URL, '매매', save_apt_trades), (RENT_URL, '전월세', save_apt_rents)]:
                try:
                    r = requests.get(url, params={
                        'serviceKey': KEY, 'LAWD_CD': code, 'DEAL_YMD': ym,
                        'pageNo': 1, 'numOfRows': '9999', '_type': 'json'
                    }, timeout=30)
                    if r.status_code == 200:
                        items = r.json()['response']['body'].get('items', {}).get('item', [])
                        if isinstance(items, dict): items = [items]
                        if items:
                            c = save_fn(pd.DataFrame(items), code, rname)
                            total += c if c else 0
                    time.sleep(0.15)
                except: pass
    
    msg = f"📡 {len(missing_months)}개월({missing_months}) 수집 완료: {total}건" if total else f"📭 수집 데이터 없음"
    return total, msg


def run_analysis():
    """분석 실행 + 결과 문자열 반환"""
    from strategy.recommender import RecommendationEngine, print_ranking
    import io
    from contextlib import redirect_stdout

    # Ranking
    buf = io.StringIO()
    with redirect_stdout(buf):
        print_ranking(10)
    ranking = buf.getvalue()
    
    # Score regions
    engine = RecommendationEngine()
    scores = {}
    for r in ['서울특별시 강남구','서울특별시 서초구','서울특별시 송파구','서울특별시 마포구','서울특별시 노원구','서울특별시 관악구']:
        try:
            sig = engine.score_region(r)
            factors = sig.get('factors', {})
            reasons = []
            for k, v in list(factors.items())[:4]:
                reasons.append(f"{k}: {v.get('value','')} ({v.get('score','')}점)")
            scores[r] = {'score': sig['total_score'], 'grade': sig['grade'], 'reasons': reasons}
        except Exception as e:
            scores[r] = {'score': 0, 'grade': '오류', 'reasons': [str(e)[:80]]}
    engine.close()
    
    return ranking, scores


def save_to_wiki(briefing_text, collect_msg):
    """위키에 브리핑 저장"""
    today = datetime.now().strftime('%Y-%m-%d')
    
    # 디렉토리 생성
    wiki_dir = os.path.expanduser('~/wiki/concepts/daily-briefing')
    os.makedirs(wiki_dir, exist_ok=True)
    
    page_path = os.path.join(wiki_dir, f'{today}.md')
    
    # 페이지 내용 (frontmatter + briefing + wikilinks)
    content = f"""---
title: 데일리 부동산 브리핑 ({today})
created: {today}
updated: {today}
type: concept
tags: [부동산, 데일리브리핑, 서울아파트, 매매분석]
sources: [국토교통부 실거래가 API]
confidence: medium
---

# 데일리 부동산 브리핑 ({today})

{briefing_text}

---

**참고 페이지:**
- [[real-estate-purchase-criteria]] — 매수 조건 종합 체크리스트
- [[gap-investment-strategy]] — 갭투자 전략
- [[site-inspection-checklist]] — 임장 체크리스트

*자동 생성 | 데이터 출처: 국토교통부 실거래가 API*
*업데이트: {datetime.now().strftime("%Y-%m-%d %H:%M")}*
"""
    
    with open(page_path, 'w') as f:
        f.write(content)
    
    # log.md 업데이트
    log_path = os.path.expanduser('~/wiki/log.md')
    log_entry = f"\n## [{today}] ingest | 데일리 부동산 브리핑\n- Created [[daily-briefing/{today}]]\n- {collect_msg}\n"
    with open(log_path, 'a') as f:
        f.write(log_entry)
    
    # index.md 업데이트 (중복 방지)
    index_path = os.path.expanduser('~/wiki/index.md')
    with open(index_path, 'r') as f:
        index_content = f.read()
    
    entry = f'- [[daily-briefing/{today}]] — 데일리 부동산 브리핑 ({today})\n'
    if entry not in index_content:
        # Concepts 섹션 찾아서 알파벳 순으로 삽입
        lines = index_content.split('\n')
        new_lines = []
        in_concepts = False
        inserted = False
        for i, line in enumerate(lines):
            if line.strip() == '## Concepts':
                in_concepts = True
                new_lines.append(line)
                continue
            if in_concepts:
                # 다음 섹션 시작 전까지
                if line.strip().startswith('## '):
                    # concept보다 먼저 삽입 (알파벳 순: d < m)
                    if not inserted:
                        new_lines.append(entry)
                        inserted = True
                    in_concepts = False
                    new_lines.append(line)
                elif i == len(lines) - 1:
                    new_lines.append(line)
                    if not inserted:
                        new_lines.append(entry)
                        inserted = True
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        
        # 만약 Concepts 섹션이 없거나 삽입 못했으면 맨 끝에 추가
        if not inserted:
            new_lines.append('\n' + entry)
        
        with open(index_path, 'w') as f:
            f.write('\n'.join(new_lines))
    else:
        print("  index.md 이미 최신")
    
    return page_path


def main():
    today = datetime.now().strftime('%Y-%m-%d')
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    
    print(f"🏠 부동산 데일리 업데이트 ({now_str})")
    print("=" * 50)
    
    external_msgs = []
    hg_count = 0
    kb_count = 0
    
    # Step 1A: MOLIT 데이터 수집
    print("\n[1A/5] MOLIT 실거래가 수집 중...")
    collected, collect_msg = smart_collect()
    print(f"  {collect_msg}")
    
    # Step 1B: KB부동산 데이터 수집 (PublicDataReader)
    print("\n[1B/5] KB부동산 데이터 수집 중...")
    try:
        from collectors.kb_price import collect_all_kb
        kb_count = collect_all_kb()
        external_msgs.append(f"KB {kb_count}건")
        print(f"  ✅ KB {kb_count}건 저장")
    except Exception as e:
        print(f"  ⚠️ KB 수집 실패: {e}")
        external_msgs.append("KB ⚠️")
    
    # Step 1C: 호갱노노 데이터 수집 (핵심 지역)
    print("\n[1C/5] 호갱노노 실거래가 수집 중...")
    try:
        from collectors.hogangnono import search_apts, get_apt_simple, get_room_types, get_monthly_reports, TRADE_TYPE_LABEL
        from data.database import get_conn
        
        # 핵심 단지 hash (서울 주요 5호선 + 기타)
        CORE_HASHES = [
            '18Hb3','18tc5','19wb4','18uc9','19k9a','19ta7',  # 강서 방화
            'eN41','eMb6','eYf8','ez9f',                       # 동대문
            '14k74','13E5c','eNYxL',                            # 화곡/강동
        ]
        conn = get_conn()
        cur = conn.cursor()
        hg_count = 0
        
        for apt_hash in CORE_HASHES:
            info = get_apt_simple(apt_hash)
            if not info:
                continue
            apt_name = info.get('name', '')
            
            # 단지 정보 저장
            cur.execute('''INSERT OR IGNORE INTO hogang_apts
                (apt_hash, apt_name, address, road_address, region_code, lat, lng, household, trade_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (apt_hash, apt_name, info.get('address',''), info.get('roadAddress',''),
                 info.get('regionCode',''), info.get('lat'), info.get('lng'), info.get('areaNo',0), 0))
            
            # 평형별 실거래가
            rts = get_room_types(apt_hash)
            for area_idx, rt in enumerate(rts[:3]):
                area_no = area_idx + 1
                rt_name = rt.get('zigbangRoomType', f'area{area_no}')
                for tt in [0, 1]:  # 매매, 전세
                    reports = get_monthly_reports(apt_hash, tt, area_no)
                    if not reports:
                        continue
                    for month in reports:
                        trade_date = (month.get('date','') or '')[:10].replace('T',' ')
                        for trade in month.get('trades', []):
                            price = trade.get('price') or month.get('averagePrice', 0)
                            if not price: continue
                            floor = trade.get('floor', 0)
                            day = trade.get('day', 1)
                            category = trade.get('category', tt + 1)
                            is_lower = 1 if trade.get('isLowerFloor') else 0
                            try:
                                dt = f"{trade_date[:7]}-{day:02d}" if trade_date and day else trade_date
                            except:
                                dt = trade_date
                            cur.execute('''INSERT OR IGNORE INTO hogang_trades
                                (apt_hash, apt_name, area_no, room_type, trade_type,
                                 trade_date, price, floor, category, is_lower_floor)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                                (apt_hash, apt_name, area_no, rt_name, tt, dt,
                                 int(price), floor, category, is_lower))
                            if cur.rowcount > 0:
                                hg_count += 1
            conn.commit()
        conn.close()
        external_msgs.append(f"호갱 {hg_count}건")
        print(f"  ✅ 호갱노노 {hg_count}건 저장")
    except Exception as e:
        print(f"  ⚠️ 호갱노노 수집 실패: {e}")
        external_msgs.append("호갱 ⚠️")
    
    # Step 2: 분석
    print("\n[2/5] 분석 실행 중...")
    ranking, scores = run_analysis()
    
    # Step 3: KB 브리핑 데이터
    print("\n[3/5] KB 시장 데이터 수집...")
    kb_brief = ""
    try:
        from collectors.kb_price import get_jeonse_rate, get_market_trend
        df_rate = get_jeonse_rate()
        df_trend = get_market_trend()
        if df_rate is not None:
            for code, name in [('1100000000','서울'),('1B0000','강남11'),('1A0000','강북14')]:
                rd = df_rate[df_rate['지역코드'].astype(str) == code]
                if not rd.empty:
                    last = rd.iloc[-1]
                    kb_brief += f"- KB 전세가율({name}): {last['전세가격비율']:.1f}%\n"
        if df_trend is not None:
            rd = df_trend[df_trend['지역코드'].astype(str) == '1100000000']
            if not rd.empty:
                last = rd.iloc[-1]
                kb_brief += f"- KB 매수우위지수(서울): {last['매수우위지수']:.1f}\n"
    except Exception as e:
        kb_brief = f"- KB 데이터 로딩 실패\n"
    
    # Step 4: 위키 저장
    print("\n[4/5] 위키 저장 중...")
    # 간단 브리핑 텍스트 구성
    briefing = []
    briefing.append(f"**📊 매매 추천 TOP 5**")
    for line in ranking.split('\n'):
        if any(r in line for r in ['강남','서초','송파','관악','마포','노원','동대문','강서','성북']):
            if '🔥' in line or '✅' in line or '➡️' in line or '⚠️' in line:
                briefing.append(line.strip())
    
    briefing.append(f"\n**📍 관심 지역 분석**")
    for region, data in scores.items():
        grade = data['grade']
        score = int(data['score']) if hasattr(data['score'], 'item') else data['score']
        briefing.append(f"- {region.replace('서울특별시','').strip()}: {score}점 ({grade})")
        for r in data['reasons'][:2]:
            briefing.append(f"  └ {r}")
    
    if kb_brief:
        briefing.append(f"\n**🏢 KB 시장 데이터**")
        briefing.append(kb_brief.strip())
    
    if external_msgs:
        briefing.append(f"\n**📦 외부 수집**")
        briefing.append(f"- {' / '.join(external_msgs)}")
    
    briefing_text = '\n'.join(briefing)
    
    page_path = save_to_wiki(briefing_text, collect_msg)
    print(f"  ✅ 위키 저장 완료: {page_path}")
    
    print(f"\\n{'=' * 50}")
    print(f"✅ 데일리 업데이트 완료!")
    print(f"  - MOLIT 수집: {collect_msg}")
    print(f"  - KB: {kb_count}건 / 호갱노노: {hg_count}건")
    print(f"  - 위키: concepts/daily-briefing/{today}.md")
    print(f"  - 분석: {len(scores)}개 지역")

if __name__ == '__main__':
    main()
