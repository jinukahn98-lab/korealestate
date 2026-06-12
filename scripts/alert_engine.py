"""
Watchlist + 가격 변동 알림 엔진

사용자가 등록한 관심 단지(watchlist)의 점수/가격 변동을
주기적으로 체크하여 알림(price_alerts)을 생성한다.
"""

import sqlite3
import os
import sys
from datetime import datetime

# 상위 디렉토리를 PYTHONPATH에 추가
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from data.database import get_conn, DB_PATH

# ─── Watchlist CRUD ──────────────────────────────────────────


def register_watchlist(user_id, apt_name, region,
                       alert_on_price_change=True,
                       alert_threshold_pct=3.0):
    """관심 단지 등록 (중복 방지: user_id+apt_name+region UNIQUE)"""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT OR IGNORE INTO watchlist
                (user_id, apt_name, region, alert_on_price_change, alert_threshold_pct)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, apt_name, region,
              int(alert_on_price_change), alert_threshold_pct))
        conn.commit()
        inserted = cur.rowcount > 0
        if inserted:
            print(f"  ✅ 관심 단지 등록: {apt_name} ({region})")
        else:
            print(f"  ℹ️  이미 등록된 단지입니다: {apt_name} ({region})")
        return inserted
    finally:
        conn.close()


def remove_watchlist(watchlist_id, user_id=None):
    """관심 단지 삭제 (user_id가 주어지면 소유자 확인)"""
    conn = get_conn()
    cur = conn.cursor()
    try:
        if user_id:
            cur.execute(
                "DELETE FROM watchlist WHERE id = ? AND user_id = ?",
                (watchlist_id, user_id))
        else:
            cur.execute(
                "DELETE FROM watchlist WHERE id = ?",
                (watchlist_id,))
        conn.commit()
        deleted = cur.rowcount > 0
        if deleted:
            print(f"  ✅ 관심 단지 삭제 완료 (id={watchlist_id})")
        else:
            print(f"  ⚠️  해당 관심 단지를 찾을 수 없습니다 (id={watchlist_id})")
        return deleted
    finally:
        conn.close()


def list_watchlists(user_id='default'):
    """사용자의 관심 단지 목록 조회"""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id, apt_name, region, alert_on_price_change,
                   alert_threshold_pct, last_score, last_price, created_at
            FROM watchlist
            WHERE user_id = ?
            ORDER BY created_at DESC
        """, (user_id,))
        rows = cur.fetchall()
        result = []
        for r in rows:
            result.append({
                'id': r[0],
                'apt_name': r[1],
                'region': r[2],
                'alert_on_price_change': bool(r[3]),
                'alert_threshold_pct': r[4],
                'last_score': r[5],
                'last_price': r[6],
                'created_at': r[7],
            })
        return result
    finally:
        conn.close()


def get_price_alerts(user_id='default', limit=20):
    """사용자별 가격 변동 알림 내역"""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT pa.id, pa.watchlist_id, pa.alert_type,
                   pa.old_value, pa.new_value, pa.message,
                   pa.created_at, pa.notified,
                   w.apt_name, w.region
            FROM price_alerts pa
            JOIN watchlist w ON pa.watchlist_id = w.id
            WHERE w.user_id = ?
            ORDER BY pa.created_at DESC
            LIMIT ?
        """, (user_id, limit))
        rows = cur.fetchall()
        result = []
        for r in rows:
            result.append({
                'id': r[0],
                'watchlist_id': r[1],
                'alert_type': r[2],
                'old_value': r[3],
                'new_value': r[4],
                'message': r[5],
                'created_at': r[6],
                'notified': bool(r[7]),
                'apt_name': r[8],
                'region': r[9],
            })
        return result
    finally:
        conn.close()


# ─── 가격/점수 변동 체크 ────────────────────────────────────


def _get_latest_price(conn, apt_name, region):
    """DB에서 특정 단지의 최신 평균 매매가 조회"""
    cur = conn.cursor()
    cur.execute("""
        SELECT ROUND(AVG(price), 0) as avg_price
        FROM apt_trade
        WHERE apt_name = ? AND region LIKE ?
          AND deal_date >= date((SELECT MAX(deal_date) FROM apt_trade), '-6 months')
    """, (apt_name, f'%{region}%'))
    row = cur.fetchone()
    return float(row[0]) if row and row[0] else None


def check_watchlist(engine=None):
    """
    모든 watchlist 단지의 점수/가격 변동 체크

    - engine: RecommendationEngine 인스턴스 (없으면 자동 생성)
    - 각 watchlist 항목의 apt_name+region으로 score_apt() 호출
    - last_score/last_price와 비교하여 변화량이 alert_threshold_pct 이상이면
      price_alerts 테이블에 알림 저장
    - last_score/last_price 업데이트
    """
    if engine is None:
        from strategy.recommender import RecommendationEngine
        engine = RecommendationEngine()

    conn = get_conn()
    cur = conn.cursor()

    try:
        # 모든 watchlist 조회
        cur.execute("""
            SELECT id, user_id, apt_name, region,
                   alert_on_price_change, alert_threshold_pct,
                   last_score, last_price
            FROM watchlist
            WHERE alert_on_price_change = 1
        """)
        rows = cur.fetchall()

        if not rows:
            print("  ℹ️  체크할 watchlist가 없습니다.")
            return []

        alerts_created = []
        for row in rows:
            wl_id, user_id, apt_name, region = row[0], row[1], row[2], row[3]
            alert_on_price_change = bool(row[4])
            threshold_pct = row[5] or 3.0
            last_score = row[6]
            last_price = row[7]

            try:
                # 현재 점수 계산
                result = engine.score_apt(apt_name, region)
                current_score = result['total_score']

                # 현재 평균 가격 조회
                current_price = _get_latest_price(conn, apt_name, region)

                # ── 점수 변동 체크 ──
                if last_score is not None and current_score is not None:
                    score_change = current_score - last_score
                    if abs(score_change) >= threshold_pct:
                        direction = 'up' if score_change > 0 else 'down'
                        msg = (
                            f"📊 [{apt_name}] 점수 변동: "
                            f"{last_score:.1f} → {current_score:.1f} "
                            f"({score_change:+.1f}점)"
                        )
                        cur.execute("""
                            INSERT INTO price_alerts
                                (watchlist_id, alert_type, old_value, new_value, message)
                            VALUES (?, ?, ?, ?, ?)
                        """, (wl_id, f'score_{direction}',
                              float(last_score), float(current_score), msg))
                        alerts_created.append(msg)
                        print(f"  {msg}")

                # ── 가격 변동 체크 ──
                if (last_price is not None and current_price is not None
                        and last_price > 0):
                    price_change_pct = ((current_price - last_price) / last_price) * 100
                    if abs(price_change_pct) >= threshold_pct:
                        direction = 'up' if price_change_pct > 0 else 'down'
                        msg = (
                            f"💰 [{apt_name}] 가격 변동: "
                            f"{last_price:,.0f}원 → {current_price:,.0f}원 "
                            f"({price_change_pct:+.1f}%)"
                        )
                        cur.execute("""
                            INSERT INTO price_alerts
                                (watchlist_id, alert_type, old_value, new_value, message)
                            VALUES (?, ?, ?, ?, ?)
                        """, (wl_id, f'price_{direction}',
                              float(last_price), float(current_price), msg))
                        alerts_created.append(msg)
                        print(f"  {msg}")

                # last_score, last_price 업데이트
                cur.execute("""
                    UPDATE watchlist
                    SET last_score = ?, last_price = ?
                    WHERE id = ?
                """, (current_score, current_price, wl_id))

            except Exception as e:
                print(f"  ⚠️  [{apt_name}] 체크 중 오류: {e}")
                continue

        conn.commit()
        print(f"\n  ✅ watchlist 체크 완료: {len(alerts_created)}개 알림 생성")
        return alerts_created

    finally:
        conn.close()
        if engine:
            engine.close()


# ─── CLI ─────────────────────────────────────────────────────


def print_watchlists(user_id='default'):
    """CLI용 관심 단지 출력"""
    items = list_watchlists(user_id)
    if not items:
        print("  ℹ️  등록된 관심 단지가 없습니다.")
        return
    print(f"\n{'='*70}")
    print(f"  📋 [{user_id}] 관심 단지 목록")
    print(f"{'='*70}")
    for item in items:
        score_str = f"{item['last_score']:.1f}점" if item['last_score'] is not None else "-"
        price_str = f"{item['last_price']:,.0f}원" if item['last_price'] is not None else "-"
        print(f"  #{item['id']}  {item['apt_name']} ({item['region']})")
        print(f"      점수: {score_str}  |  가격: {price_str}")
        print(f"      알림: {'ON' if item['alert_on_price_change'] else 'OFF'}  "
              f"|  임계값: {item['alert_threshold_pct']}%")
        print(f"      등록일: {item['created_at']}")
    print()


def print_alerts(user_id='default', limit=20):
    """CLI용 알림 출력"""
    alerts = get_price_alerts(user_id, limit)
    if not alerts:
        print("  ℹ️  최근 알림이 없습니다.")
        return
    print(f"\n{'='*70}")
    print(f"  🔔 [{user_id}] 최근 알림 (최대 {limit}건)")
    print(f"{'='*70}")
    for a in alerts:
        notified = '✅' if a['notified'] else '⏳'
        print(f"  [{a['created_at']}] {notified} {a['apt_name']} ({a['region']})")
        print(f"    {a['message']}")
    print()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Watchlist + 알림 엔진')
    parser.add_argument('action', nargs='?', default='check',
                        choices=['check', 'list', 'alerts', 'add', 'remove'],
                        help='실행할 액션')
    parser.add_argument('--user', default='default', help='사용자 ID')
    parser.add_argument('--apt', help='단지명 (add 액션)')
    parser.add_argument('--region', help='지역명 (add 액션)')
    parser.add_argument('--id', type=int, help='watchlist ID (remove 액션)')
    parser.add_argument('--threshold', type=float, default=3.0,
                        help='알림 임계값 %% (기본: 3.0)')
    parser.add_argument('--limit', type=int, default=20, help='조회 건수')
    args = parser.parse_args()

    if args.action == 'check':
        check_watchlist()
    elif args.action == 'list':
        print_watchlists(args.user)
    elif args.action == 'alerts':
        print_alerts(args.user, args.limit)
    elif args.action == 'add':
        if not args.apt or not args.region:
            print("  ❌ --apt 와 --region 을 모두 입력하세요")
            sys.exit(1)
        register_watchlist(args.user, args.apt, args.region,
                           alert_threshold_pct=args.threshold)
    elif args.action == 'remove':
        if not args.id:
            print("  ❌ --id 를 입력하세요")
            sys.exit(1)
        remove_watchlist(args.id, args.user)
    print_alerts(args.user, 5)
