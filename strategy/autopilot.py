"""
v3.0 오토파일럿 — 부동산 분석 파이프라인 자동화

전체 수집 → 점수 계산 → 리포트 생성 → 브리핑까지
단일 워크플로우로 실행.
"""
import sqlite3
import os
import sys
from datetime import datetime
from pathlib import Path


class Autopilot:
    """
    부동산 분석 파이프라인 자동화 클래스.

    사용법:
        ap = Autopilot()
        ap.run_full_pipeline()      # 전체 파이프라인 실행
        ap.run_daily_briefing()     # 일일 브리핑 생성
        ap.check_data_quality()     # 데이터 품질 점검
        ap.generate_report()        # 마크다운 리포트 생성
    """

    def __init__(self, db_path='realestate.db', wiki_dir=None):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._ensure_log_table()

        # Wiki directory for reports
        if wiki_dir is None:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.wiki_dir = os.path.join(base, 'wiki')
        else:
            self.wiki_dir = wiki_dir
        os.makedirs(self.wiki_dir, exist_ok=True)

    def _ensure_log_table(self):
        """autopilot_log 테이블 생성"""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS autopilot_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                event TEXT,
                status TEXT,
                detail TEXT
            )
        """)
        self.conn.commit()

    def _log(self, event, status, detail=''):
        """이벤트 로그 기록"""
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.conn.execute("""
            INSERT INTO autopilot_log (timestamp, event, status, detail)
            VALUES (?, ?, ?, ?)
        """, (now, event, status, detail))
        self.conn.commit()

    def run_full_pipeline(self):
        """
        전체 파이프라인 실행:

        1. 모든 collector 실행 (데이터 수집/seed)
        2. ScorerV3 실행 (전체 지역 점수 계산)
        3. 결과 DB 저장
        4. 로그 기록

        Returns:
            dict: 파이프라인 실행 결과 요약
        """
        print("=" * 60)
        print("🚀 오토파일럿 v3.0 — 전체 파이프라인 시작")
        print(f"   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)

        results = {
            'started_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'collectors': {},
            'scorer': None,
            'status': 'running',
        }

        # ── Step 1: Run all collectors ──
        collectors = [
            ('KB 매매수급지수', 'collectors.kb_index', 'KBIndexCollector'),
            ('개발호재', 'collectors.development_news', 'DevelopmentCollector'),
            ('공급데이터', 'collectors.supply_data', 'SupplyCollector'),
            ('거시지표', 'collectors.interest_rate', 'MacroCollector'),
            ('학군정보', 'collectors.school_info', 'SchoolCollector'),
            ('뉴스감성', 'collectors.news_sentiment', 'NewsSentimentCollector'),
        ]

        for label, module_path, class_name in collectors:
            try:
                import importlib
                mod = importlib.import_module(module_path)
                cls = getattr(mod, class_name)
                collector = cls(self.db_path)
                n = collector.collect()
                collector.close()
                results['collectors'][label] = {'status': 'ok', 'records': n}
                print(f"  ✅ {label}: {n}건 저장")
                self._log(f'collector:{label}', 'ok', f'{n}건 저장')
            except Exception as e:
                results['collectors'][label] = {'status': 'error', 'error': str(e)}
                print(f"  ❌ {label}: {e}")
                self._log(f'collector:{label}', 'error', str(e))

        # ── Step 2: Run ScorerV3 ──
        print("\n📊 ScorerV3 점수 계산 중...")
        try:
            from strategy.scorer_v3 import ScorerV3
            scorer = ScorerV3(self.db_path)
            regions = [r[0] for r in self.conn.execute(
                "SELECT DISTINCT region FROM apt_trade ORDER BY region"
            ).fetchall()]

            scored_regions = []
            for region in regions:
                try:
                    result = scorer.score_region(region)
                    scored_regions.append(result)
                except Exception as e:
                    continue

            scorer.close()

            # Sort by score
            scored_regions.sort(key=lambda x: x['total_score'], reverse=True)

            # Save to DB
            self._save_scores_to_db(scored_regions)

            results['scorer'] = {
                'status': 'ok',
                'regions_scored': len(scored_regions),
                'top_region': scored_regions[0]['region'] if scored_regions else None,
                'top_score': scored_regions[0]['total_score'] if scored_regions else 0,
            }
            print(f"  ✅ {len(scored_regions)}개 지역 점수 계산 완료")
            if scored_regions:
                top = scored_regions[0]
                print(f"  🏆 1위: {top['region']} ({top['total_score']}점 {top['grade']})")
            self._log('scorer', 'ok', f'{len(scored_regions)}개 지역 점수 계산')
        except Exception as e:
            results['scorer'] = {'status': 'error', 'error': str(e)}
            print(f"  ❌ ScorerV3: {e}")
            self._log('scorer', 'error', str(e))

        # ── Step 3: Run backtest ──
        print("\n📈 백테스트 실행 중...")
        try:
            # Re-create scorer for backtest (separate connection)
            scorer2 = ScorerV3(self.db_path)
            bt = scorer2.backtest()
            scorer2.close()
            results['backtest'] = bt
            print(f"  ✅ 상관계수: {bt['correlation']} (n={bt['count']})")
            self._log('backtest', 'ok', f"상관계수 {bt['correlation']}, n={bt['count']}")
        except Exception as e:
            results['backtest'] = {'error': str(e)}
            print(f"  ❌ 백테스트: {e}")
            self._log('backtest', 'error', str(e))

        results['status'] = 'completed'
        results['finished_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        print("\n" + "=" * 60)
        print("✅ 오토파일럿 파이프라인 완료")
        print(f"   소요: {len(regions) if 'regions' in dir() else 0}개 지역 분석")
        print("=" * 60)
        self._log('pipeline', 'completed', f"전체 파이프라인 완료")

        return results

    def _save_scores_to_db(self, scored_regions):
        """ScorerV3 결과를 DB에 저장"""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS scorer_results (
                region TEXT PRIMARY KEY,
                total_score REAL,
                grade TEXT,
                factors TEXT,
                version TEXT,
                scored_at TEXT
            )
        """)
        import json
        now = datetime.now().strftime('%Y-%m-%d %H:%M')
        for r in scored_regions:
            self.conn.execute("""
                INSERT OR REPLACE INTO scorer_results
                (region, total_score, grade, factors, version, scored_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                r['region'],
                r['total_score'],
                r['grade'],
                json.dumps(r['factors'], ensure_ascii=False),
                r['version'],
                now,
            ))
        self.conn.commit()

    def run_daily_briefing(self):
        """
        Telegram-format 일일 브리핑 생성.

        Returns:
            str: Telegram 마크다운 형식의 브리핑 텍스트
        """
        now = datetime.now()
        date_str = now.strftime('%Y-%m-%d')

        # Get latest scorer results
        rows = self.conn.execute("""
            SELECT * FROM scorer_results ORDER BY total_score DESC LIMIT 10
        """).fetchall()

        # Get backtest
        bt = {}
        try:
            from strategy.scorer_v3 import ScorerV3
            s = ScorerV3(self.db_path)
            bt = s.backtest()
            s.close()
        except Exception:
            pass

        # Build briefing
        lines = []
        lines.append(f"🏠 *부동산 v3.0 일일 브리핑*")
        lines.append(f"📅 {date_str}")
        lines.append("")

        lines.append("━" * 30)
        lines.append("*📊 TOP 10 지역*")
        lines.append("")

        if rows:
            for i, row in enumerate(rows):
                short = row['region']
                for p in ['서울특별시 ', '경기도 ', '부산광역시 ', '대전광역시 ',
                          '대구광역시 ', '인천광역시 ', '광주광역시 ', '울산광역시 ',
                          '세종특별자치시 ']:
                    short = short.replace(p, '')
                grade = row['grade']
                lines.append(f"{i+1}. *{short}* — {row['total_score']}점 {grade}")
        else:
            lines.append("데이터 없음")

        lines.append("")
        lines.append("━" * 30)
        lines.append("*📈 백테스트*")
        if bt:
            lines.append(f"상관계수: `{bt.get('correlation', 'N/A')}`")
            lines.append(f"분석지역: `{bt.get('count', 0)}`개")
        else:
            lines.append("백테스트 데이터 없음")

        # Collector status
        lines.append("")
        lines.append("━" * 30)
        lines.append("*📡 데이터 품질*")
        quality = self.check_data_quality()
        for item in quality:
            icon = "✅" if item['healthy'] else "⚠️"
            lines.append(f"{icon} {item['name']}: {item['staleness_days']}일 경과")

        lines.append("")
        lines.append("━" * 30)
        lines.append(f"🤖 *오토파일럿 v3.0*")
        lines.append(f"생성: {now.strftime('%H:%M:%S')}")

        briefing = "\n".join(lines)
        self._log('daily_briefing', 'ok', f"브리핑 생성 ({len(rows)}개 지역)")

        return briefing

    def check_data_quality(self):
        """
        모든 collector 테이블의 신선도(staleness) 점검.

        Returns:
            list[dict]: 각 데이터 소스의 상태 정보
        """
        tables = [
            ('KB 매매수급지수', 'external_kb_index', 'collected_at', 30),
            ('개발호재', 'external_development', 'collected_at', 30),
            ('공급데이터', 'external_supply', 'collected_at', 30),
            ('학군정보', 'external_school', 'collected_at', 365),
            ('뉴스감성', 'external_news_sentiment', 'updated_at', 7),
            ('거시지표', 'external_macro', 'collected_at', 30),
        ]

        results = []
        for name, table, date_col, max_stale in tables:
            try:
                row = self.conn.execute(
                    f"SELECT MAX({date_col}) as last FROM {table}"
                ).fetchone()
                last_date = row['last'] if row and row['last'] else None

                if last_date:
                    last_dt = datetime.strptime(last_date[:10], '%Y-%m-%d')
                    staleness = (datetime.now() - last_dt).days
                else:
                    staleness = 999

                results.append({
                    'name': name,
                    'table': table,
                    'last_updated': last_date or '없음',
                    'staleness_days': staleness,
                    'max_stale_days': max_stale,
                    'healthy': staleness <= max_stale,
                })
            except Exception as e:
                results.append({
                    'name': name,
                    'table': table,
                    'last_updated': '오류',
                    'staleness_days': 999,
                    'max_stale_days': max_stale,
                    'healthy': False,
                    'error': str(e),
                })

        self._log('data_quality', 'ok', f'{sum(1 for r in results if r["healthy"])}/{len(results)} 정상')
        return results

    def generate_report(self, filename=None):
        """
        마크다운 리포트 생성하여 wiki 디렉토리에 저장.

        Args:
            filename: 저장할 파일명 (기본: wiki/report_{날짜}.md)

        Returns:
            str: 저장된 파일 경로
        """
        if filename is None:
            date_str = datetime.now().strftime('%Y%m%d_%H%M')
            filename = os.path.join(self.wiki_dir, f'report_{date_str}.md')

        os.makedirs(os.path.dirname(filename), exist_ok=True)

        # ── Collect report data ──
        now = datetime.now()

        # Top regions from scorer_results
        top_rows = self.conn.execute("""
            SELECT * FROM scorer_results ORDER BY total_score DESC LIMIT 20
        """).fetchall()

        # Backtest
        bt = {}
        try:
            from strategy.scorer_v3 import ScorerV3
            s = ScorerV3(self.db_path)
            bt = s.backtest()
            s.close()
        except Exception:
            pass

        # Data quality
        quality = self.check_data_quality()

        # Collector record counts
        collector_counts = {}
        for name, table, _, _ in [
            ('KB 매매수급지수', 'external_kb_index', 'collected_at', 30),
            ('개발호재', 'external_development', 'collected_at', 30),
            ('공급데이터', 'external_supply', 'collected_at', 30),
            ('학군정보', 'external_school', 'collected_at', 365),
            ('뉴스감성', 'external_news_sentiment', 'updated_at', 7),
            ('거시지표', 'external_macro', 'collected_at', 30),
        ]:
            try:
                cnt = self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                collector_counts[name] = cnt
            except Exception:
                collector_counts[name] = 0

        # ── Build markdown ──
        md = []
        md.append(f"# 🏠 부동산 분석 리포트 v3.0")
        md.append(f"")
        md.append(f"- **생성일**: {now.strftime('%Y-%m-%d %H:%M')}")
        md.append(f"- **데이터베이스**: {os.path.basename(self.db_path)}")
        md.append(f"")
        md.append(f"---")
        md.append(f"")

        # Section 1: Top Regions
        md.append(f"## 📊 Top 20 지역")
        md.append(f"")
        md.append(f"| 순위 | 지역 | 점수 | 등급 |")
        md.append(f"|------|------|------|------|")
        for i, row in enumerate(top_rows):
            short = row['region']
            for p in ['서울특별시 ', '경기도 ', '부산광역시 ', '대전광역시 ',
                      '대구광역시 ', '인천광역시 ', '광주광역시 ', '울산광역시 ',
                      '세종특별자치시 ']:
                short = short.replace(p, '')
            md.append(f"| {i+1} | {short} | {row['total_score']} | {row['grade']} |")

        md.append(f"")

        # Section 2: Backtest
        md.append(f"## 📈 백테스트 결과")
        md.append(f"")
        if bt:
            md.append(f"- **상관계수**: {bt.get('correlation', 'N/A')}")
            md.append(f"- **분석 지역 수**: {bt.get('count', 0)}")
            md.append(f"- **평균 점수**: {bt.get('avg_score', 'N/A')}")
            md.append(f"- **평균 수익률**: {bt.get('avg_actual', 'N/A')}%")
        else:
            md.append(f"백테스트 데이터 없음")
        md.append(f"")

        # Section 3: Data Quality
        md.append(f"## 📡 데이터 품질")
        md.append(f"")
        md.append(f"| 소스 | 레코드 | 상태 | 경과일 |")
        md.append(f"|------|--------|------|--------|")
        for q in quality:
            icon = "✅" if q['healthy'] else "⚠️"
            cnt = collector_counts.get(q['name'], 0)
            md.append(f"| {q['name']} | {cnt} | {icon} | {q['staleness_days']}일 |")
        md.append(f"")

        # Section 4: Pipeline log
        md.append(f"## 📋 파이프라인 로그")
        md.append(f"")
        logs = self.conn.execute("""
            SELECT * FROM autopilot_log ORDER BY id DESC LIMIT 20
        """).fetchall()
        md.append(f"| 시간 | 이벤트 | 상태 | 상세 |")
        md.append(f"|------|--------|------|------|")
        for log in logs:
            md.append(f"| {log['timestamp']} | {log['event']} | {log['status']} | {log['detail']} |")
        md.append(f"")

        md.append(f"---")
        md.append(f"*🤖 생성: 오토파일럿 v3.0*")

        report = "\n".join(md)

        # Write file
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(report)

        self._log('generate_report', 'ok', f"리포트 저장: {filename}")
        print(f"✅ 리포트 저장 완료: {filename}")

        return filename

    def close(self):
        self.conn.close()


def main():
    """CLI mode for Autopilot"""
    import argparse

    parser = argparse.ArgumentParser(description='오토파일럿 v3.0 — 부동산 분석 파이프라인')
    parser.add_argument('action', nargs='?', default='pipeline',
                        choices=['pipeline', 'briefing', 'quality', 'report'],
                        help='실행할 작업')
    parser.add_argument('--db', default='realestate.db',
                        help='데이터베이스 경로')
    parser.add_argument('--output', '-o', default=None,
                        help='리포트 출력 경로 (report 액션)')

    args = parser.parse_args()
    ap = Autopilot(args.db)

    if args.action == 'pipeline':
        results = ap.run_full_pipeline()
        print(f"\n📋 파이프라인 요약:")
        print(f"  상태: {results['status']}")
        print(f"  시작: {results['started_at']}")
        print(f"  종료: {results.get('finished_at', 'N/A')}")
        for name, info in results.get('collectors', {}).items():
            status_icon = "✅" if info['status'] == 'ok' else "❌"
            detail = f"({info.get('records', '?')}건)" if info['status'] == 'ok' else f"({info.get('error', '?')})"
            print(f"  {status_icon} {name}: {detail}")

    elif args.action == 'briefing':
        briefing = ap.run_daily_briefing()
        print("\n" + briefing)

    elif args.action == 'quality':
        print("\n📡 데이터 품질 점검")
        print("=" * 50)
        quality = ap.check_data_quality()
        for item in quality:
            status_icon = "✅" if item['healthy'] else "⚠️"
            print(f"\n{status_icon} {item['name']}")
            print(f"   테이블: {item['table']}")
            print(f"   최종 업데이트: {item['last_updated']}")
            print(f"   경과일: {item['staleness_days']}일 / 최대 {item['max_stale_days']}일")
            if not item['healthy']:
                print(f"   ⚠️ ** 데이터 신선도 초과! **")
            if 'error' in item:
                print(f"   ❌ 오류: {item['error']}")

        healthy_count = sum(1 for r in quality if r['healthy'])
        print(f"\n📊 전체: {healthy_count}/{len(quality)} 정상")

    elif args.action == 'report':
        path = ap.generate_report(args.output)
        print(f"✅ 리포트 저장: {path}")

    ap.close()


if __name__ == '__main__':
    main()
