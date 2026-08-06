---
title: korealestate v3.0
emoji: 🏠
colorFrom: blue
colorTo: green
sdk: docker
pinned: false
---

# 🏠 한국 부동산 분석 시스템 v3.0

13개 요소, 6개 외부 소스 통합 스코어러.
- 상관계수 0.800 (ML 최적화 0.876)
- ScorerV3: 가격모멘텀/중기추세/전세가율/KB수급지수/개발호재/공급리스크/학군/거시환경/뉴스감성

## Deployment

Cloudflare Worker is the primary deployment. Pushes to `main` that change `cf-worker/**` (or its deployment workflow) run `.github/workflows/cloudflare-worker.yml`, which installs dependencies, runs configured type checks and tests, and deploys with Wrangler.

The documented default Worker URL is:

```text
https://kr-realestate.joark-stock.workers.dev
```

Run public endpoint smoke checks after deployment (or pass another Worker URL as the first argument):

```bash
bash cf-worker/scripts/smoke_remote.sh
# bash cf-worker/scripts/smoke_remote.sh https://your-worker.workers.dev
```

### GitHub Actions secrets

Configure these repository secret **names** for the Cloudflare workflows. Do not commit their values:

```text
CLOUDFLARE_API_TOKEN
CLOUDFLARE_ACCOUNT_ID
```

### Controlled D1 schema and data refresh

Remote D1 schema changes never run on a normal push. Use the **Apply remote D1 migrations** workflow (`.github/workflows/d1-data-sync.yml`) through GitHub Actions and enter `SYNC` exactly for `confirm_remote_d1`.

Aggregate data is deliberately separate from GitHub code deployment: the local exporter produces public aggregate table dumps, uploads them to the configured Google Drive folder, and the Worker Cron applies changed files. This keeps local SQLite source data and generated SQL out of GitHub and avoids a GitHub runner rewriting D1 without access to the source database.

### Local Streamlit fallback

For local development or a fallback UI, install the Python dependencies and run Streamlit locally:

```bash
python3 -m pip install -r requirements.txt
streamlit run app_v3.py
```

🔗 [GitHub Repository](https://github.com/jinukahn98-lab/korealestate)
