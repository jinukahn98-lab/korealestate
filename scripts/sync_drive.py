#!/usr/bin/env python3
"""korealestate → Google Drive + LLM Wiki 자동 동기화"""
import os, shutil, sys
from datetime import datetime

PROJECT = "/Users/joark/projects/kr-realestate"
DRIVE = "/Users/joark/Google Drive/내 드라이브/11. 개인 업무/korealestate"
WIKI = "/Users/joark/wiki/concepts"

EXCLUDES = {'venv', '.git', '__pycache__', 'realestate.db', 'korealestate.db', '.coverage', 'node_modules', '.github'}
EXT_EXCLUDES = {'.pyc', '.pyo', '.db', '.sqlite', '.gz'}

def should_exclude(name):
    if name in EXCLUDES:
        return True
    for ext in EXT_EXCLUDES:
        if name.endswith(ext):
            return True
    return False

def sync_dir(src_root, dst_root, label):
    if not os.path.exists(dst_root):
        os.makedirs(dst_root)
        print(f"  📁 생성: {dst_root}")

    count = 0
    for root, dirs, files in os.walk(src_root):
        dirs[:] = [d for d in dirs if not should_exclude(d)]
        rel = os.path.relpath(root, src_root)
        dst_dir = os.path.join(dst_root, rel) if rel != '.' else dst_root
        os.makedirs(dst_dir, exist_ok=True)

        for f in files:
            if should_exclude(f):
                continue
            src = os.path.join(root, f)
            dst = os.path.join(dst_dir, f)

            src_stat = os.stat(src)
            dst_stat = os.stat(dst) if os.path.exists(dst) else None
            if dst_stat and dst_stat.st_mtime >= src_stat.st_mtime and dst_stat.st_size == src_stat.st_size:
                continue

            shutil.copy2(src, dst)
            count += 1

    if count > 0:
        print(f"  {label}: {count}개 파일 업데이트")
    return count

def sync_wiki():
    """LLM 위키 동기화 — 프로젝트 관련 wiki 문서 업데이트"""
    wiki_src = WIKI
    drive_wiki = os.path.join(DRIVE, "wiki")
    os.makedirs(drive_wiki, exist_ok=True)

    count = 0
    if os.path.exists(wiki_src):
        for f in os.listdir(wiki_src):
            src = os.path.join(wiki_src, f)
            dst = os.path.join(drive_wiki, f)
            if os.path.isfile(src):
                shutil.copy2(src, dst)
                count += 1
            elif os.path.isdir(src):
                dst_sub = os.path.join(drive_wiki, f)
                os.makedirs(dst_sub, exist_ok=True)
                for sf in os.listdir(src):
                    shutil.copy2(os.path.join(src, sf), os.path.join(dst_sub, sf))
                    count += 1

    if count > 0:
        print(f"  Wiki: {count}개 파일 업데이트")
    return count

def run():
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    print(f"🔄 동기화 시작 ({now})")

    total = 0
    total += sync_dir(PROJECT, DRIVE, "프로젝트")
    total += sync_wiki()
    print(f"✅ 완료: 총 {total}개 파일 동기화")
    return total

if __name__ == '__main__':
    sys.exit(0 if run() > 0 else 0)
