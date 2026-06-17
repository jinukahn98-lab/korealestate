"""외부 리포트 통합 수집 스크립트"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from datetime import datetime


def run():
    print(f"📡 외부 리포트 수집 시작 ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
    print("=" * 50)

    from collectors.naver_news import GoogleNewsCollector, GovPolicyCollector, KBStatsCollector

    collectors = [
        ("Google 뉴스", GoogleNewsCollector()),
        ("KB 통계", KBStatsCollector()),
        ("정부 정책", GovPolicyCollector()),
    ]

    total = 0
    for name, collector in collectors:
        print(f"\n[{name}] 수집 중...")
        try:
            reports = collector.collect()
            print(f"  → {len(reports)}건 발견")
            if reports:
                collector.save_to_wiki(reports)
                collector.update_wiki_log(len(reports))
                total += len(reports)
                print(f"  ✅ wiki/raw/articles/{collector.source_name}/ 저장 완료")
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"  ⚠️ 오류: {e}")

    print(f"\n{'=' * 50}")
    print(f"✅ 총 {total}건 리포트 수집 완료")


if __name__ == '__main__':
    run()
