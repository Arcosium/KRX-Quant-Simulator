# KRX Quant Simulator — 한국 주식 백테스팅 & 전략 시뮬레이터

> 2,773개 KRX 종목을 대상으로 5년치 재무·기술 지표 백테스팅을 돌리고, Gemini 2.5 Flash 가 결과를 한국어로 해석해주는 로컬 퀀트 워크벤치.

KRX Quant Simulator 는 한국 주식시장(KOSPI/KOSDAQ) 종목을 대상으로 한
**재무 필터링 + 기술적 분석 + 백테스팅 + AI 해설** 을 한 화면에서 돌릴 수 있는
Flask 기반 로컬 도구입니다.

- 2,773 KRX 종목 × 5년치 재무 데이터 (D-1y ~ D-5y)
- 24개 재무 지표 + 50개 이상의 기술 지표 (이동평균, RSI, MACD, 스토캐스틱, 볼린저, 캔들 패턴 27종)
- 10가지 포트폴리오 전략 (균등배분, 켈리, 리스크 패리티, 최소 분산, 최대 샤프, …)
- DART 공시 자동 반영 (유상증자 / 주식분할 / 배당 / 합병 등)
- Monte Carlo 시뮬레이션 + Gemini 자연어 해설

---

## 핵심 기능

### 1. 재무 필터링 (Financial Filter)
2,773 종목을 사용자가 정의한 재무 조건으로 스크리닝합니다.

```
PER < 10 AND ROE > 15 AND 부채비율 < 100
```

지원 지표:
- **수익성**: ROE, ROA, GPM, OPM, NPM, EBITDA
- **안전성**: 부채비율, 유동비율, 당좌비율, 자기자본비율
- **성장성**: 매출액증가율, 영업이익증가율, EPS증가율, BPS증가율
- **활동성**: 재고자산회전율, 총자산회전율
- **가치평가**: PER, PBR, PSR, PCR, EV/EBITDA, GP/A
- **현금흐름**: OCF, FCF

### 2. 전략 정의
자연어로 매수/매도 조건을 입력하면 Gemini 가 Python 식으로 변환합니다.

```
"5일 이평선이 20일 이평선을 골든크로스 + RSI < 30"
→ ma5 > ma20 AND ma5_yesterday <= ma20_yesterday AND rsi < 30
```

또는 직접 식을 작성:
```python
RSI * 3 < 30   # 3일 연속 RSI 30 미만 (preprocess_consecutive_logic)
양봉 AND 거래량 > 거래량_5일평균 * 2
적삼병 AND 시가총액 > 1000억
```

### 3. 백테스팅
1~5년 구간을 선택하고 10가지 포트폴리오 전략 중 선택:

| 전략 | 설명 |
|---|---|
| `equal_weight` | 현금 균등 배분 |
| `market_cap` | 시가총액 가중 |
| `momentum_weight` | 최근 수익률 가중 |
| `risk_parity` | 변동성 역수 가중 |
| `inverse_volatility` | 변동성 역수 가중 (단순) |
| `kelly_criterion` | Kelly 공식 기반 동적 |
| `min_variance` | 최소 분산 포트폴리오 |
| `max_sharpe` | 최대 샤프 포트폴리오 |
| `dynamic_asset` | 동적 자산배분 |
| `all_in` | 전량 1종목 집중 |

수수료(0.015%) + 거래세(0.18%) 적용 옵션.

### 4. 결과
- **성과 지표**: CAGR, MDD, Sharpe, 승률, Profit Factor, KOSPI 벤치마크 대비
- **트레이드 히스토리**: CSV 저장 (`Memories/`)
- **그래프**: matplotlib PNG (자산 곡선 vs B&H vs KOSPI)
- **HTML 리포트**: Tailwind + Chart.js
- **AI 해설**: Gemini 2.5 Flash 가 결과를 한국어로 분석 ("이 전략은 약세장에서 MDD 가 컸지만 …")
- **Monte Carlo**: 1,000개 경로 시뮬레이션 → 5/50/95 percentile

## 빠른 시작

### 1. 의존성

```bash
pip install flask flask-cors pandas numpy google-generativeai pytz \
            matplotlib beautifulsoup4 requests opendartreader
```

### 2. 환경변수

```bash
export GEMINI_API_KEY=AIza...    # AI 해설 / 자연어 → 식 변환에 필요
export DART_API_KEY=...          # (선택) DART 공시 데이터에 필요
export APP_PORT=7861             # (선택) 미설정시 7861~7898 자동 탐색
```

### 3. 실행

```bash
python app.py
# [KRX Quant Simulator] Starting on port 7861...
# 브라우저에서 http://localhost:7861 접속
```

## 디렉터리 구조

```
KRX Quant Simulator/
├── app.py                      # Flask REST API (28KB)
│                                 라우트: /backtest, /filter, /generate,
│                                        /memories, /status, /progress
├── quant_logic.py              # 핵심 백테스팅 엔진 (80KB)
│                                 클래스: DBManager, CrawlerUtil,
│                                        TechnicalAnalysis, QuantLogic
├── templates/
│   └── index.html              # 5탭 UI (config / fast backtest / filter /
│                                  strategy / results) Tailwind + Chart.js
├── D-{1,2,3,4,5}y_data.csv     # 2020~2024 연도별 재무 스냅샷 (각 ~470KB)
├── logic.csv                   # 24개 지표 정의 + 입력 예시
├── Memories/                   # 백테스트 결과 (HTML / CSV / PNG)
│   └── stock_cache.db          # SQLite 가격/투자자 캐시
├── docs_cache/                 # OpenDartReader 기업 코드 캐시 (~8.4MB)
├── 사용설명서.pdf              # 한국어 매뉴얼
└── app.log
```

## 데이터 (`D-1y_data.csv`)

2,773 종목 × 28 컬럼:
```
종목코드,기업명,ROE,ROA,GPM,OPM,NPM,EBITDA,부채비율,유동비율,당좌비율,
자기자본비율,매출액증가율,영업이익증가율,EPS증가율,BPS증가율,
재고자산회전율,총자산회전율,PER,PBR,PSR,PCR,EV/EBITDA,GP/A,
OCF,FCF,주가,시가총액

000010,신한은행,9.82,0.63,0.0,0.0,0.0,53096.94,1452.43,...
```

가격 / 투자자(외인/기관/개인) / 거래량 데이터는 네이버 금융에서 실시간 스크레이핑 후
SQLite 에 캐시 (`Memories/stock_cache.db`).

## 캔들 패턴 (27종 지원)

```
양봉 / 음봉 / 장대양봉 / 장대음봉
십자캔들(Doji) / 망치형(Hammer) / 역망치형 / 유성형
비석형도지(Gravestone) / 잠자리도지(Dragonfly)
상승장악형(Bullish Engulfing) / 하락장악형(Bearish Engulfing)
관통형(Piercing) / 흑운형(Dark Cloud)
적삼병(Three Red Soldiers) / 흑삼병(Three Black Crows)
상한가 / 하한가 / 52주신고가 / 52주신저가
```

DART 공시 이벤트도 식에서 사용 가능:
```
유상증자, 무상증자, 자사주취득, 자사주처분, 주식분할, 감자,
합병, 전환사채, 신주인수권부사채, 배당락
```

## API 엔드포인트

| Path | Method | 설명 |
|---|---|---|
| `/` | GET | 메인 UI |
| `/backtest` | POST | 풀 백테스팅 실행 |
| `/fast_backtest_parse` | POST | 자연어 → 구조화된 전략 |
| `/filter` | POST | 재무 필터링 |
| `/generate` | POST | 자연어 → 매수/매도 식 (Gemini) |
| `/progress` | GET | 진행률 (long-polling) |
| `/memories` | GET | 과거 백테스트 결과 목록 |
| `/status` | GET | 헬스체크 |

## 운영 노트

- **버전**: `1.3.0-local-ai`
- **시간대**: 모든 timestamp 는 `Asia/Seoul` (pytz)
- **첫 실행 시**: DART 기업 코드 캐시 (~8.4MB) 자동 다운로드 → `docs_cache/`
- **주의**: Naver Finance 스크레이핑은 IP rate limit 가능 — 캐시를 적극 활용

## 한계

- **백테스트 ≠ 실거래**: 슬리피지, 가격충돌, 호가 시뮬레이션 없음
- **재무 데이터는 연 단위**: 분기/월 단위 정밀도 X
- **DART 공시 의존**: 비상장사 / 외국 상장 종목 미지원
- **로컬 전용**: 멀티유저 / 동시 백테스트 비대응

---

## English Summary

Local quant workbench for the Korea Exchange (KRX). Backtests across 2,773
stocks and 5 years of financial data with 24 financial metrics, 50+ technical
indicators, 27 candlestick patterns, and 10 portfolio allocation strategies.
Integrates DART (corporate filings) for events like rights issues and splits,
runs Monte Carlo projections, and uses Gemini 2.5 Flash for natural-language
strategy authoring and post-hoc result analysis.

**Stack:** Flask · pandas · numpy · BeautifulSoup · OpenDartReader · Google Gemini API · Tailwind · Chart.js · matplotlib

## Disclaimer

For research and education only. Past performance from backtests does not
guarantee future returns. Do not treat the AI-generated commentary as
investment advice.
