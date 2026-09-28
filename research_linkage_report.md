# 연구 데이터 연결 검수 · 2026-09-24

## 적용 원칙

- 동일 회사·기간·통화·단위·회계기준의 원천 수정은 현재 계산으로 전달합니다.
- 원천 파일의 수정시각만 보지 않고 내용과 선택한 행을 확인합니다.
- 계산 도중 원천이 바뀌거나 기준·범위가 달라지면 이전 숫자의 재사용을 보류합니다.
- 정성적 의견은 새 수치만으로 자동 승인하지 않습니다. 검토 필요 상태와 기존 연구 빈티지를 표시합니다.
- 확정된 과거 프리뷰·리뷰·예측·평가 기록은 덮어쓰지 않습니다.

## 범위

등록 소비 경로 33개, 입력 의존성 191개. 공개 화면·경보·앙상블의 실제 독자별 검사를 적용합니다. 범용 임의 명령 실행기는 활성화하지 않습니다.

| 구분 | 경로 수 |
|---|---:|
| 기존 실행 시 재계산 | 20 |
| 읽을 때 현재 입력으로 계산 | 2 |
| 검토 후 새 연구 빈티지 필요 | 9 |
| 과거 기록 불변 | 2 |

## 경로별 동작과 한계

| 경로 | 동작 | 명시적 한계 |
|---|---|---|
| composite | 기존 실행 시 재계산 | No filesystem watcher or global refresh scheduler is installed by this registry. The reviewed composite.extra_sources selectors remain authoritative; catalogue entries are conservative whole-file dependencies. A stale cache is suppressed until the explicit composite CLI regenerates it. |
| conditional | 읽을 때 현재 입력으로 계산 | 35 admitted contracts/21 reconciliation checks are an initial current admission, not proof of original capture. Archive snapshots and PIT vintages remain immutable; no PV or investment-signal promotion. SANM and DY historical models have no invented required raw trade proxy. |
| tone_model | 읽을 때 현재 입력으로 계산 | Only the implemented IBIDEN conditional-financial adapter is admitted; other financial_dependency values hold. New or revised qualitative judgments require explicit review; old judgment text is not automatically rewritten. |
| universal_preview | 기존 실행 시 재계산 | Existing research documents and markdown are preserved, not numerically regenerated. Public release still requires parent-owned preservation checks, whole-site claim and deploy lock. |
| alerts_profile | 기존 실행 시 재계산 | No sender is enabled by this registry; deployment and notifications are separate. |
| alerts_snapshot_engine | 기존 실행 시 재계산 | Collector-specific sources and alert state/history are dynamic; sends remain separately authorized. A successful rebuild is not a new provider observation. Legacy records lacking valid receipts remain unavailable until a real successful producer run. |
| atlas | 기존 실행 시 재계산 | Dynamic bio data remains outside complete end-to-end source lineage; no claim that all Atlas prose is recomputed or re-reviewed. No remote sync is invoked. |
| U01 | 기존 실행 시 재계산 | Only cached FX is used; no network. Independent mem registry remains research-only. Quality is a source-pinned prior review, not a new model assessment. |
| U02 | 기존 실행 시 재계산 | Only cached FX is used; no network. Independent mem registry remains research-only. Quality is a source-pinned prior review, not a new model assessment. |
| U03 | 기존 실행 시 재계산 | Only cached FX is used; no network. Independent mem registry remains research-only. Quality is a source-pinned prior review, not a new model assessment. |
| ensemble_home | 기존 실행 시 재계산 | Fixed external Claude artifact links still reference external snapshots; local home regeneration cannot update those sites. Chronicle and cycle embeds retain their independently produced vintage. |
| ensemble_quality | 검토 후 새 연구 빈티지 필요 | No quality, BM or thesis model executor is implemented. A numeric input correction cannot approve new interpretation. |
| C01_facts | 기존 실행 시 재계산 | Only configured targets recompute; unmodeled ratios, narratives and BM assumptions require review. Approved E09 patches are not automatically approved by this registry. |
| C01_opinions | 검토 후 새 연구 빈티지 필요 | Static opinions and BM parameters are not deterministic numerical transforms. |
| C02_facts | 기존 실행 시 재계산 | In-place data/page writes use the chain refresh transaction, not the disabled generic executor. E09 patches require existing approval; rejected/missing evidence is not synthesized. C02 Dell GAAP and C03 Kioxia IFRS are separate from existing non-GAAP/ex-JV series. |
| C02_opinions | 검토 후 새 연구 빈티지 필요 | Static opinions and BM parameters are not deterministic numerical transforms. |
| C03_facts | 기존 실행 시 재계산 | In-place data/page writes use the chain refresh transaction, not the disabled generic executor. E09 patches require existing approval; rejected/missing evidence is not synthesized. C02 Dell GAAP and C03 Kioxia IFRS are separate from existing non-GAAP/ex-JV series. |
| C03_opinions | 검토 후 새 연구 빈티지 필요 | Static opinions and BM parameters are not deterministic numerical transforms. |
| C04_facts | 기존 실행 시 재계산 | Only configured targets recompute; unmodeled ratios, narratives and BM assumptions require review. Approved E09 patches are not automatically approved by this registry. |
| C04_opinions | 검토 후 새 연구 빈티지 필요 | Static opinions and BM parameters are not deterministic numerical transforms. |
| C05_facts | 기존 실행 시 재계산 | Only configured targets recompute; unmodeled ratios, narratives and BM assumptions require review. Approved E09 patches are not automatically approved by this registry. |
| C05_opinions | 검토 후 새 연구 빈티지 필요 | Static opinions and BM parameters are not deterministic numerical transforms. |
| C06_facts | 기존 실행 시 재계산 | Only configured targets recompute; unmodeled ratios, narratives and BM assumptions require review. Approved E09 patches are not automatically approved by this registry. |
| C06_opinions | 검토 후 새 연구 빈티지 필요 | Static opinions and BM parameters are not deterministic numerical transforms. |
| C08_export | 기존 실행 시 재계산 | Unmanifested legacy exports are not treated as current; same bytes preserve output mtime. Memory observations preserve native basis and numeric_promotion=false; official ledger is a separate export. |
| C08_foundry | 기존 실행 시 재계산 | Existing ex-JV memory scenarios and global wafer demand are not overwritten by IFRS joins. W04 copied research remains a separate assumption vintage. Production wrapper also contains network/publish operations and is not enabled here. |
| W04_copied_opinions | 검토 후 새 연구 빈티지 필요 | No current canonical financial readthrough is implemented here; a producer correction requires reviewed research revision. Existing fixed research asof and non-GAAP/ex-JV definitions must not be re-stamped as current by hashing alone. |
| grid | 기존 실행 시 재계산 | No automatic numerical re-extraction of corrected source reports or global DAG executor is implemented. Existing source watcher/review queue is separate; no extra watcher or data changes made here. |
| LUX | 기존 실행 시 재계산 | Existing canonical-root default remains; caller must use the intended root. Rights-unverified private observations cannot enter public scoring/forecasts. A new numerical fit still requires a valid producer/model receipt before downstream alerts accept it. |
| leadtime | 기존 실행 시 재계산 | No Dell/Kioxia financial dependency exists and none was invented. Existing weekly collection/release is separate; no active leadtime files, outputs or locks were touched. |
| recal | 검토 후 새 연구 빈티지 필요 | No automatic BM/quality approval or SSH dispatch is authorized by registry. Company profiles and explicit task inputs remain review evidence, not an executable mathematical dependency. |
| sealed_PV | 과거 기록 불변 | Source corrections never rewrite historical forecasts or evaluation evidence. |
| append_only_signals | 과거 기록 불변 | Network/source-specific collection is explicitly unimplemented in this runner. Issuer guidance is not analyst consensus; no generic writer is enabled. |

## 재무 예시

Dell의 FY2027 Q2 기간과 GAAP 영업이익을 별도 공식 원천 계약으로 연결했습니다. Kioxia의 IFRS 재무는 non-GAAP·ex-JV 연구 시나리오와 구분합니다. 회계기준이 다른 값을 자동으로 치환하지 않습니다.

## 프리뷰·포지션 계약

- 모든 등록 기업과 신규 등록 기업에 동일한 톤/반응 표시 계약을 적용합니다. 근거가 없는 계열은 결측으로 유지합니다.
- 회사별 5단계 톤, 통화·회계범위를 구분한 장기 가이던스 편향, 다음 이벤트의 연구 판단을 구분합니다.
- 발표 직후 첫 정규장 시가·종가 반응은 당시 확인 가능한 IV와 시가총액/비교집단 근거가 있어야 등급화합니다. 실현변동성을 IV로 대체하지 않습니다.
- 발표 당시 입력 빈티지와 시계열 외부검증이 충족되지 않으면 롱·숏과 사이즈를 보류합니다. 확신도를 임의로 채우지 않습니다.
- 이벤트당 연구 손실 예산은 순자산 0.5%입니다. 가격 갭·슬리피지로 실제 손실이 이를 초과할 수 있습니다.
- 현재 이비덴의 연구 판단은 NO_TRADE, 순자산 대비 사이즈 0%, 검증된 승률·확신도는 미확인입니다.

## 검수와 운영

내용 변경·삭제, 같은 수정시각의 숫자 변경, 다른 회사의 무관한 변경, 계산 중 변경, 캐시 재사용, 부분분기·오래된 관측, 생산 영수증 불일치, 비공개 관측의 공개 승격 차단을 검증합니다. 기존 정기 실행에 갱신 단계를 연결하며 별도 중복 스케줄을 만들지 않습니다.

범위 밖 사본·외부 앱·다른 연구 빈티지가 자동으로 모두 바뀌는 것은 아닙니다. 위 표의 W04 사본 연구, Atlas 일부 bio 동적 입력, 독립 시스템과 정성적 판단의 한계는 그대로 명시합니다.
