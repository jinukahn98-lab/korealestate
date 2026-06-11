"""
스트림릿 클라우드용 부트스트랩 - DB 자동 다운로드
"""
import os
import urllib.request
import sqlite3
import gzip
import shutil

DB_PATH = os.path.join(os.path.dirname(__file__), 'realestate.db')
DB_GZ_URL = "https://github.com/jinukahn98-lab/korealestate/releases/download/v1.0/realestate.db.gz"


def ensure_db():
    """DB 없으면 다운로드"""
    if os.path.exists(DB_PATH) and os.path.getsize(DB_PATH) > 1000:
        return True

    print("📦 DB 파일 다운로드 중 (첫 실행 시만 필요)...")
    try:
        urllib.request.urlretrieve(DB_GZ_URL, DB_PATH + ".gz")
        with gzip.open(DB_PATH + ".gz", 'rb') as f_in:
            with open(DB_PATH, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        os.remove(DB_PATH + ".gz")
        print(f"✅ DB 다운로드 완료 ({os.path.getsize(DB_PATH)/1024/1024:.0f}MB)")
        return True
    except Exception as e:
        print(f"⚠️ DB 다운로드 실패: {e}")
        print("⚠️ 로컬에서만 동작합니다 (샘플 데이터로 실행)")
        return False


if __name__ == "__main__":
    ensure_db()
