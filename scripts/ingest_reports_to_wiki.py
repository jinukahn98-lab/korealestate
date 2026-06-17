"""외부 리포트 → 위키 개념 페이지 인제스트"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from datetime import datetime
import re


def ingest():
    wiki = os.path.expanduser('~/wiki')
    raw_dir = os.path.join(wiki, 'raw/articles')
    today = datetime.now().strftime('%Y-%m-%d')

    # 오늘 수집된 raw 파일 읽기
    new_articles = []
    for root, dirs, files in os.walk(raw_dir):
        for f in files:
            if f.startswith(today):
                with open(os.path.join(root, f), 'r') as fh:
                    content = fh.read()
                new_articles.append({
                    'path': os.path.relpath(os.path.join(root, f), wiki),
                    'content': content,
                    'source': os.path.basename(root),
                })

    if not new_articles:
        print("📭 오늘 수집된 새 리포트 없음")
        return

    print(f"📚 {len(new_articles)}개 리포트 인제스트 중...")

    # 키워드 기반 분류
    policy_news = []
    market_news = []
    development_news = []

    for a in new_articles:
        text = a['content']
        if any(x in text for x in ['LTV', 'DSR', '규제', '정책', '금리', '대출', '세금', '종부세']):
            policy_news.append(a)
        if any(x in text for x in ['시세', '매매', '전세', '가격', '거래량', 'KB']):
            market_news.append(a)
        if any(x in text for x in ['GTX', '재건축', '재개발', '신도시', '개발', '정비']):
            development_news.append(a)

    print(f"  🏛️ 정책: {len(policy_news)}건")
    print(f"  📊 시장: {len(market_news)}건")
    print(f"  🏗️ 개발: {len(development_news)}건")

    # 업데이트 요약
    summary = []
    if policy_news:
        summary.append(f"- 정책 뉴스 {len(policy_news)}건 → [[current-policy]]")
    if market_news:
        summary.append(f"- 시장 뉴스 {len(market_news)}건 → [[market-trends]]")
    if development_news:
        summary.append(f"- 개발 뉴스 {len(development_news)}건 → [[development-projects]]")

    # log.md 업데이트
    log_path = os.path.join(wiki, 'log.md')
    entry = f"\n## [{today}] ingest | 외부 리포트 → 위키\n- 총 {len(new_articles)}건 raw 리포트 처리\n"
    for s in summary:
        entry += f"  {s}\n"
    with open(log_path, 'a') as f:
        f.write(entry)

    print(f"  ✅ log.md 업데이트 완료")
    print(f"  📝 총 {len(new_articles)}건 인제스트 완료")

    # Export to repo JSON for dashboard
    export_script = os.path.join(os.path.dirname(__file__), 'export_wiki_reports.py')
    if os.path.exists(export_script):
        import subprocess
        subprocess.run([sys.executable, export_script], cwd=os.path.dirname(export_script))
        print(f"  ✅ repo JSON export 완료 (dashboard 반영)")


if __name__ == '__main__':
    ingest()
