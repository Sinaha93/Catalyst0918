# 월별 계획·실적 그래프 전용 시트 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use $superpower-subagents (recommended) or $superpower-executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking via update_plan.

**Goal:** 생성 보고서의 `월별 계획·실적` 시트에서 누적 중복표를 제거하고 그래프만 보이게 한다.

**Architecture:** `종합3(누적)`과 현재 확정 스냅샷으로 계산하는 기존 이력 흐름은 유지한다. 보고서 작성 마지막에 그래프 원본 행을 숨기고, 중복 범위를 비우며, 숨긴 원본도 차트가 표시하도록 설정하는 작은 COM 보조 함수를 호출한다.

**Tech Stack:** Python 3, pytest, Excel COM (`pywin32`), openpyxl 검증

---

### Task 1: 그래프 전용 정리 동작

**Files:**
- Create: `tests/test_report_trend_cleanup.py`
- Modify: `catalyst/reports.py`

- [ ] **Step 1: 실패하는 단위 테스트 작성**

```python
from catalyst.reports import simplify_trend_sheet


def test_simplify_trend_sheet_hides_sources_and_keeps_hidden_chart_data():
    ws = FakeWorksheet(chart_count=2)
    simplify_trend_sheet(ws)
    assert ws.cleared == ['B66:AT148']
    assert ws.hidden == [('30:148', True)]
    assert [chart.PlotVisibleOnly for chart in ws.charts] == [False, False]
```

- [ ] **Step 2: 테스트가 기능 부재로 실패하는지 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_report_trend_cleanup.py -q`

Expected: `ImportError: cannot import name 'simplify_trend_sheet'`

- [ ] **Step 3: 최소 구현 추가**

```python
def simplify_trend_sheet(ws):
    ws.Range('B66:AT148').ClearContents()
    ws.Rows('30:148').Hidden=True
    charts=ws.ChartObjects()
    for index in range(1,charts.Count+1):
        charts.Item(index).Chart.PlotVisibleOnly=False
```

`generate()`에서 `update_history(combined,30,2,None,...)` 직후 이 함수를 호출한다.

- [ ] **Step 4: 단위 테스트와 전체 테스트 실행**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_report_trend_cleanup.py -q`

Expected: 새 테스트 통과

Run: `.\.venv\Scripts\python.exe -m pytest -q`

Expected: 전체 테스트 통과

### Task 2: 실제 Excel 출력 검증

**Files:**
- Verify: `tools/verify_office.py`
- Verify: generated `outputs/*.xlsx` in the isolated temporary root

- [ ] **Step 1: 격리된 Office 보고서 생성**

Run: `.\.venv\Scripts\python.exe tools\verify_office.py`

Expected: 출력 파일 이름과 `catalyst_verify_*` 임시 루트가 출력된다.

- [ ] **Step 2: 생성 파일 구조 검사**

검사 항목:

```text
월별 계획·실적!B66:AT148 값 없음
월별 계획·실적 30:148행 숨김
차트 1개 이상 유지
종합3(누적) 시트 유지
Excel 수식 오류 없음
```

- [ ] **Step 3: 변경 파일 커밋**

```powershell
git add catalyst/reports.py tests/test_report_trend_cleanup.py docs/superpowers/plans/2026-09-22-trend-chart-only.md
git commit -m "feat: simplify monthly trend report to chart only"
```

## Verification

- 단위 테스트가 정리 범위와 차트 설정을 고정한다.
- 전체 pytest가 기존 보고서 흐름의 회귀를 확인한다.
- 설치된 Excel로 실제 산출물을 만들고 시트 구조를 검사한다.

## Next skill

`$superpower-executing-plans`
