"""
매매 추천 시스템 — 지역별/단지별 Buy/Sell 순위 엔진

8개 요소를 종합 점수화(0-100)하여 매수 추천 지역/단지 순위 제공
"""
import pandas as pd
import numpy as np
from datetime import datetime
from data.database import get_conn


class RecommendationEngine:
    """매매 추천 엔진"""

    # 가중치 설정 (합계 100)
    WEIGHTS = {
        "jeonse_rate": 20,      # 전세가율 (낮을수록 좋음)
        "volume_momentum": 15,  # 거래량 모멘텀
        "price_trend": 20,      # 가격 추세
        "gap_size": 10,         # 갭 크기 (매매-전세)
        "trade_stability": 10,  # 거래 안정성 (최근 거래일)
        "seasonal_boost": 10,   # 계절성 보정
        "diversity": 5,        # 단지 분산도
        "pyung_value": 10,     # 평당가 매력도
    }

    def __init__(self):
        self.conn = get_conn()
        # DB 내 최신 거래일 기준 (MOLIT API 다운으로 date('now') 사용 불가)
        row = self.conn.execute(
            "SELECT MAX(deal_date) FROM apt_trade WHERE deal_date IS NOT NULL"
        ).fetchone()
        self.ref_date = row[0] if row and row[0] else "2025-05-31"
        # 기준일 기반 상대 날짜들 미리 계산
        self._cache_dates()

    def _cache_dates(self):
        """ref_date 기준 상대일 캐싱"""
        rd = self.ref_date
        q = self.conn.execute
        self.d6 = q(f"SELECT date('{rd}', '-6 months')").fetchone()[0]
        self.d3 = q(f"SELECT date('{rd}', '-3 months')").fetchone()[0]
        self.d12 = q(f"SELECT date('{rd}', '-12 months')").fetchone()[0]
        self.d24 = q(f"SELECT date('{rd}', '-24 months')").fetchone()[0]
        self.d6_to_3_start = q(f"SELECT date('{rd}', '-6 months')").fetchone()[0]
        self.d6_to_3_end = q(f"SELECT date('{rd}', '-3 months')").fetchone()[0]

    def close(self):
        if self.conn:
            self.conn.close()

    # ─── 헬퍼 ──────────────────────────────────────

    def _apt_filter(self, table='t', apt_name=None):
        """단지명 필터 SQL + 파라미터"""
        if apt_name:
            return f"AND {table}.apt_name = ?", [apt_name]
        return "", []

    def _grade(self, total):
        if total >= 80:  return '🔥 강력매수'
        if total >= 65:  return '✅ 매수'
        if total >= 50:  return '➡️ 관망'
        if total >= 35:  return '⚠️ 매도'
        return '🔴 긴급매도'

    # ─── 개별 요소 점수 ──────────────────────────────

    def score_jeonse_rate(self, region, apt_name=None):
        """전세가율 점수 (0-100, 낮을수록 고득점)"""
        if apt_name:
            q = """SELECT COALESCE(AVG(r.deposit * 100.0 / NULLIF(t.price, 0)), 0) as rate
            FROM apt_trade t JOIN apt_rent r ON t.apt_name = r.apt_name AND ABS(t.area - r.area) < 5
            WHERE t.region LIKE ? AND t.deal_date >= ? AND r.deal_date >= ?
              AND t.apt_name = ?"""
            rate = pd.read_sql_query(q, self.conn, params=[f'%{region}%', self.d6, self.d6, apt_name]).iloc[0, 0]
        else:
            q = """SELECT COALESCE(AVG(r.deposit * 100.0 / NULLIF(t.price, 0)), 0) as rate
            FROM apt_trade t JOIN apt_rent r ON t.apt_name = r.apt_name AND ABS(t.area - r.area) < 5
            WHERE t.region LIKE ? AND t.deal_date >= ? AND r.deal_date >= ?"""
            rate = pd.read_sql_query(q, self.conn, params=[f'%{region}%', self.d6, self.d6]).iloc[0, 0]
        if rate == 0:
            return 50, 0
        score = max(0, min(100, 100 - (rate - 30) * 2))
        return round(score, 1), round(rate, 1)

    def score_volume_momentum(self, region, apt_name=None):
        """거래량 모멘텀 (0-100)"""
        af, ap = self._apt_filter('apt_trade', apt_name)
        q = f"""SELECT
          SUM(CASE WHEN deal_date >= ? THEN 1 ELSE 0 END) as recent,
          SUM(CASE WHEN deal_date >= ? AND deal_date < ? THEN 1 ELSE 0 END) as prev
          FROM apt_trade WHERE region LIKE ? {af}"""
        row = pd.read_sql_query(q, self.conn, params=[self.d3, self.d6, self.d3, f'%{region}%'] + ap).iloc[0]
        recent, prev = int(row['recent'] or 0), int(row['prev'] or 0)
        if prev == 0:
            return 60, 0, 0
        change_pct = (recent - prev) / prev * 100
        score = max(0, min(100, 50 + change_pct))
        return round(score, 1), round(change_pct, 1), recent

    def score_price_trend(self, region, apt_name=None):
        """가격 추세 (0-100, 안정적 상승 + 과열 아님)"""
        af, ap = self._apt_filter('apt_trade', apt_name)
        q = f"SELECT strftime('%Y-%m', deal_date) as month, ROUND(AVG(price), 0) as avg_p FROM apt_trade WHERE region LIKE ? AND deal_date >= ? {af} GROUP BY month ORDER BY month"
        df = pd.read_sql_query(q, self.conn, params=[f'%{region}%', self.d6] + ap)
        if len(df) < 2:
            return 50, 0, 0
        p1 = df['avg_p'].iloc[0]; p2 = df['avg_p'].iloc[-1]
        change_pct = (p2 - p1) / p1 * 100 if p1 > 0 else 0
        if change_pct > 20:      score = max(0, 100 - (change_pct - 20) * 5)
        elif change_pct > 5:     score = 80
        elif change_pct > 0:     score = 70
        elif change_pct > -5:    score = 50
        else:                    score = max(0, 50 + change_pct * 2)
        return round(score, 1), round(change_pct, 1), int(p2)

    def score_gap_size(self, region, apt_name=None):
        """갭 크기 점수 (0-100, 갭이 적절히 클수록 좋음)"""
        af, ap = self._apt_filter('t', apt_name)
        q = f"""SELECT ROUND(AVG(t.price), 0) as avg_price, ROUND(AVG(r.deposit), 0) as avg_deposit
          FROM apt_trade t JOIN apt_rent r ON t.apt_name = r.apt_name AND ABS(t.area - r.area) < 5
          WHERE t.region LIKE ? AND t.deal_date >= ? AND r.deal_date >= ? {af}"""
        params = [f'%{region}%', self.d6, self.d6] + ap
        row = pd.read_sql_query(q, self.conn, params=params).iloc[0]
        avg_price = row['avg_price'] or 0
        avg_deposit = row['avg_deposit'] or 0
        gap = avg_price - avg_deposit
        if avg_price == 0:
            return 50, 0, 0
        gap_ratio = gap / avg_price * 100
        if 10 <= gap_ratio <= 30:   score = 90
        elif gap_ratio < 5:         score = 30
        elif gap_ratio < 10:        score = 60
        elif gap_ratio <= 40:       score = 70
        else:                       score = 40
        return round(score, 1), int(gap), round(gap_ratio, 1)

    def score_trade_stability(self, region, apt_name=None):
        """거래 안정성 (0-100, 최근 거래일이 가까울수록 좋음)"""
        af, ap = self._apt_filter('apt_trade', apt_name)
        q = f"""SELECT MAX(deal_date) as last_trade, COUNT(*) as trade_count
          FROM apt_trade WHERE region LIKE ? AND deal_date >= ? {af}"""
        row = pd.read_sql_query(q, self.conn, params=[f'%{region}%', self.d12] + ap).iloc[0]
        last_trade = row['last_trade']; trade_count = int(row['trade_count'] or 0)
        if not last_trade:
            return 0, 0, 0
        ref = datetime.strptime(self.ref_date, '%Y-%m-%d')
        last = datetime.strptime(last_trade, '%Y-%m-%d')
        days_since = (ref - last).days
        if days_since <= 30:       stability_score = 100
        elif days_since <= 90:     stability_score = 80
        elif days_since <= 180:    stability_score = 50
        else:                      stability_score = max(0, 50 - (days_since - 180) * 0.3)
        return round(stability_score, 1), days_since, trade_count

    def score_seasonal(self, region, apt_name=None):
        """계절성 보정 (0-100)"""
        ref_month = datetime.strptime(self.ref_date, '%Y-%m-%d').month
        af, ap = self._apt_filter('apt_trade', apt_name)
        q = f"SELECT CAST(strftime('%m', deal_date) AS INTEGER) as m, COUNT(*) as cnt FROM apt_trade WHERE region LIKE ? AND deal_date >= ? {af} GROUP BY m"
        df = pd.read_sql_query(q, self.conn, params=[f'%{region}%', self.d24] + ap)
        if df.empty:
            return 50, 0
        max_cnt = df['cnt'].max()
        row = df[df['m'] == ref_month]
        current_cnt = row['cnt'].iloc[0] if not row.empty else 0
        ratio = current_cnt / max_cnt if max_cnt > 0 else 0.5
        return round(ratio * 100, 1), round(ratio * 100, 1)

    def score_diversity(self, region, apt_name=None):
        """단지 분산도 (0-100) — 단지 수준은 항상 100"""
        if apt_name:
            return 100, 1, 0
        q = "SELECT COUNT(DISTINCT apt_name) as apt_count, COUNT(*) as total_trades FROM apt_trade WHERE region LIKE ? AND deal_date >= ?"
        row = pd.read_sql_query(q, self.conn, params=[f'%{region}%', self.d6]).iloc[0]
        apt_count = int(row['apt_count'] or 0); total = int(row['total_trades'] or 0)
        if apt_count == 0:
            return 30, 0, 0
        density = total / apt_count
        if apt_count >= 20:      ds = 100
        elif apt_count >= 10:    ds = 80
        elif apt_count >= 5:     ds = 60
        else:                    ds = 30
        if density > 50:         ds *= 0.7
        elif density > 20:       ds *= 0.9
        return round(ds, 1), apt_count, round(density, 1)

    def score_pyung_value(self, region, apt_name=None):
        """평당가 매력도 (0-100)"""
        af, ap = self._apt_filter('apt_trade', apt_name)
        q = f"SELECT ROUND(AVG(price / NULLIF(area, 0) * 3.3), 0) as avg_pyung, COUNT(*) as cnt FROM apt_trade WHERE region LIKE ? AND deal_date >= ? {af}"
        row = pd.read_sql_query(q, self.conn, params=[f'%{region}%', self.d6] + ap).iloc[0]
        avg_pyung = row['avg_pyung'] or 0
        if avg_pyung == 0:
            return 50, 0
        sido = region[:2]
        q2 = "SELECT ROUND(AVG(price / NULLIF(area, 0) * 3.3), 0) as sido_avg_pyung FROM apt_trade WHERE region LIKE ? AND deal_date >= ?"
        sido_row = pd.read_sql_query(q2, self.conn, params=[f'{sido}%', self.d6]).iloc[0]
        sido_avg = sido_row['sido_avg_pyung'] or avg_pyung
        ratio = avg_pyung / sido_avg * 100 if sido_avg > 0 else 100
        if ratio <= 80:    score = 100
        elif ratio <= 100: score = 100 - (ratio - 80) * 2
        elif ratio <= 120: score = max(0, 60 - (ratio - 100) * 2)
        else:              score = 20
        return round(score, 1), int(avg_pyung)

    # ─── 지역 종합 점수 ──────────────────────────────

    def score_region(self, region):
        """지역 종합 점수 계산"""
        f = {}
        s1, v1 = self.score_jeonse_rate(region);          f['전세가율'] = {'score': s1, 'value': f'{v1}%'}
        s2, v2, v2b = self.score_volume_momentum(region);  f['거래량모멘텀'] = {'score': s2, 'value': f'{v2:+.1f}% ({v2b}건)'}
        s3, v3, v3b = self.score_price_trend(region);      f['가격추세'] = {'score': s3, 'value': f'{v3:+.1f}% → {v3b//10000}억'}
        s4, v4, v4b = self.score_gap_size(region);         f['갭크기'] = {'score': s4, 'value': f'{v4//10000}억 (갭비율 {v4b}%)'}
        s5, v5, v5b = self.score_trade_stability(region);  f['거래안정성'] = {'score': s5, 'value': f'{v5}일 전 / 연 {v5b}건'}
        s6, v6 = self.score_seasonal(region);               f['계절성'] = {'score': s6, 'value': f'성수기지수 {v6}%'}
        s7, v7, v7b = self.score_diversity(region);         f['단지분산도'] = {'score': s7, 'value': f'{v7}개 단지 (집중도 {v7b})'}
        s8, v8 = self.score_pyung_value(region);            f['평당가매력'] = {'score': s8, 'value': f'평균 {v8}만원/평'}
        sm = {'jeonse_rate': s1, 'volume_momentum': s2, 'price_trend': s3,
              'gap_size': s4, 'trade_stability': s5, 'seasonal_boost': s6,
              'diversity': s7, 'pyung_value': s8}
        total = sum(sm[k] * (self.WEIGHTS[k] / 100.0) for k in self.WEIGHTS)
        return {'region': region, 'total_score': round(total, 1),
                'grade': self._grade(total), 'factors': f,
                'time': datetime.now().strftime('%Y-%m-%d %H:%M')}

    # ══════════════════════════════════════════════════
    # Phase 1: 단지 단위 추천
    # ══════════════════════════════════════════════════

    def score_apt(self, apt_name, region):
        """단지별 8개 요소 종합 점수"""
        f = {}
        s1, v1 = self.score_jeonse_rate(region, apt_name);         f['전세가율'] = {'score': s1, 'value': f'{v1}%'}
        s2, v2, v2b = self.score_volume_momentum(region, apt_name); f['거래량모멘텀'] = {'score': s2, 'value': f'{v2:+.1f}% ({v2b}건)'}
        s3, v3, v3b = self.score_price_trend(region, apt_name);     f['가격추세'] = {'score': s3, 'value': f'{v3:+.1f}% → {v3b//10000}억'}
        s4, v4, v4b = self.score_gap_size(region, apt_name);        f['갭크기'] = {'score': s4, 'value': f'{v4//10000}억 (갭비율 {v4b}%)'}
        s5, v5, v5b = self.score_trade_stability(region, apt_name); f['거래안정성'] = {'score': s5, 'value': f'{v5}일 전 / 연 {v5b}건'}
        s6, v6 = self.score_seasonal(region, apt_name);              f['계절성'] = {'score': s6, 'value': f'성수기지수 {v6}%'}
        s7, v7, v7b = self.score_diversity(region, apt_name);        f['단지분산도'] = {'score': s7, 'value': f'{v7}개 단지'}
        s8, v8 = self.score_pyung_value(region, apt_name);           f['평당가매력'] = {'score': s8, 'value': f'평균 {v8}만원/평'}

        sm = {'jeonse_rate': s1, 'volume_momentum': s2, 'price_trend': s3,
              'gap_size': s4, 'trade_stability': s5, 'seasonal_boost': s6,
              'diversity': s7, 'pyung_value': s8}
        total = sum(sm[k] * (self.WEIGHTS[k] / 100.0) for k in self.WEIGHTS)
        return {'apt_name': apt_name, 'region': region,
                'total_score': round(total, 1), 'grade': self._grade(total),
                'factors': f, 'time': datetime.now().strftime('%Y-%m-%d %H:%M')}

    def list_apts(self, region, min_trades=3):
        """지역 내 분석 가능한 단지 목록"""
        q = """SELECT apt_name, COUNT(*) as cnt FROM apt_trade
               WHERE region LIKE ? AND deal_date >= ?
               GROUP BY apt_name HAVING cnt >= ? ORDER BY cnt DESC"""
        df = pd.read_sql_query(q, self.conn, params=[f'%{region}%', self.d12, min_trades])
        return df['apt_name'].tolist()

    def rank_apts(self, region, limit=20, min_trades=3, sort_by='total_score'):
        """단지 순위표"""
        apts = self.list_apts(region, min_trades)
        results = []
        for apt in apts:
            try:
                r = self.score_apt(apt, region)
                results.append(r)
            except Exception:
                continue
        results.sort(key=lambda x: x[sort_by], reverse=True)
        df = pd.DataFrame([{
            '순위': i + 1, '단지명': r['apt_name'],
            '종합점수': r['total_score'], '등급': r['grade'],
            '전세가율': r['factors']['전세가율']['value'],
            '가격추세': r['factors']['가격추세']['value'],
            '거래량': r['factors']['거래량모멘텀']['value'],
            '갭크기': r['factors']['갭크기']['value'],
        } for i, r in enumerate(results[:limit])])
        return df

    def find_best_apts(self, region, top_n=10, min_trades=3):
        """매수 추천 단지 TOP N"""
        df = self.rank_apts(region, limit=50, min_trades=min_trades)
        filtered = df[df['종합점수'] >= 60].head(top_n)
        return filtered

    def find_sell_apt_alerts(self, region, top_n=10, min_trades=3):
        """매도 경보 단지 TOP N"""
        df = self.rank_apts(region, limit=50, min_trades=min_trades)
        filtered = df[df['종합점수'] < 40].head(top_n)
        return filtered

    def search_apts(self, keyword, limit=20):
        """단지명 검색"""
        q = "SELECT DISTINCT apt_name, region, COUNT(*) as cnt FROM apt_trade WHERE apt_name LIKE ? GROUP BY apt_name ORDER BY cnt DESC LIMIT ?"
        df = pd.read_sql_query(q, self.conn, params=[f'%{keyword}%', limit])
        return df

    # ─── 지역 순위 ──────────────────────────────────

    def rank_regions(self, regions=None, limit=20):
        """전체/선택 지역 순위표"""
        if isinstance(limit, float):
            limit = int(limit)
        if not regions:
            df = pd.read_sql_query(
                "SELECT DISTINCT region FROM apt_trade ORDER BY region", self.conn
            )
            regions = df['region'].tolist()

        results = []
        for r in regions:
            try:
                result = self.score_region(r)
                results.append(result)
            except Exception:
                continue
        results.sort(key=lambda x: x['total_score'], reverse=True)
        results = results[:limit]

        df_result = pd.DataFrame([{
            '순위': i + 1,
            '지역': r['region'].replace('서울특별시 ', '').replace('경기도 ', '').replace('부산광역시 ', ''),
            '종합점수': r['total_score'],
            '등급': r['grade'],
            '전세가율': r['factors']['전세가율']['value'],
            '가격추세': r['factors']['가격추세']['value'],
            '거래량': r['factors']['거래량모멘텀']['value'],
            '갭크기': r['factors']['갭크기']['value'],
            '평당가': r['factors']['평당가매력']['value'],
        } for i, r in enumerate(results)])
        return df_result

    def find_best_deals(self, top_n=10):
        """최고 매수 추천 지역"""
        df = self.rank_regions(limit=50)
        filtered = df[df['종합점수'] >= 60].head(top_n)
        return filtered

    def find_sell_alerts(self, top_n=10):
        """매도 경보 지역"""
        df = self.rank_regions(limit=50)
        filtered = df[df['종합점수'] < 40].head(top_n)
        return filtered


def print_recommendation(region):
    """CLI용 추천 출력"""
    engine = RecommendationEngine()
    result = engine.score_region(region)
    engine.close()
    print(f"\n{'='*50}")
    print(f"📍 {result['region']}")
    print(f"📊 종합점수: {result['total_score']}/100  |  등급: {result['grade']}")
    print(f"🕐 {result['time']}")
    print(f"{'='*50}")
    for name, data in result['factors'].items():
        bar_len = int(data['score'] / 10)
        bar = '█' * bar_len + '░' * (10 - bar_len)
        print(f"  {name:8s} |{bar}| {data['score']:.1f}점 ({data['value']})")
    print()
    return result


def print_ranking(limit=20):
    """CLI용 지역 순위표 출력"""
    engine = RecommendationEngine()
    df = engine.rank_regions(limit=limit)
    engine.close()
    print(f"\n{'='*80}")
    print(f"🏆 매매 추천 지역 순위")
    print(f"{'='*80}")
    print(df.to_string(index=False))
    print(f"\n🔥 강력매수: 80↑  ✅ 매수: 65↑  ➡️ 관망: 50↑  ⚠️ 매도: 35↑  🔴 긴급매도: 35↓")
    return df


def print_apt_ranking(region, limit=20):
    """CLI용 단지 순위표 출력"""
    engine = RecommendationEngine()
    df = engine.rank_apts(region, limit=limit)
    engine.close()
    print(f"\n{'='*80}")
    print(f"🏆 {region} 단지별 추천 순위")
    print(f"{'='*80}")
    if df.empty:
        print("   데이터 부족으로 단지 순위를 생성할 수 없습니다.")
    else:
        print(df.to_string(index=False))
        print(f"\n🔥 강력매수: 80↑  ✅ 매수: 65↑  ➡️ 관망: 50↑  ⚠️ 매도: 35↑  🔴 긴급매도: 35↓")
    return df


def rank_by_budget(budget_ok=5):
    """예산 기반 매수 추천"""
    engine = RecommendationEngine()
    conn = engine.conn
    q = """
    SELECT region, ROUND(AVG(price), 0) as avg_price,
           ROUND(AVG(area), 1) as avg_area, COUNT(*) as cnt
    FROM apt_trade WHERE deal_date >= ?
    GROUP BY region HAVING avg_price BETWEEN ? AND ?
    ORDER BY cnt DESC
    """
    low = (budget_ok - 1) * 10000
    high = budget_ok * 10000
    df = pd.read_sql_query(q, conn, params=[engine.d6, low, high])
    if df.empty:
        engine.close()
        return pd.DataFrame()

    scores = []
    for _, row in df.iterrows():
        try:
            result = engine.score_region(row['region'])
            scores.append({
                '지역': row['region'].replace('서울특별시 ', ''),
                '평균가(억)': f"{row['avg_price']/10000:.1f}",
                '평균면적': f"{row['avg_area']:.0f}m²",
                '거래건수': int(row['cnt']),
                '추천점수': result['total_score'],
                '등급': result['grade'],
            })
        except Exception:
            continue

    engine.close()
    df_result = pd.DataFrame(scores)
    if not df_result.empty:
        df_result = df_result.sort_values('추천점수', ascending=False).reset_index(drop=True)
        df_result.index = df_result.index + 1
        df_result.index.name = '순위'
    return df_result


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 2 and sys.argv[1] == 'apt':
        print_apt_ranking(sys.argv[2])
    elif len(sys.argv) > 1 and sys.argv[1] == 'rank':
        print_ranking()
    elif len(sys.argv) > 1:
        print_recommendation(sys.argv[1])
    else:
        print_recommendation('서울특별시 강남구')
        print_ranking(10)
