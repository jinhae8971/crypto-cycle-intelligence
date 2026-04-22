# 배포 가이드 (웹 UI만으로 완료)

PowerShell, Docker, 로컬 설치 전혀 필요 없습니다. 모든 과정이 GitHub 웹사이트에서 완료됩니다.

## 🎯 필요한 것

- GitHub 계정 (`jinhae8971`)
- Telegram bot token (이미 있음): `8481005106:...`
- 시간: **약 5분**

---

## Step 1: 새 레포지토리 생성 (1분)

1. https://github.com/new 접속
2. 다음과 같이 설정:
   - **Repository name**: `crypto-cycle-intelligence`
   - **Description**: "Free-API crypto cycle intelligence dashboard"
   - **Public** ← 중요! GitHub Pages 무료 사용을 위해
   - ⚠️ README / .gitignore 추가하지 말 것 (우리가 가져올 거니까)
3. "Create repository" 클릭

## Step 2: 파일 업로드 (1분)

### 방법 A: 드래그 앤 드롭 (가장 쉬움)

1. 방금 만든 빈 레포 페이지에서 **"uploading an existing file"** 링크 클릭
2. 이 프로젝트 폴더 전체를 드래그해서 업로드 영역에 놓기
   - `scripts/`, `docs/`, `.github/`, `requirements.txt`, `README.md`, `.gitignore` 모두 포함
3. 커밋 메시지: `feat: initial deployment`
4. "Commit changes" 클릭

### 방법 B: Git CLI

```bash
# 이 zip 파일을 풀어서 나온 폴더로 이동
cd cci-serverless

# 레포와 연결
git init
git add .
git commit -m "feat: initial deployment"
git branch -M main
git remote add origin https://github.com/jinhae8971/crypto-cycle-intelligence.git
git push -u origin main
```

## Step 3: Telegram Secrets 등록 (1분)

1. 레포 페이지에서 **Settings** 탭 클릭
2. 좌측 메뉴에서 **Secrets and variables** → **Actions**
3. **"New repository secret"** 클릭, 다음 2개 추가:

| Name | Secret |
|------|--------|
| `TELEGRAM_TOKEN` | `8481005106:AAESmINZyjDHrbno69EVB6kSMSjWyG_dyCU` |
| `TELEGRAM_CHAT_ID` | `954137156` |

## Step 4: GitHub Pages 활성화 (30초)

1. 레포 Settings → 좌측 메뉴 **Pages**
2. **Source** 드롭다운: **"GitHub Actions"** 선택
   - ⚠️ "Deploy from a branch" 아님! "GitHub Actions"여야 함
3. Save

## Step 5: Workflow 권한 설정 (30초)

1. 레포 Settings → 좌측 메뉴 **Actions** → **General**
2. **"Workflow permissions"** 섹션 스크롤
3. **"Read and write permissions"** 라디오 버튼 선택
4. Save

## Step 6: 첫 실행 (1분)

1. 레포의 **Actions** 탭 클릭
2. 좌측 워크플로우 목록에서 **"pipeline"** 클릭
3. 우측 상단 **"Run workflow"** 버튼 클릭
4. Branch: `main` 확인 → **Run workflow** (초록 버튼)

## ✅ 배포 완료 확인 (2-3분 대기)

1. Actions 탭에서 실행 진행 상황 관찰
2. 녹색 체크 표시 뜨면 성공
3. **확인 3가지**:

### ① Telegram 수신
스마트폰에 `📊 Crypto Cycle Daily Report`로 시작하는 메시지가 도착

### ② JSON 파일 생성
레포의 `data/` 폴더에 다음 3개 파일이 생성:
- `latest.json` — 최신 스냅샷
- `history.json` — 히스토리
- `snapshots/2026-04-22.json` — 일별 아카이브

### ③ 대시보드 접근
브라우저에서 다음 URL 접속:
```
https://jinhae8971.github.io/crypto-cycle-intelligence/
```

⏰ Pages는 첫 배포 시 **최대 10분** 걸릴 수 있습니다.

---

## 🔁 이후 자동 실행

- **6시간마다**: 00:00, 06:00, 12:00, 18:00 UTC에 자동 실행
- **08:30 KST**: 메인 일일 리포트 (23:30 UTC)
- **수동 실행**: Actions 탭에서 언제든 가능

대시보드 URL을 스마트폰 홈 화면에 추가하면 앱처럼 씁니다.

---

## 🛠️ 트러블슈팅

### Telegram 수신 안됨
- Secrets에 오타 없는지 확인
- Token 앞에 공백 없는지 확인
- Actions 로그에서 `Telegram sent` 문자열 확인

### Pages 접속 404
- Settings → Pages에서 Source가 "GitHub Actions"로 되어 있는지 확인
- 첫 배포 최대 10분 기다리기
- Pages URL 정확히: `https://jinhae8971.github.io/crypto-cycle-intelligence/` (슬래시 포함)

### "Workflow permissions" 에러
- Settings → Actions → General → "Read and write permissions" 확인
- 이거 안 되어 있으면 `git commit` 스텝에서 실패

### CCS 숫자가 너무 낮거나 일부 차원이 "no data"
- 정상입니다. 일부 API (BGeometrics)가 8/hr 제한이라 누락될 수 있음
- 24시간 내에 모든 지표가 한번씩은 수집됨
- 누적 데이터가 쌓이면 점점 정확해짐

### Actions 실패
- 로그에서 `❌ FATAL` 부분 확인
- 대부분 API 일시 장애 → 다음 스케줄에 자동 재시도
- 영속적 실패면 Telegram으로 자동 알림 수신

---

## 💡 운영 팁

### 대시보드 북마크
브라우저 즐겨찾기 또는 스마트폰 홈 화면에 추가.
Pages는 100% 정적이라 로딩 매우 빠름.

### 대시보드 URL을 안드로이드 앱처럼 추가
Chrome 모바일 → 메뉴 → "홈 화면에 추가" → 앱 아이콘 생성

### 변경 사항 배포
`scripts/run_pipeline.py` 또는 `docs/site/index.html`을 편집한 뒤
GitHub에 push하면 다음 스케줄에 자동 반영.

### 더 자주 실행하고 싶으면
`.github/workflows/pipeline.yml` 열어서:
```yaml
- cron: "0 */6 * * *"  →  - cron: "0 */2 * * *"  # 2시간마다
```
단, GitHub Actions 무료 2,000분/월 한도 주의.

### 알림 스팸 방지
매 6시간마다 텔레그램 날아오는 게 과하면,
`scripts/run_pipeline.py`의 `send_telegram()` 호출 조건 추가:
```python
# 08:30 KST에만 텔레그램 전송
from datetime import datetime
if datetime.utcnow().hour == 23 and 25 <= datetime.utcnow().minute <= 35:
    sent = send_telegram(...)
```

### 수동 갱신
대시보드 새 데이터 보고 싶으면 Actions 탭 → pipeline → "Run workflow"
2분 안에 갱신됨.
