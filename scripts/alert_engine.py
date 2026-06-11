"""
조건 기반 부동산 알림 엔진
- 사용자 등록 조건 저장/관리
- 갭 투자 / 전세가율 조건 매칭 체크
"""
import sqlite3
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from data.database import get_conn, DB_PATH
from strategy.gap_scanner import scan_gap_opportunities
from strategy.jeonse import alert_reverse_jeonse


def _ensure_tables():
    """alert_conditions, alert_history 테이블 생성"""
    conn = get_conn()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS alert_conditions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL,
            condition_type TEXT NOT NULL,
            region TEXT DEFAULT '',
            min_rate REAL DEFAULT 0,
            max_rate REAL DEFAULT 100,
            max_gap REAL DEFAULT 999999,
            min_trades INTEGER DEFAULT 3,
            active INTEGER DEFAULT 1,
            label TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS alert_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            condition_id INTEGER,
            matched_at TEXT DEFAULT (datetime('now', 'localtime')),
            matched_text TEXT
        );
    ''')
    conn.commit()
    conn.close()


def register_condition(chat_id, condition_type, **kwargs):
    """조건 등록"""
    _ensure_tables()
    conn = get_conn()
    conn.execute('''
        INSERT INTO alert_conditions
        (chat_id, condition_type, region, min_rate, max_rate, max_gap, min_trades, label)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        chat_id,
        condition_type,
        kwargs.get('region', ''),
        float(kwargs.get('min_rate', 0)),
        float(kwargs.get('max_rate', 100)),
        float(kwargs.get('max_gap', 999999)),
        int(kwargs.get('min_trades', 3)),
        kwargs.get('label', ''),
    ))
    conn.commit()
    cid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return cid


def list_conditions(chat_id=None):
    """등록된 조건 목록"""
    _ensure_tables()
    conn = get_conn()
    if chat_id:
        rows = conn.execute(
            "SELECT * FROM alert_conditions WHERE chat_id=? ORDER BY created_at DESC",
            (chat_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM alert_conditions ORDER BY created_at DESC"
        ).fetchall()
    conn.close()
    return rows


def remove_condition(condition_id):
    """조건 삭제"""
    _ensure_tables()
    conn = get_conn()
    conn.execute("DELETE FROM alert_conditions WHERE id=?", (condition_id,))
    conn.commit()
    conn.close()


def check_conditions():
    """
    모든 활성 조건 체크 → 매칭된 (chat_id, message) 리스트 반환
    """
    _ensure_tables()
    conn = get_conn()

    conditions = conn.execute(
        "SELECT * FROM alert_conditions WHERE active=1"
    ).fetchall()
    conn.close()

    if not conditions:
        return []

    results = []

    # 갭 데이터 한번만 로드
    gap_df = scan_gap_opportunities(min_rate=0, max_rate=100, max_gap=999999, min_trades=1)

    for cond in conditions:
        cid, chat_id, ctype, region, min_r, max_r, max_g, min_t, active, label, created = cond
        matched = []

        if ctype == 'gap' and gap_df is not None and not gap_df.empty:
            df = gap_df.copy()
            if region:
                df = df[df['region'].str.contains(region)]
            df = df[(df['jeonse_rate'] >= min_r) & (df['jeonse_rate'] <= max_r)]
            df = df[df['gap'] <= max_g]
            df = df[df['trade_count'] >= min_t]

            for _, r in df.head(5).iterrows():
                matched.append(
                    f"{r['region']} {r['apt_name']} | "
                    f"전세가율 {r['jeonse_rate']:.1f}% | "
                    f"갭 {r['gap']/10000:.1f}억 | "
                    f"거래 {r['trade_count']}건"
                )

        elif ctype == 'jeonse_rate':
            msg = alert_reverse_jeonse(threshold=min_r)
            if msg:
                lines = [l for l in msg.strip().split('\n') if l.strip()]
                for l in lines[2:]:  # skip header
                    if region and region not in l:
                        continue
                    matched.append(l.strip())

        if matched:
            today = datetime.now().strftime('%Y-%m-%d')
            label_str = f" [{label}]" if label else ""
            body = "\n".join(matched[:5])
            message = f"🔔 **조건 매칭{label_str}** ({today})\n{body}"

            # 기록 저장
            conn2 = get_conn()
            conn2.execute(
                "INSERT INTO alert_history (condition_id, matched_text) VALUES (?, ?)",
                (cid, message)
            )
            conn2.commit()
            conn2.close()

            results.append((chat_id, message))

    return results


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'check':
        results = check_conditions()
        for chat_id, msg in results:
            print(f"TO:{chat_id}")
            print(f"MSG:{msg}")
            print("---")
        if not results:
            print("✅ 매칭된 조건 없음")
    else:
        print("사용법: python alert_engine.py check")
