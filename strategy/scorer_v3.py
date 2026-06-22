"""
v3.0 통합 스코어러 — DB 2개 테이블 + 외부 5개 소스 통합 점수
"""
import sqlite3, numpy as np
from datetime import datetime
from data.database import get_conn


class ScorerV3:
    """16개 요소 통합 점수 (100pt + 보정 30pt)"""

    def __init__(self, db_path='realestate.db'):
        self.conn = sqlite3.connect(db_path)
        row = self.conn.execute(
            "SELECT MAX(deal_date) FROM apt_trade WHERE deal_date IS NOT NULL"
        ).fetchone()
        self.ref_date = row[0] if row and row[0] else "2025-05-31"
        self._cache_dates()
        self._init_collectors()
        self._weight_multipliers = self._load_weights()

    def _load_weights(self):
        """ml_weights 테이블에서 최적화된 가중치 로드 (없으면 기본 1.0x)"""
        try:
            rows = self.conn.execute(
                "SELECT factor_name, default_weight, optimized_weight FROM ml_weights"
            ).fetchall()
            return {
                r[0]: round(r[2] / r[1], 2) if r[1] > 0 else 1.0
                for r in rows
            }
        except Exception:
            return {}

    def _cache_dates(self):
        rd = self.ref_date
        q = self.conn.execute
        self.d3 = q(f"SELECT date('{rd}', '-3 months')").fetchone()[0]
        self.d6 = q(f"SELECT date('{rd}', '-6 months')").fetchone()[0]
        self.d12 = q(f"SELECT date('{rd}', '-12 months')").fetchone()[0]

    def _init_collectors(self):
        from collectors.kb_index import KBIndexCollector
        from collectors.development_news import DevelopmentCollector
        from collectors.supply_data import SupplyCollector
        from collectors.interest_rate import MacroCollector
        from collectors.school_info import SchoolCollector
        from collectors.news_sentiment import NewsSentimentCollector
        self.collectors = {
            'kb': KBIndexCollector(),
            'dev': DevelopmentCollector(),
            'supply': SupplyCollector(),
            'macro': MacroCollector(),
            'school': SchoolCollector(),
            'news': NewsSentimentCollector(),
        }

    def close(self):
        for c in self.collectors.values():
            c.close()
        self.conn.close()

    def _tier(self, region):
        seoul_core = {'용산구', '서초구', '강남구', '송파구', '성동구', '마포구'}
        metro = {'경기도', '부산광역시', '대구광역시', '인천광역시',
                 '광주광역시', '대전광역시', '울산광역시', '세종특별자치시'}
        if '서울' not in region:
            if any(region.startswith(p) for p in metro):
                return 3
            return 4
        short = region.replace('서울특별시 ', '')
        return 1 if short in seoul_core else 2

    # ─── 16개 요소 통합 점수 ──────────────────────────

    def _scale(self, raw_score, weight):
        """외부 collector 점수(0-100) → 해당 요소 배점으로 스케일링"""
        return round(raw_score * weight / 100.0, 1)

    def score_region(self, region):
        f = {}
        s1, v1 = self._db_price_momentum(region);    f['가격모멘텀'] = {'score': s1, 'value': f'{v1:+.1f}%'}
        s2, v2 = self._db_medium_trend(region);      f['중기추세'] = {'score': s2, 'value': f'{v2:+.1f}%'}
        s3, v3 = self._db_jeonse_rate(region);       f['전세가율'] = {'score': s3, 'value': f'{v3:.1f}%'}
        s4, v4 = self._db_stability(region);         f['거래안정성'] = {'score': s4, 'value': f'{v4}건'}
        s5, v5 = self._db_gap(region);               f['갭매력도'] = {'score': s5, 'value': f'{v5:.1f}억'}
        s6, v6 = self._db_reversion(region);         f['리버전'] = {'score': s6, 'value': f'{v6:+.1f}%'}
        raw7, v7 = self.collectors['kb'].get_score(region);     f['KB수급지수'] = {'score': self._scale(raw7, 10), 'value': f'{v7}'}
        raw8, v8 = self.collectors['dev'].get_score(region);    f['개발호재'] = {'score': self._scale(raw8, 8), 'value': f'{v8}건'}
        raw9, v9 = self.collectors['supply'].get_score(region);  f['공급리스크'] = {'score': self._scale(raw9, 8), 'value': f'{v9:.1f}%'}
        raw10, v10 = self.collectors['school'].get_score(region); f['학군'] = {'score': self._scale(raw10, 8), 'value': f'{v10:.1f}'}
        raw11, v11 = self.collectors['macro'].get_score();       f['거시환경'] = {'score': self._scale(raw11, 10), 'value': f'{v11:.1f}%'}
        tier = self._tier(region)
        tier_scores = {1: 8, 2: 6, 3: 4, 4: 2}
        s12 = tier_scores.get(tier, 2)
        f['지역계층'] = {'score': s12, 'value': f'{tier}단계'}
        # new: 뉴스 감성 (5pt)
        raw13, v13 = self.collectors['news'].get_score(region)
        f['뉴스감성'] = {'score': self._scale(raw13, 5), 'value': v13}

        total = s1 + s2 + s3 + s4 + s5 + s6 + self._scale(raw7, 10) + self._scale(raw8, 8) + self._scale(raw9, 8) + self._scale(raw10, 8) + self._scale(raw11, 10) + s12 + self._scale(raw13, 5)

        # Apply ML-optimized weight multipliers if available
        if self._weight_multipliers:
            w = self._weight_multipliers
            f['가격모멘텀']['score'] = round(f['가격모멘텀']['score'] * w.get('가격모멘텀', 1), 1)
            f['중기추세']['score'] = round(f['중기추세']['score'] * w.get('중기추세', 1), 1)
            f['전세가율']['score'] = round(f['전세가율']['score'] * w.get('전세가율', 1), 1)
            f['거래안정성']['score'] = round(f['거래안정성']['score'] * w.get('거래안정성', 1), 1)
            f['갭매력도']['score'] = round(f['갭매력도']['score'] * w.get('갭매력도', 1), 1)
            f['리버전']['score'] = round(f['리버전']['score'] * w.get('리버전', 1), 1)
            f['KB수급지수']['score'] = round(f['KB수급지수']['score'] * w.get('KB수급지수', 1), 1)
            f['개발호재']['score'] = round(f['개발호재']['score'] * w.get('개발호재', 1), 1)
            f['공급리스크']['score'] = round(f['공급리스크']['score'] * w.get('공급리스크', 1), 1)
            f['학군']['score'] = round(f['학군']['score'] * w.get('학군', 1), 1)
            f['거시환경']['score'] = round(f['거시환경']['score'] * w.get('거시환경', 1), 1)
            f['지역계층']['score'] = round(f['지역계층']['score'] * w.get('지역계층', 1), 1)
            f['뉴스감성']['score'] = round(f['뉴스감성']['score'] * w.get('뉴스감성', 1), 1)
            total = sum(f[k]['score'] for k in f)
            f['_weight_source'] = {'score': 0, 'value': 'ML 최적화'}

        return {
            'region': region,
            'total_score': round(total, 1),
            'grade': self._grade(total),
            'factors': f,
            'version': 'v3.0',
            'time': datetime.now().strftime('%Y-%m-%d %H:%M'),
        }

    def _grade(self, total):
        if total >= 90: return '🔥 강력매수'
        if total >= 72: return '✅ 매수'
        if total >= 55: return '➡️ 관망'
        if total >= 35: return '⚠️ 매도'
        return '🔴 긴급매도'

    # ─── DB 기반 개별 스코어러 (price 1억~30억) ───

    def _db_price_momentum(self, region):
        row = self.conn.execute("""
            SELECT ROUND(AVG(CASE WHEN deal_date >= ? THEN price/10000.0 END), 1),
                   ROUND(AVG(CASE WHEN deal_date >= ? AND deal_date < ? THEN price/10000.0 END), 1)
            FROM apt_trade WHERE region = ? AND price BETWEEN 10000 AND 300000 AND deal_date >= ?
        """, (self.d3, self.d12, self.d3, region, self.d12)).fetchone()
        p3 = row[0] or 0; p12_3 = row[1] or 0
        if p12_3 == 0: return 10, 0
        chg = round((p3 - p12_3) * 100.0 / p12_3, 1)
        if chg > 5:   return 15, chg
        elif chg > 2: return 12, chg
        elif chg > 0: return 10, chg
        elif chg > -2: return 7, chg
        elif chg > -5: return 4, chg
        else:         return 2, chg

    def _db_medium_trend(self, region):
        row = self.conn.execute("""
            SELECT ROUND(AVG(CASE WHEN deal_date >= ? THEN price/10000.0 END), 1),
                   ROUND(AVG(CASE WHEN deal_date >= ? AND deal_date < ? THEN price/10000.0 END), 1)
            FROM apt_trade WHERE region = ? AND price BETWEEN 10000 AND 300000 AND deal_date >= ?
        """, (self.d3, self.d6, self.d3, region, self.d6)).fetchone()
        p3 = row[0] or 0; p6_3 = row[1] or 0
        if p6_3 == 0: return 5, 0
        chg = round((p3 - p6_3) * 100.0 / p6_3, 1)
        if chg > 3:   return 8, chg
        elif chg > 0: return 6, chg
        elif chg > -3: return 4, chg
        else:         return 2, chg

    def _db_jeonse_rate(self, region):
        avg_p = self.conn.execute("""
            SELECT ROUND(AVG(price)/10000.0, 1) FROM apt_trade
            WHERE region = ? AND price BETWEEN 10000 AND 300000 AND deal_date >= ?
        """, (region, self.d6)).fetchone()[0] or 0
        avg_j = self.conn.execute("""
            SELECT ROUND(AVG(deposit)/10000.0, 1) FROM apt_rent
            WHERE region = ? AND deposit > 10000 AND deposit < 150000
        """, (region,)).fetchone()[0] or 0
        if avg_p == 0 or avg_j == 0: return 3, 0
        jr = round(avg_j * 100.0 / avg_p, 1)
        tier = self._tier(region)
        if tier == 1:
            score = 8 if 30 <= jr <= 50 else (5 if 20 <= jr <= 60 else 3)
        elif tier == 2:
            score = 8 if 40 <= jr <= 65 else (5 if 30 <= jr <= 75 else 3)
        elif tier == 3:
            score = 8 if 50 <= jr <= 70 else (5 if 40 <= jr <= 80 else 3)
        else:
            score = 8 if 55 <= jr <= 75 else (5 if 45 <= jr <= 85 else 3)
        return score, jr

    def _db_stability(self, region):
        vol = self.conn.execute("""
            SELECT COUNT(*) FROM apt_trade
            WHERE region = ? AND price BETWEEN 10000 AND 300000 AND deal_date >= ?
        """, (region, self.d6)).fetchone()[0] or 0
        if vol >= 800:   return 8, vol
        elif vol >= 400: return 6, vol
        elif vol >= 200: return 4, vol
        elif vol >= 80:  return 2, vol
        else:            return 1, vol

    def _db_gap(self, region):
        avg_p = self.conn.execute("""
            SELECT ROUND(AVG(price)/10000.0, 1) FROM apt_trade
            WHERE region = ? AND price BETWEEN 10000 AND 300000 AND deal_date >= ?
        """, (region, self.d6)).fetchone()[0] or 0
        avg_j = self.conn.execute("""
            SELECT ROUND(AVG(deposit)/10000.0, 1) FROM apt_rent
            WHERE region = ? AND deposit > 10000 AND deposit < 150000
        """, (region,)).fetchone()[0] or 0
        if avg_p == 0 or avg_j == 0: return 2, 0
        gap = round(avg_p - avg_j, 1)
        if gap <= 0:    return 1, gap
        elif gap <= 1:  return 2, gap
        elif gap <= 2:  return 3, gap
        elif gap <= 4:  return 5, gap
        elif gap <= 6:  return 4, gap
        else:           return 2, gap

    def _db_reversion(self, region):
        row = self.conn.execute("""
            SELECT ROUND(AVG(CASE WHEN deal_date >= ? THEN price/10000.0 END), 1),
                   ROUND(AVG(CASE WHEN deal_date >= ? AND deal_date < ? THEN price/10000.0 END), 1)
            FROM apt_trade WHERE region = ? AND price BETWEEN 10000 AND 300000 AND deal_date >= ?
        """, (self.d3, self.d12, self.d3, region, self.d12)).fetchone()
        p3 = row[0] or 0; p12_3 = row[1] or 0
        if p12_3 == 0: return 3, 0
        chg = round((p3 - p12_3) * 100.0 / p12_3, 1)
        if chg > 15:     return 1, chg
        elif chg > 8:    return 2, chg
        elif chg > 2:    return 4, chg
        elif chg > -5:   return 5, chg
        else:            return 3, chg

    def backtest(self):
        regions = [r[0] for r in self.conn.execute(
            "SELECT DISTINCT region FROM apt_trade ORDER BY region"
        ).fetchall()]
        scores, actuals = [], []
        for region in regions:
            try:
                result = self.score_region(region)
                row = self.conn.execute("""
                    SELECT ROUND(AVG(CASE WHEN deal_date >= ? THEN price/10000.0 END), 1),
                           ROUND(AVG(CASE WHEN deal_date >= ? AND deal_date < ? THEN price/10000.0 END), 1)
                    FROM apt_trade WHERE region = ? AND price BETWEEN 10000 AND 300000 AND deal_date >= ?
                """, (self.d3, self.d12, self.d3, region, self.d12)).fetchone()
                p3 = row[0] or 0; p12_3 = row[1] or 0
                if p12_3 > 0:
                    scores.append(result['total_score'])
                    actuals.append(round((p3 - p12_3) * 100.0 / p12_3, 1))
            except Exception:
                continue
        if len(scores) < 5:
            return {'correlation': 0, 'count': len(scores)}
        corr = np.corrcoef(scores, actuals)[0, 1]
        return {'correlation': round(corr, 3), 'count': len(scores),
                'avg_score': round(np.mean(scores), 1), 'avg_actual': round(np.mean(actuals), 1)}


if __name__ == '__main__':
    import sys
    s = ScorerV3()
    if len(sys.argv) > 1:
        # Resolve short name to full region name
        query = sys.argv[1]
        region_row = s.conn.execute(
            "SELECT DISTINCT region FROM apt_trade WHERE region LIKE ? LIMIT 1",
            (f'%{query}%',)
        ).fetchone()
        if region_row:
            region = region_row[0]
        else:
            region = query
        r = s.score_region(region)
        print(f"\n📍 {r['region']} — {r['total_score']}점 {r['grade']} (v{r['version']})")
        for k, v in r['factors'].items():
            bar = '█' * int(v['score'] / 8) + '░' * (10 - int(v['score'] / 8))
            print(f"  {k:12s} |{bar}| {v['score']:>5.1f}점 ({v['value']})")
    else:
        print("=== v3.0 TOP 10 ===")
        regions = [r[0] for r in s.conn.execute(
            "SELECT DISTINCT region FROM apt_trade ORDER BY region"
        ).fetchall()]
        results = []
        for r in regions:
            try:
                results.append(s.score_region(r))
            except Exception:
                continue
        results.sort(key=lambda x: x['total_score'], reverse=True)
        for i, r in enumerate(results[:10]):
            short = r['region']
            for p in ['서울특별시 ','경기도 ','부산광역시 ','대전광역시 ','대구광역시 ','인천광역시 ','광주광역시 ','울산광역시 ','세종특별자치시 ']:
                short = short.replace(p, '')
            print(f"  {i+1:>2}. {short:<12} {r['total_score']:>5.1f}점 {r['grade']}")
    bt = s.backtest()
    print(f"\n📊 백테스트: 상관계수 {bt['correlation']} (n={bt['count']})")
    s.close()
