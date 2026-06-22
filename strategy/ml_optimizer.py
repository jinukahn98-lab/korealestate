"""
v3.0 ML 가중치 최적화기 — ScorerV3의 12개 요소 가중치를 최적화

Scipy나 sklearn이 없어도 numpy + sqlite3 + brute-force grid search로 동작.
"""
import sqlite3
import numpy as np
from itertools import product
from datetime import datetime


class MLOptimizer:
    """
    ScorerV3의 가중치를 최적화하는 클래스.

    sklearn/scipy가 없어도 numpy + brute-force grid search로 동작 가능.
    """

    FACTOR_NAMES = [
        '가격모멘텀', '중기추세', '전세가율', '거래안정성', '갭매력도',
        '리버전', 'KB수급지수', '개발호재', '공급리스크', '학군',
        '거시환경', '지역계층'
    ]
    DEFAULT_WEIGHTS = np.array([
        15, 8, 8, 8, 5, 5, 10, 8, 8, 8, 10, 7
    ])

    def __init__(self, db_path='realestate.db'):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.training_data = None  # list of dicts with factor_scores and actual_return
        self.best_weights = None
        self.best_corr = 0.0
        self._load_scorer()

    def _load_scorer(self):
        """Lazy-load ScorerV3 for scoring methods."""
        from strategy.scorer_v3 import ScorerV3
        self.scorer = ScorerV3(self.db_path)

    def _get_ref_dates(self):
        """Get reference dates matching ScorerV3's logic."""
        row = self.conn.execute(
            "SELECT MAX(deal_date) FROM apt_trade WHERE deal_date IS NOT NULL"
        ).fetchone()
        ref_date = row[0] if row and row[0] else "2025-05-31"
        d3 = self.conn.execute(
            f"SELECT date('{ref_date}', '-3 months')"
        ).fetchone()[0]
        d12 = self.conn.execute(
            f"SELECT date('{ref_date}', '-12 months')"
        ).fetchone()[0]
        return ref_date, d3, d12

    def collect_training_data(self):
        """
        백테스트를 실행하여 각 지역의 factor 점수와 실제 가격 변동률 수집.

        Returns:
            list[dict]: 각 지역의 factor별 점수와 실제 수익률
        """
        regions = [r[0] for r in self.conn.execute(
            "SELECT DISTINCT region FROM apt_trade ORDER BY region"
        ).fetchall()]

        ref_date, d3, d12 = self._get_ref_dates()
        training_data = []

        # Score each region and collect factor breakdowns + actual return
        for region in regions:
            try:
                result = self.scorer.score_region(region)
                factors = result['factors']

                # Extract individual factor scores
                factor_scores = []
                for fname in self.FACTOR_NAMES:
                    factor_scores.append(factors.get(fname, {}).get('score', 0))

                # Calculate actual return over the same period
                row = self.conn.execute("""
                    SELECT ROUND(AVG(CASE WHEN deal_date >= ? THEN price/10000.0 END), 1),
                           ROUND(AVG(CASE WHEN deal_date >= ? AND deal_date < ? THEN price/10000.0 END), 1)
                    FROM apt_trade WHERE region = ? AND price BETWEEN 10000 AND 300000 AND deal_date >= ?
                """, (d3, d12, d3, region, d12)).fetchone()
                p3 = row[0] or 0
                p12_3 = row[1] or 0

                if p12_3 > 0:
                    actual_return = round((p3 - p12_3) * 100.0 / p12_3, 1)
                    training_data.append({
                        'region': region,
                        'factor_scores': np.array(factor_scores, dtype=float),
                        'total_score': result['total_score'],
                        'actual_return': actual_return,
                    })
            except Exception:
                continue

        self.training_data = training_data
        return training_data

    def optimize_weights(self, method='bruteforce'):
        """
        Brute-force grid search로 최적의 가중치 찾기.

        sklearn/scipy가 없어도 numpy만으로 동작.

        Args:
            method: 'bruteforce' (기본) — 간단한 그리드 서치

        Returns:
            dict: {'weights': np.array, 'correlation': float, 'method': str}
        """
        if not self.training_data:
            self.collect_training_data()

        if len(self.training_data) < 10:
            return {
                'weights': self.DEFAULT_WEIGHTS.copy(),
                'correlation': 0.0,
                'method': 'insufficient_data',
                'count': len(self.training_data),
            }

        factor_matrix = np.array([d['factor_scores'] for d in self.training_data])
        actual_returns = np.array([d['actual_return'] for d in self.training_data])

        # Brute-force grid search over weight multipliers (0.5x, 0.75x, 1.0x, 1.25x, 1.5x)
        best_corr = -1.0
        best_weights = self.DEFAULT_WEIGHTS.copy()
        multipliers = [0.6, 0.8, 1.0, 1.2, 1.4]

        # Phase 1: Per-factor grid search (each factor optimized independently)
        # 5^12 is too large, so we use iterative refinement: 3 rounds
        best_weights = self.DEFAULT_WEIGHTS.copy()
        multipliers = [0.3, 0.5, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 2.0, 3.0]

        for _ in range(3):  # 3 rounds of iterative refinement
            for idx in range(len(best_weights)):
                for m in multipliers:
                    weights = best_weights.copy()
                    weights[idx] = self.DEFAULT_WEIGHTS[idx] * m
                    predicted = np.dot(factor_matrix, weights)
                    if np.std(predicted) > 0 and np.std(actual_returns) > 0:
                        corr = np.corrcoef(predicted, actual_returns)[0, 1]
                        if corr > best_corr:
                            best_corr = corr
                            best_weights = weights.copy()

        # Phase 2: Refine top-performing factors with finer granularity
        refined_multipliers = [x / 10 for x in range(2, 31, 1)]  # 0.2 to 3.0 step 0.1
        top_indices = np.argsort(best_weights)[-3:]  # top 3 factors
        for idx in top_indices:
            base = self.DEFAULT_WEIGHTS[idx]
            for m in refined_multipliers:
                weights = best_weights.copy()
                weights[idx] = base * m
                predicted = np.dot(factor_matrix, weights)
                if np.std(predicted) > 0 and np.std(actual_returns) > 0:
                    corr = np.corrcoef(predicted, actual_returns)[0, 1]
                    if corr > best_corr:
                        best_corr = corr
                        best_weights = weights.copy()

        self.best_weights = best_weights.round(1)
        self.best_corr = round(best_corr, 4)

        return {
            'weights': self.best_weights,
            'correlation': self.best_corr,
            'method': 'bruteforce_grid',
            'count': len(self.training_data),
            'weight_map': dict(zip(self.FACTOR_NAMES, self.best_weights.tolist())),
        }

    def apply_weights(self):
        """
        최적화된 가중치를 ScorerV3에 적용.

        ScorerV3는 각 factor별로 고정 가중치를 사용하므로,
        이 메서드는 내부 DB에 최적 가중치를 저장하고
        get_score 호출 시 가중치 반영을 위한 설정을 제공한다.

        Returns:
            bool: 적용 성공 여부
        """
        if self.best_weights is None:
            result = self.optimize_weights()
            if result['correlation'] <= 0:
                return False

        # Store optimized weights in a settings table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS ml_weights (
                factor_name TEXT PRIMARY KEY,
                default_weight REAL,
                optimized_weight REAL,
                updated_at TEXT
            )
        """)

        now = datetime.now().strftime('%Y-%m-%d %H:%M')
        for i, fname in enumerate(self.FACTOR_NAMES):
            self.conn.execute("""
                INSERT OR REPLACE INTO ml_weights
                (factor_name, default_weight, optimized_weight, updated_at)
                VALUES (?, ?, ?, ?)
            """, (fname, self.DEFAULT_WEIGHTS[i], self.best_weights[i], now))

        self.conn.commit()

        # Log the optimization result
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS ml_optimization_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                correlation REAL,
                count INTEGER,
                method TEXT,
                created_at TEXT
            )
        """)
        self.conn.execute("""
            INSERT INTO ml_optimization_log (correlation, count, method, created_at)
            VALUES (?, ?, ?, ?)
        """, (self.best_corr, len(self.training_data or []), 'bruteforce', now))
        self.conn.commit()

        return True

    def analyze_features(self):
        """
        특징 중요도 분석 — 각 factor가 예측에 미치는 영향도 계산.

        Returns:
            dict: {
                'importance': {factor_name: importance_score},
                'correlation_matrix': {factor_name: corr_with_actual},
                'top_features': [(name, score), ...],
            }
        """
        if not self.training_data:
            self.collect_training_data()

        if len(self.training_data) < 5:
            return {'importance': {}, 'correlation_matrix': {}, 'top_features': []}

        factor_matrix = np.array([d['factor_scores'] for d in self.training_data])
        actual_returns = np.array([d['actual_return'] for d in self.training_data])

        # Method 1: Correlation of each factor with actual returns
        corr_with_actual = {}
        for i, fname in enumerate(self.FACTOR_NAMES):
            f_scores = factor_matrix[:, i]
            if np.std(f_scores) > 0 and np.std(actual_returns) > 0:
                corr = np.corrcoef(f_scores, actual_returns)[0, 1]
                corr_with_actual[fname] = round(corr, 3)
            else:
                corr_with_actual[fname] = 0.0

        # Method 2: Use optimized weights as importance indicator
        if self.best_weights is not None:
            # Normalize weight changes as importance
            default_norm = self.DEFAULT_WEIGHTS / (self.DEFAULT_WEIGHTS.sum() or 1)
            opt_norm = self.best_weights / (self.best_weights.sum() or 1)
            importance = {}
            for i, fname in enumerate(self.FACTOR_NAMES):
                # How much the weight changed relative to default
                delta = abs(opt_norm[i] - default_norm[i])
                importance[fname] = round(opt_norm[i] * 100, 1)
        else:
            # Without optimization, use absolute correlation
            total_abs = sum(abs(v) for v in corr_with_actual.values()) or 1
            importance = {
                k: round(abs(v) / total_abs * 100, 1)
                for k, v in corr_with_actual.items()
            }

        # Sort features by importance
        sorted_features = sorted(
            importance.items(), key=lambda x: x[1], reverse=True
        )

        return {
            'importance': importance,
            'correlation_matrix': corr_with_actual,
            'top_features': sorted_features,
        }

    def get_optimization_history(self):
        """최적화 이력 조회"""
        rows = self.conn.execute("""
            SELECT * FROM ml_optimization_log
            ORDER BY created_at DESC LIMIT 20
        """).fetchall()
        return [dict(r) for r in rows]

    def get_current_weights(self):
        """현재 저장된 최적 가중치 조회"""
        rows = self.conn.execute("""
            SELECT * FROM ml_weights ORDER BY factor_name
        """).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self.scorer.close()
        self.conn.close()


def main():
    """CLI runner for MLOptimizer"""
    import argparse

    parser = argparse.ArgumentParser(description='ML 가중치 최적화 도구 (v3.0)')
    parser.add_argument('action', nargs='?', default='optimize',
                        choices=['optimize', 'analyze', 'show', 'apply'],
                        help='실행할 작업')
    parser.add_argument('--db', default='realestate.db',
                        help='데이터베이스 경로')

    args = parser.parse_args()

    opt = MLOptimizer(args.db)

    if args.action == 'optimize':
        print("📊 학습 데이터 수집 중...")
        data = opt.collect_training_data()
        print(f"  → {len(data)}개 지역 데이터 수집 완료")

        print("🔍 가중치 최적화 중...")
        result = opt.optimize_weights()

        print(f"\n=== 최적화 결과 ===")
        print(f"  상관계수: {result['correlation']:.4f}")
        print(f"  방법: {result['method']}")
        print(f"  학습 데이터: {result['count']}개 지역")
        print(f"\n  최적 가중치:")
        for name, w in result['weight_map'].items():
            default = opt.DEFAULT_WEIGHTS[opt.FACTOR_NAMES.index(name)]
            delta = w - default
            sign = '+' if delta > 0 else ''
            print(f"    {name:12s}: {w:>6.1f} (기본 {default:>5.1f}, {sign}{delta:.1f})")

    elif args.action == 'analyze':
        print("🔬 특징 중요도 분석 중...")
        analysis = opt.analyze_features()

        print(f"\n=== 특징 중요도 ===")
        for name, imp in analysis['top_features']:
            corr = analysis['correlation_matrix'].get(name, 0)
            print(f"  {name:12s}: 중요도 {imp:>6.1f}%  (상관계수 {corr:>+.3f})")

        print(f"\n=== 상관계수 행렬 ===")
        for name, corr in sorted(analysis['correlation_matrix'].items(),
                                  key=lambda x: abs(x[1]), reverse=True):
            bar = '█' * int(abs(corr) * 20) + '░' * (20 - int(abs(corr) * 20))
            print(f"  {name:12s} |{bar}| {corr:>+.3f}")

    elif args.action == 'show':
        print("=== 현재 최적 가중치 ===")
        weights = opt.get_current_weights()
        if weights:
            for w in weights:
                print(f"  {w['factor_name']:12s}: 기본 {w['default_weight']:>5.1f} → 최적 {w['optimized_weight']:>5.1f}")
        else:
            print("  저장된 가중치 없음. 먼저 'optimize' 실행 필요.")

        print("\n=== 최적화 이력 ===")
        history = opt.get_optimization_history()
        if history:
            for h in history:
                print(f"  {h['created_at']}: 상관계수 {h['correlation']:.4f} (n={h['count']}, {h['method']})")
        else:
            print("  최적화 이력 없음.")

    elif args.action == 'apply':
        print("💾 최적 가중치 적용 중...")
        success = opt.apply_weights()
        if success:
            print("✅ 가중치 적용 완료")
            print(f"  최종 상관계수: {opt.best_corr:.4f}")
        else:
            print("❌ 가중치 적용 실패")

    opt.close()


if __name__ == '__main__':
    main()
