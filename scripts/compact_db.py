"""DB 경량화: 중복제거, VACUUM, ANALYZE"""
import sqlite3, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from data.database import DB_PATH

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

print("📦 DB Compact 시작...")
before = os.path.getsize(DB_PATH)
print(f"   Before: {before/1024/1024:.0f}MB")

# 1. 중복 거래 제거
cur.execute("""
    DELETE FROM apt_trade WHERE id NOT IN (
        SELECT MIN(id) FROM apt_trade 
        GROUP BY lawd_cd, apt_name, ROUND(area,1), floor, deal_date, price
    )
""")
dup = cur.rowcount
print(f"   중복 제거: {dup}건")

# 2. commit transaction from DELETE
conn.commit()

# 3. analyze
cur.execute("ANALYZE")

# 4. VACUUM (must be outside any transaction)
conn.commit()  # commit anything pending
cur.execute("VACUUM")

conn.close()
after = os.path.getsize(DB_PATH)
print(f"   After: {after/1024/1024:.0f}MB")
print(f"   절약: {(before-after)/1024/1024:.0f}MB ({(1-after/before)*100:.0f}%)")
print("✅ DB Compact 완료")
