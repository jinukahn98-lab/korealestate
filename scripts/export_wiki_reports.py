#!/usr/bin/env python3
"""Export ~/wiki/concepts/{current-policy,market-trends,development-projects}.md → data/external_reports/"""
import json, os, re, sys
from pathlib import Path
from datetime import datetime

WIKI_DIR = Path(os.path.expanduser("~/wiki/concepts"))
EXPORT_DIR = Path(__file__).parent.parent / "data" / "external_reports"
PAGES = {
    "current-policy": "정책 현황",
    "market-trends": "시장 동향",
    "development-projects": "개발 호재",
}

def parse_markdown(text: str) -> dict:
    """Parse markdown with YAML frontmatter into sections"""
    result = {"frontmatter": {}, "sections": [], "raw": text}

    # Extract frontmatter
    fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', text, re.DOTALL)
    if fm_match:
        for line in fm_match.group(1).strip().split('\n'):
            if ':' in line:
                k, v = line.split(':', 1)
                result["frontmatter"][k.strip()] = v.strip().strip('"').strip("'")
        body = text[fm_match.end():]
    else:
        body = text

    # Parse sections by ## headers
    sections = re.split(r'\n(?=##\s)', body)
    for sec in sections:
        sec = sec.strip()
        if not sec:
            continue
        lines = sec.split('\n')
        title = lines[0].replace('##', '').strip() if lines[0].startswith('##') else '(서문)'
        content = '\n'.join(lines[1:]).strip() if len(lines) > 1 else ''
        if content:
            result["sections"].append({"title": title, "content": content[:500]})  # trim for display
    return result

def export():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {"exported_at": datetime.now().isoformat(), "pages": {}}

    for filename, label in PAGES.items():
        md_path = WIKI_DIR / f"{filename}.md"
        if not md_path.exists():
            print(f"  ⚠️  {md_path.name} 없음, 스킵")
            continue

        text = md_path.read_text(encoding='utf-8')
        parsed = parse_markdown(text)

        # Save JSON
        json_path = EXPORT_DIR / f"{filename}.json"
        json_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"  ✅ {json_path.name} ({len(text)} bytes, {len(parsed['sections'])} sections)")

        manifest["pages"][filename] = {
            "label": label,
            "size": len(text),
            "sections": len(parsed["sections"]),
            "updated": parsed["frontmatter"].get("updated", "unknown"),
        }

    # Save manifest
    (EXPORT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"  ✅ manifest.json ({len(manifest['pages'])} pages)")
    print(f"\n📦 {EXPORT_DIR} 내보내기 완료")

if __name__ == "__main__":
    export()
