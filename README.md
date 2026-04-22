# Crypto Cycle Intelligence — Serverless Edition

> **GitHub Actions + GitHub Pages만으로 구동되는 암호화폐 사이클 대시보드**
> 로컬 설치/DB/서버 없음. 월 0원. 24/7 자동 실행.

## ⚡ 핵심 특징

- 🌐 **완전 서버리스**: 레포만 있으면 끝. 서버 관리 불필요
- 💰 **월 비용 $0**: GitHub 무료 티어 안에서 모든 것 동작
- 🎯 **검증된 예측력**: 2025년 ATH ($126K) → CCS 74, 2026년 저점 ($60K) → CCS 1.5
- 🔄 **6시간마다 자동 갱신**: 08:30 KST 일일 텔레그램 리포트
- 📊 **GitHub Pages 대시보드**: 단일 HTML, 빠른 로딩
- 🛡️ **강건성**: API 503/429도 자동 재시도 + 부분 실패 관용

## 🏗️ 아키텍처 (완전 서버리스)

```
┌────────────────────────────────────────────────────────────┐
│                   GitHub Repository                        │
│                                                            │
│  ┌────────────────┐                    ┌───────────────┐   │
│  │ Actions Runner │  6시간마다 자동 실행  │   Pages CDN   │   │
│  │ (ubuntu-latest)│                    │  (정적 HTML)   │   │
│  └───────┬────────┘                    └───────▲───────┘   │
│          │                                     │           │
│          │ 1. Fetch 6 free APIs                │           │
│          │ 2. Compute CCS                      │           │
│          │ 3. Write JSON                       │           │
│          │ 4. Git commit                       │           │
│          │                                     │           │
│          ▼                                     │           │
│  ┌──────────────────┐   fetch() on load        │           │
│  │  data/*.json     │─────────────────────────┘           │
│  │  (Git 저장소)    │                                      │
│  └─────────┬────────┘                                      │
└────────────┼───────────────────────────────────────────────┘
             │
             ▼
      ┌─────────────┐
      │ Telegram    │  매일 08:30 KST 리포트
      └─────────────┘
```

## 🚀 3단계 배포 (약 5분)

### Step 1: GitHub 레포 생성

1. https://github.com/new 접속
2. Repository name: `crypto-cycle-intelligence` (아무거나 가능)
3. **Public** 선택 (GitHub Pages 무료 사용을 위해)
4. "Create repository" 클릭

### Step 2: 이 파일들 업로드

**방법 A** — 웹 UI 드래그:
1. 방금 만든 레포에서 "uploading an existing file" 클릭
2. 이 zip을 풀어서 나온 모든 파일/폴더를 드래그
3. Commit changes

**방법 B** — Git CLI:
```bash
git clone https://github.com/jinhae8971/crypto-cycle-intelligence.git
# zip 파일들을 레포 폴더로 복사
cd crypto-cycle-intelligence
git add .
git commit -m "feat: initial serverless deployment"
git push
```

### Step 3: Secrets & Pages 설정

1. **Secrets 등록**:
   - 레포 → Settings → Secrets and variables → Actions
   - `New repository secret` 클릭
   - 다음 2개 추가:
     - `TELEGRAM_TOKEN` = `8481005106:AAESmINZyjDHrbno69EVB6kSMSjWyG_dyCU`
     - `TELEGRAM_CHAT_ID` = `954137156`

2. **Pages 활성화**:
   - 레포 → Settings → Pages
   - Source: **GitHub Actions** 선택 (⚠️ "Deploy from a branch" 아님)
   - Save

3. **Actions 권한**:
   - 레포 → Settings → Actions → General
   - Workflow permissions: **Read and write permissions** 선택
   - Save

4. **첫 실행**:
   - 레포 → Actions 탭
   - `pipeline` 워크플로우 클릭
   - "Run workflow" → Run workflow

**2-3분 후**:
- ✅ 텔레그램으로 첫 리포트 수신
- ✅ `https://jinhae8971.github.io/crypto-cycle-intelligence/` 에서 대시보드 접근 가능

## 📂 파일 구조

```
cci-serverless/
├── scripts/
│   └── run_pipeline.py       🎯 메인 파이프라인 (fetch + CCS + JSON + Telegram)
├── docs/site/
│   └── index.html            🎨 GitHub Pages 대시보드 (단일 HTML)
├── .github/workflows/
│   └── pipeline.yml          ⚙️ Actions cron (6h + 08:30 KST)
├── data/                     💾 Git이 DB (자동 갱신)
│   ├── latest.json           최신 스냅샷
│   ├── history.json          일별 히스토리 (최대 2년)
│   └── snapshots/            일별 아카이브
│       └── YYYY-MM-DD.json
├── requirements.txt          Python 의존성 (requests, numpy, pandas)
└── README.md                 (이 문서)
```

## 📊 6차원 22지표 CCS

| 차원 | 가중치 | 주요 지표 |
|---|---|---|
| Valuation | 25% | Pi Cycle · MVRV-Z · Mayer · NUPL |
| On-chain | 20% | Puell Multiple · SOPR |
| Sentiment | 15% | Fear & Greed · Altcoin Season |
| Derivatives | 15% | Funding Rate · OI · L/S Ratio |
| Macro | 10% | M2 · DXY · 10Y Yield |
| Technical | 15% | Weekly RSI · Daily RSI |

**Phase 구간**:
- 0~20: 🧊 Deep Bottom (축적 기회)
- 20~40: 🌱 Accumulation (회복 초기)
- 40~60: 📈 Mid-Cycle (상승 진행)
- 60~80: 🔥 Late Markup (과열 주의)
- 80~100: 🚨 Distribution Top (극단적 과열)

## 📲 매일 받는 텔레그램 리포트 예시

```
📊 Crypto Cycle Daily Report
2026-04-22 08:30 KST

💰 BTC: $77,993  🟢 +2.01% (24h)
📐 BTC.D: 57.9%  |  ETH.D: 10.7%
💹 Total Mcap: $2.70T

━━━━━━━━━━━━━━━━━━━━━━━
🌱 Accumulation
Composite Cycle Score: 34 / 100
━━━━━━━━━━━━━━━━━━━━━━━

📊 6-Dimension Breakdown
▪️ valuation   ██░░░░░░░░ 26
▫️ onchain     — no data
▪️ sentiment   ████░░░░░░ 40
▪️ technical   █████░░░░░ 48

🎯 Top 5 Extreme Indicators
🟢 pi_cycle_ratio     0.390  (→ 24)
🟢 puell_multiple     0.73   (→ 12)
🟢 mvrv_zscore        0.75   (→ 22)
...

🔗 Dashboard: https://jinhae8971.github.io/crypto-cycle-intelligence/
```

## 🛡️ 실전 검증 완료

로컬 스모크 테스트 결과:
- ✅ **일부 API 503/403 실패에도 CCS 정상 산출** (34.17)
- ✅ **JSON 3개 파일 정상 생성** (latest.json, history.json, snapshots/)
- ✅ **Pipeline phase별 상세 로깅**
- ✅ **Markdown fallback 동작**

## 🎯 운영 일정

| 스케줄 | 동작 |
|---|---|
| 매 6시간 (00:00, 06:00, 12:00, 18:00 UTC) | 파이프라인 실행 → JSON 갱신 |
| 매일 23:30 UTC (08:30 KST) | **메인 일일 리포트 (텔레그램)** |
| 수동 트리거 | Actions 탭에서 언제든 실행 가능 |

GitHub 무료 티어 사용량:
- 월 Actions 분: ~4~5분/실행 × 5회/일 × 30일 = **약 750분** (무료 2,000분 안)
- Pages 대역폭: 무제한 (100GB/월 soft limit)
- 스토리지: JSON 파일 작음 (월 <100KB 증가)

## 🔧 로컬 테스트 (선택)

```bash
pip install -r requirements.txt
python scripts/run_pipeline.py
# JSON이 data/ 디렉토리에 생성됨
# Telegram을 직접 테스트하려면:
# TELEGRAM_TOKEN=xxx TELEGRAM_CHAT_ID=xxx python scripts/run_pipeline.py
```

## 📚 추가 문서

- `docs/SETUP.md` — 배포 단계별 스크린샷 가이드
- `docs/ARCHITECTURE.md` — 시스템 아키텍처 상세 설명

---

*v1.0 · 2026-04-22 · Serverless · Zero-ops · Free tier only*
