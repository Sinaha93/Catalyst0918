import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  LayoutDashboard,
  Files,
  Database,
  TriangleAlert,
  FolderClock,
  ArrowUpRight,
  RefreshCw,
  Upload,
  Check,
  ChevronRight,
  Download,
  Search,
  X,
  Activity,
} from "lucide-react";
import "./style.css";

type Row = Record<string, any>;
const labels: Row = {
  part: "품번 마스터",
  price: "단가",
  receipt: "입고",
  shipment: "출하",
  settlement: "정산",
  opening: "기초 이월",
  plan: "계획",
  adjustment: "수량 조정",
};
const fields: Row = {
  part: "품번",
  customer: "거래처",
  date: "일자 / 적용일",
  quantity: "수량",
  price: "단가(원)",
  amount: "금액(원)",
  note: "사유 / 비고",
};
const fmt = (n: any) =>
  n === null || n === undefined
    ? "—"
    : Number(n).toLocaleString("ko-KR", { maximumFractionDigits: 2 });
async function api(url: string, data?: unknown) {
  const r = await fetch(
    "/api" + url,
    data === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data),
        },
  );
  const v = await r.json();
  if (!r.ok)
    throw Error(
      typeof v.detail === "string" ? v.detail : JSON.stringify(v.detail),
    );
  return v;
}
function App() {
  const [tab, setTab] = useState(0),
    [period, setPeriod] = useState("2026-08"),
    [status, setStatus] = useState<Row>({}),
    [sources, setSources] = useState<Row[]>([]),
    [records, setRecords] = useState<Row[]>([]),
    [runs, setRuns] = useState<Row[]>([]),
    [issues, setIssues] = useState<Row[]>([]),
    [outputs, setOutputs] = useState<string[]>([]),
    [preview, setPreview] = useState<Row | null>(null),
    [busy, setBusy] = useState(""),
    [toast, setToast] = useState(""),
    [modal, setModal] = useState<Row | null>(null),
    [search, setSearch] = useState("");
  const [mapping, setMapping] = useState<Row | null>(null),
    [mapped, setMapped] = useState<Row | null>(null),
    [manual, setManual] = useState<Row>({
      kind: "price",
      date: "2026-08-01",
      part: "",
      customer: "",
      quantity: "",
      price: "",
      amount: "",
      note: "",
    }),
    [reason, setReason] = useState(""),
    [paste, setPaste] = useState("");
  async function reload() {
    const [s, f, r, u, i, o, p] = await Promise.all([
      api("/status"),
      api("/sources"),
      api("/records"),
      api("/runs"),
      api("/issues"),
      api("/outputs"),
      api("/closing/" + period),
    ]);
    setStatus(s);
    setSources(f);
    setRecords(r);
    setRuns(u);
    setIssues(i);
    setOutputs(o);
    setPreview(p);
  }
  useEffect(() => {
    reload().catch((e) => setToast(e.message));
  }, [period]);
  async function action(fn: () => Promise<any>, message = "처리 중") {
    setBusy(message);
    setToast("");
    try {
      let result = await fn();
      if (result?.job_id) {
        for (;;) {
          await new Promise((r) => setTimeout(r, 600));
          const j = await api("/jobs/" + result.job_id);
          if (j.state === "failed") throw Error(j.message);
          if (j.state === "done") {
            result = JSON.parse(j.result);
            break;
          }
        }
      }
      await reload();
      setToast("완료했습니다");
      return result;
    } catch (e: any) {
      setToast(e.message);
    } finally {
      setBusy("");
    }
  }
  async function upload(files: FileList | null) {
    if (!files) return;
    await action(async () => {
      for (const f of files) {
        const body = new FormData();
        body.append("file", f);
        const r = await fetch("/api/upload", { method: "POST", body });
        const j = await r.json();
        if (!r.ok) throw Error(j.detail);
        for (;;) {
          await new Promise((r) => setTimeout(r, 500));
          const p = await api("/jobs/" + j.job_id);
          if (p.state === "failed") throw Error(p.message);
          if (p.state === "done") break;
        }
      }
    }, "파일을 분석하고 있습니다");
  }
  function openMapping(source: Row) {
    const sh = source.meta.sheets?.[0];
    setMapping({
      id: source.id,
      name: source.name,
      sheet: sh?.name || "",
      header_row: sh?.headers?.[0]?.row || 1,
      kind: "receipt",
      scope: "",
      mode: "replace",
      columns: {},
      defaults: {},
    });
    setMapped(null);
  }
  const selectedSource = sources.find((s) => s.id === mapping?.id),
    selectedSheet = selectedSource?.meta.sheets?.find(
      (s: Row) => s.name === mapping?.sheet,
    ),
    headers =
      selectedSheet?.headers?.find(
        (h: Row) => h.row === Number(mapping?.header_row),
      )?.cells || [];
  const pages = [
    "마감 현황",
    "자료 등록",
    "마스터 관리",
    "확인 필요",
    "보고서·이력",
  ];
  const Icons = [LayoutDashboard, Files, Database, TriangleAlert, FolderClock];
  const count = (preview?.issues?.length || 0) + status.pending;
  return (
    <div className="shell">
      <aside>
        <div className="brand">
          <div className="brandIcon">
            <Activity size={23} />
          </div>
          <div>
            CATALYST<span>촉매 마감 관리</span>
          </div>
        </div>
        <div className="workspace">
          WORKSPACE <span>로컬</span>
        </div>
        <nav>
          {pages.map((p, i) => {
            const Icon = Icons[i];
            return (
              <button
                key={p}
                className={tab === i ? "active" : ""}
                onClick={() => {
                  setTab(i);
                  setSearch("");
                }}
              >
                <Icon size={19} />
                {p}
                {i === 3 && count > 0 && <b>{count}</b>}
              </button>
            );
          })}
        </nav>
        <div className="sidebarBottom">
          <span className="dot" />내 PC에 저장 중
          <p>
            입력 자료부터 보고서까지
            <br />
            월별 이력을 안전하게 관리합니다.
          </p>
          <button onClick={() => action(() => api("/backups", {}), "백업 중")}>
            데이터 백업 <ArrowUpRight size={15} />
          </button>
          <button onClick={()=>setModal({title:'프로그램 종료',shutdown:true})}>프로그램 종료</button>
        </div>
      </aside>
      <main>
        <header>
          <span>
            업무 관리 <ChevronRight size={14} /> {pages[tab]}
          </span>
          <div>
            <span className="local">LOCAL WORKSPACE</span>
            <div className="avatar">나</div>
          </div>
        </header>
        <div className="content">
          <section className="pageTitle">
            <div>
              <div className="eyebrow">MONTHLY CLOSING</div>
              <h1>{pages[tab]}</h1>
              <p>
                {
                  [
                    "이번 달 자료를 확인하고 마감을 준비하세요.",
                    "엑셀 파일을 등록하면 구조를 확인하고 반영합니다.",
                    "품번과 적용일별 단가, 직접 입력값을 관리합니다.",
                    "반영을 막는 항목과 그 근거를 확인하세요.",
                    "확정한 마감과 생성된 보고서를 확인하세요.",
                  ][tab]
                }
              </p>
            </div>
            <div className="actions">
              <input
                aria-label="마감월"
                type="month"
                value={period}
                onChange={(e) => setPeriod(e.target.value)}
              />
              <button
                className="iconBtn"
                aria-label="새로고침"
                onClick={() => action(reload, "새로고침 중")}
              >
                <RefreshCw size={18} />
              </button>
            </div>
          </section>
          {toast && (
            <div role="status" className="notice">
              <span>{toast}</span>
              <button aria-label="알림 닫기" onClick={() => setToast("")}>
                <X size={16} />
              </button>
            </div>
          )}
          {busy && (
            <div className="progress">
              <span className="spinner" />
              {busy}
            </div>
          )}
          {tab === 0 && (
            <>
              <div className="stats">
                {[
                  ["등록한 자료", status.sources || 0, "원본 파일"],
                  ["반영한 데이터", status.records || 0, "활성 데이터 행"],
                  ["확인할 자료", status.pending || 0, "열 연결·검토 필요"],
                  ["확정한 마감", status.runs || 0, "버전별 보관"],
                ].map(([label, value, hint], i) => (
                  <div className="stat" key={label}>
                    <span>{label}</span>
                    <strong className={i === 2 ? "orange" : ""}>
                      {fmt(value)}
                      <small>건</small>
                    </strong>
                    <p>{hint}</p>
                  </div>
                ))}
              </div>
              <section className="flow">
                <div>
                  <h2>{period.split("-")[1]}월 마감 진행</h2>
                  <p>필요한 자료를 반영하고 결과를 확인하세요.</p>
                </div>
                <div className="steps">
                  {["자료 등록", "검증·반영", "결과 확인", "마감 확정"].map(
                    (s, i) => (
                      <div key={s} className={[status.sources>0,status.records>0,preview?.ready,runs.some(r=>r.period===period)][i] ? "current" : ""}>
                        <b>{[status.sources>0,status.records>0,preview?.ready,runs.some(r=>r.period===period)][i] ? <Check size={15} /> : i + 1}</b>
                        <span>{s}</span>
                        {i < 3 && <i />}
                      </div>
                    ),
                  )}
                </div>
              </section>
              <div className="columns">
                <section className="panel wide">
                  <div className="panelTitle">
                    <h2>거래처별 마감 현황</h2>
                    <button disabled={!!busy} onClick={()=>action(async()=>{const b=await api('/baseline/'+period);setModal({title:'기존 마감 결과 비교',rows:b.rows,message:b.message});})}>기존 결과와 비교</button>
                  </div>
                  {preview?.customers?.length ? (
                    <table>
                      <thead>
                        <tr>
                          <th>거래처</th>
                          <th>전월 이월</th>
                          <th>당월 입고</th>
                          <th>당월 정산</th>
                          <th>미결</th>
                        </tr>
                      </thead>
                      <tbody>
                        {preview.customers.map((r: Row) => (
                          <tr
                            key={r.customer}
                            onClick={() =>
                              setModal({
                                title: r.customer + " 계산 근거",
                                rows: preview.details.filter(
                                  (d: Row) => d.customer === r.customer,
                                ),
                              })
                            }
                          >
                            <td>{r.customer}</td>
                            {[
                              "opening",
                              "receipt",
                              "settlement",
                              "closing",
                            ].map((k) => (
                              <td key={k}>{fmt(r[k])}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <div className="empty">
                      <Database size={30} />
                      <h3>마감 계산을 위한 자료를 등록하세요</h3>
                      <p>
                        기존 보고서는 비교 기준으로 보관됩니다.
                        <br />
                        입고·정산·이월 자료를 반영하면 현황이 나타납니다.
                      </p>
                      <button className="primary" onClick={() => setTab(1)}>
                        자료 등록하기 <ArrowUpRight size={16} />
                      </button>
                    </div>
                  )}
                </section>
                <section className="panel">
                  <div className="panelTitle">
                    <h2>다음 할 일</h2>
                    <span className="tag">
                      {preview?.issues?.length || 0}건
                    </span>
                  </div>
                  <div className="tasks">
                    {preview?.issues?.slice(0, 4).map((i: Row, n: number) => (
                      <button key={n} onClick={() => setTab(3)}>
                        <TriangleAlert size={17} />
                        <span>{i.message}</span>
                        <ChevronRight size={15} />
                      </button>
                    ))}
                  </div>
                  <button
                    className="primary full"
                    disabled={busy !== "" || !preview?.ready}
                    onClick={() =>
                      setModal({ title: "마감 확정", confirm: true })
                    }
                  >
                    마감 확정하기
                  </button>
                  <p className="help">
                    미해결 항목을 처리하면 확정할 수 있습니다.
                  </p>
                </section>
              </div>
              <section className="panel">
                <div className="panelTitle">
                  <h2>최근 등록한 자료</h2>
                  <button className="textBtn" onClick={() => setTab(1)}>
                    전체 보기 <ArrowUpRight size={14} />
                  </button>
                </div>
                <FileTable items={sources.slice(0, 4)} onMap={openMapping} />
              </section>
            </>
          )}
          {tab === 1 && (
            <>
              <label
                className="dropzone"
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  upload(e.dataTransfer.files);
                }}
              >
                <Upload size={28} />
                <h2>여기에 파일을 놓거나 클릭해 선택하세요</h2>
                <p>XLSX · CSV / 파일당 최대 100MB</p>
                <input
                  type="file"
                  multiple
                  accept=".xlsx,.csv"
                  onChange={(e) => upload(e.target.files)}
                />
              </label>
              <div className="folderLine">
                <span>자동 수집 폴더: {status.input_folder}</span>
                <button
                  disabled={!!busy}
                  onClick={() =>
                    action(
                      () => api("/scan", {}),
                      "폴더의 자료를 검사하고 있습니다",
                    )
                  }
                >
                  <RefreshCw size={15} />
                  기존 폴더 자료 읽기
                </button>
              </div>
              <section className="panel">
                <div className="panelTitle">
                  <h2>입력 자료</h2>
                  <span>{sources.length}개 파일</span>
                </div>
                <FileTable items={sources} onMap={openMapping} />
              </section>
            </>
          )}
          {tab === 2 && (
            <>
              <PartLinks onSave={reload}/>
              <PriceEstimates period={period} details={preview?.details || []} onSave={reload}/>
              <section className="panel formPanel">
                <div className="panelTitle">
                  <h2>직접 입력</h2>
                  <span>기록과 적용일을 함께 보관합니다</span>
                </div>
                <div className="formGrid">
                  <label>
                    구분
                    <select
                      value={manual.kind}
                      onChange={(e) =>
                        setManual({ ...manual, kind: e.target.value })
                      }
                    >
                      {Object.entries(labels).map(([k, v]) => (
                        <option key={k} value={k}>
                          {v}
                        </option>
                      ))}
                    </select>
                  </label>
                  {Object.entries(fields).map(([k, v]) => (
                    <label key={k}>
                      {v}
                      <input
                        type={k === "date" ? "date" : "text"}
                        value={manual[k]}
                        onChange={(e) =>
                          setManual({ ...manual, [k]: e.target.value })
                        }
                      />
                    </label>
                  ))}
                  <label>
                    입력 사유
                    <input
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                    />
                  </label>
                </div>
                <div className="formFooter">
                  <button
                    disabled={!!busy}
                    className="primary"
                    onClick={() =>
                      action(
                        () =>
                          api("/records", {
                            scope: "직접입력:" + manual.kind,
                            mode: "append",
                            reason,
                            rows: [manual],
                          }),
                        "직접 입력 반영 중",
                      )
                    }
                  >
                    입력값 반영
                  </button>
                </div>
                <details>
                  <summary>엑셀 표 붙여넣기</summary>
                  <p className="help">
                    열 순서: 품번 / 거래처 / 일자 / 수량 / 단가 / 금액 / 비고.
                    제목 행 없이 붙여넣습니다. 위에서 선택한 구분과 입력 사유를
                    사용합니다.
                  </p>
                  <textarea
                    value={paste}
                    onChange={(e) => setPaste(e.target.value)}
                    placeholder="엑셀에서 복사한 행을 붙여넣으세요"
                  />
                  <button
                    onClick={() =>
                      action(() =>
                        api("/records", {
                          scope: "직접입력:" + manual.kind,
                          mode: "append",
                          reason,
                          rows: paste
                            .trim()
                            .split("\n")
                            .map((line) => {
                              const cells = line.split("\t");
                              return {
                                kind: manual.kind,
                                ...Object.fromEntries(
                                  Object.keys(fields).map((k, i) => [
                                    k,
                                    cells[i] || "",
                                  ]),
                                ),
                              };
                            }),
                        }),
                      )
                    }
                  >
                    붙여넣은 자료 반영
                  </button>
                </details>
              </section>
              <section className="panel">
                <div className="panelTitle">
                  <h2>반영 데이터</h2>
                  <div className="search">
                    <Search size={16} />
                    <input
                      placeholder="품번·거래처 검색"
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                    />
                  </div>
                </div>
                <div className="scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>구분</th>
                        <th>품번</th>
                        <th>거래처</th>
                        <th>적용일</th>
                        <th>수량</th>
                        <th>단가</th>
                        <th>금액</th>
                        <th>근거</th>
                      </tr>
                    </thead>
                    <tbody>
                      {records
                        .filter((r) => JSON.stringify(r).includes(search))
                        .map((r) => (
                          <tr key={r.id}>
                            <td>{labels[r.kind]}</td>
                            <td>{r.part}</td>
                            <td>{r.customer || "공통"}</td>
                            <td>{r.date}</td>
                            <td>{fmt(r.quantity)}</td>
                            <td>{fmt(r.price)}</td>
                            <td>{fmt(r.amount)}</td>
                            <td>
                              <button
                                onClick={() =>
                                  setModal({
                                    title: "원본 근거",
                                    rows: [JSON.parse(r.provenance)],
                                  })
                                }
                              >
                                보기
                              </button>
                              <button onClick={()=>setModal({title:'입력값 수정',edit:{...r},reason:''})}>수정</button>
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                  {!records.length && (
                    <div className="empty compact">
                      반영된 데이터가 없습니다.
                    </div>
                  )}
                </div>
              </section>
            </>
          )}
          {tab === 3 && (
            <section className="panel">
              <div className="panelTitle">
                <h2>확인할 항목</h2>
                <span>오류를 눌러 근거를 확인하세요</span>
              </div>
              {[...(preview?.issues || []), ...issues].map(
                (i: Row, n: number) => (
                  <button
                    className="issue"
                    key={n}
                    onClick={() => setModal({ title: i.message, rows: [i] })}
                  >
                    <TriangleAlert size={20} />
                    <div>
                      <strong>{i.message}</strong>
                      <p>
                        {i.code === "import"
                          ? "원본의 열 연결과 입력값을 확인해주세요."
                          : "자료를 보완하면 다음 계산에 자동 반영됩니다."}
                      </p>
                    </div>
                    <ChevronRight size={18} />
                  </button>
                ),
              )}
              {sources
                .filter((s) => s.status === "pending")
                .map((s) => (
                  <button
                    className="issue"
                    key={"s" + s.id}
                    onClick={() => openMapping(s)}
                  >
                    <Files size={20} />
                    <div>
                      <strong>{s.name}</strong>
                      <p>처음 받는 자료입니다. 열 연결을 지정해주세요.</p>
                    </div>
                    <ChevronRight size={18} />
                  </button>
                ))}
            </section>
          )}
          {tab === 4 && (
            <>
              <section className="panel">
                <div className="panelTitle">
                  <h2>확정 마감</h2>
                  <button
                    onClick={() =>
                      action(async () => {
                        const b = await api("/backups");
                        setModal({ title: "백업 복원", backups: b });
                      })
                    }
                  >
                    백업·복원
                  </button>
                </div>
                {runs.map((r) => (
                  <div className="run" key={r.id}>
                    <div>
                      <strong>
                        {r.period} 마감{" "}
                        <span className="tag">v{r.version}</span>
                      </strong>
                      <p>{r.created}</p>
                    </div>
                    <div className="actions">
                      <button
                        onClick={() =>
                          action(async () => {
                            const d = await api("/runs/" + r.id);
                            setModal({
                              title: "확정 결과",
                              rows: d.snapshot.customers,
                            });
                          })
                        }
                      >
                        결과 보기
                      </button>
                      <button
                        className="primary"
                        disabled={!!busy}
                        onClick={() =>
                          action(
                            () => api("/runs/" + r.id + "/export", {}),
                            "엑셀 보고서 생성 중",
                          )
                        }
                      >
                        엑셀 생성
                      </button>
                    </div>
                  </div>
                ))}
                {!runs.length && (
                  <div className="empty compact">확정된 마감이 없습니다.</div>
                )}
              </section>
              <section className="panel">
                <div className="panelTitle">
                  <h2>생성한 보고서</h2>
                </div>
                {outputs.map((name) => (
                  <a
                    className="download"
                    href={"/api/outputs/" + encodeURIComponent(name)}
                    key={name}
                  >
                    <Files size={18} />
                    {name}
                    <Download size={18} />
                  </a>
                ))}
                {!outputs.length && (
                  <div className="empty compact">
                    아직 생성한 보고서가 없습니다.
                  </div>
                )}
              </section>
            </>
          )}
          <footer>
            촉매 마감 관리 <span>원본 보관 · 변경 이력 · 월별 마감</span>
          </footer>
        </div>
      </main>
      {mapping && (
        <div className="overlay">
          <section className="dialog">
            <div className="panelTitle">
              <h2>입력 양식 연결</h2>
              <button onClick={() => setMapping(null)} aria-label="닫기">
                <X />
              </button>
            </div>
            <p>{mapping.name}</p>
            <div className="formGrid">
              <label>
                시트
                <select
                  value={mapping.sheet}
                  onChange={(e) => {
                    setMapping({
                      ...mapping,
                      sheet: e.target.value,
                      columns: {},
                    });
                    setMapped(null);
                  }}
                >
                  {selectedSource?.meta.sheets?.map((s: Row) => (
                    <option key={s.name}>{s.name}</option>
                  ))}
                </select>
              </label>
              <label>
                제목 행
                <select
                  value={mapping.header_row}
                  onChange={(e) => {
                    setMapping({
                      ...mapping,
                      header_row: Number(e.target.value),
                      columns: {},
                    });
                    setMapped(null);
                  }}
                >
                  {selectedSheet?.headers.map((h: Row) => (
                    <option key={h.row} value={h.row}>
                      {h.row}행:{" "}
                      {h.cells.filter(Boolean).slice(0, 4).join(" / ")}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                자료 구분
                <select
                  value={mapping.kind}
                  onChange={(e) => {
                    setMapping({ ...mapping, kind: e.target.value });
                    setMapped(null);
                  }}
                >
                  {Object.entries(labels).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                자료 묶음 이름
                <input
                  placeholder="예: 우신 입고"
                  value={mapping.scope}
                  onChange={(e) =>
                    setMapping({ ...mapping, scope: e.target.value })
                  }
                />
              </label>
              <label>
                반영 방식
                <select
                  value={mapping.mode}
                  onChange={(e) =>
                    setMapping({ ...mapping, mode: e.target.value })
                  }
                >
                  <option value="replace">같은 자료 묶음·월을 교체</option>
                  <option value="append">별도 거래로 추가</option>
                </select>
              </label>
            </div>
            <p className="help">
              각 항목에 대응하는 열을 선택하세요. 날짜·거래처가 파일에 없으면
              공통값을 입력합니다.
            </p>
            <div className="formGrid">
              {Object.entries(fields).map(([key, label]) => (
                <label key={key}>
                  {label}
                  <select
                    value={mapping.columns[key] ?? ""}
                    onChange={(e) => {
                      setMapping({
                        ...mapping,
                        columns: { ...mapping.columns, [key]: e.target.value },
                      });
                      setMapped(null);
                    }}
                  >
                    <option value="">열 없음 / 공통값 사용</option>
                    {headers.map((h: string, i: number) => (
                      <option key={i} value={i}>
                        {i + 1}열: {h || "(빈 제목)"}
                      </option>
                    ))}
                  </select>
                  <input
                    placeholder="공통값 (선택)"
                    value={mapping.defaults[key] || ""}
                    onChange={(e) => {
                      setMapping({
                        ...mapping,
                        defaults: {
                          ...mapping.defaults,
                          [key]: e.target.value,
                        },
                      });
                      setMapped(null);
                    }}
                  />
                </label>
              ))}
            </div>
            {mapped && (
              <div className="mappingResult">
                <strong>
                  {mapped.count}행 · 오류 {mapped.errors.length}건
                </strong>
                <pre>
                  {JSON.stringify(
                    mapped.errors.length
                      ? mapped.errors
                      : mapped.rows.slice(0, 3),
                    null,
                    2,
                  )}
                </pre>
              </div>
            )}
            <div className="formFooter">
              <button
                disabled={!!busy}
                onClick={() =>
                  action(async () => {
                    const p = await api(
                      "/sources/" + mapping.id + "/preview",
                      mapping,
                    );
                    setMapped(p);
                  })
                }
              >
                반영 전 미리보기
              </button>
              <button
                className="primary"
                disabled={
                  !!busy ||
                  !mapped ||
                  mapped.errors.length > 0 ||
                  !mapping.scope
                }
                onClick={async () => {
                  const r = await action(
                    () => api("/sources/" + mapping.id + "/apply", mapping),
                    "자료 반영 중",
                  );
                  if (r) setMapping(null);
                }}
              >
                양식 저장 및 반영
              </button>
            </div>
          </section>
        </div>
      )}
      {modal && (
        <div className="overlay">
          <section className="dialog">
            <div className="panelTitle">
              <h2>{modal.title}</h2>
              <button onClick={() => setModal(null)} aria-label="닫기">
                <X />
              </button>
            </div>
            {modal.message && <p>{modal.message}</p>}
            {modal.shutdown && <><p>데이터를 백업하고 프로그램과 폴더 감시를 종료합니다.</p><button className="primary" onClick={async()=>{try{await api('/shutdown',{});setModal(null);setToast('프로그램을 종료했습니다. 다시 사용하려면 실행 파일을 열어주세요.');}catch(e:any){setToast(e.message);}}}>백업 후 종료</button></>}
            {modal.rows && <Evidence rows={modal.rows}/>}
            {modal.edit && <><p>기존 값은 이력에 보존됩니다. 이후 같은 자료 묶음의 파일이 들어오면 수동 수정 충돌을 확인합니다.</p><div className="formGrid">{Object.entries(fields).map(([key,label])=><label key={key}>{label}<input type={key==='date'?'date':'text'} value={modal.edit[key]??''} onChange={e=>setModal({...modal,edit:{...modal.edit,[key]:e.target.value}})}/></label>)}<label>수정 사유<input value={modal.reason} onChange={e=>setModal({...modal,reason:e.target.value})}/></label></div><div className="formFooter"><button className="primary" disabled={!!busy||!modal.reason} onClick={async()=>{const result=await action(()=>api('/records/'+modal.edit.id+'/revise',{row:modal.edit,reason:modal.reason}),'수정 이력 저장 중');if(result)setModal(null);}}>수정값 반영</button></div></>}
            {modal.confirm && (
              <>
                <p>
                  {period}의 현재 자료와 계산 결과를 고정합니다. 이후 변경분은
                  새 버전으로 관리합니다.
                </p>
                <button
                  className="primary"
                  onClick={async () => {
                    const r = await action(
                      () =>
                        api("/closing/" + period, {
                          fingerprint: preview?.fingerprint,
                        }),
                      "마감 확정 중",
                    );
                    if (r) {
                      setModal(null);
                      setTab(4);
                    }
                  }}
                >
                  현재 결과 확정
                </button>
              </>
            )}
            {modal.backups && (
              <>
                <p>
                  복원 전에 현재 데이터도 자동 백업합니다. 선택한 시점 이후의
                  반영 내역은 현재 목록에서 제외됩니다.
                </p>
                {modal.backups.map((b: string) => (
                  <button
                    className="download"
                    key={b}
                    onClick={() =>
                      setModal({ title: "선택한 백업으로 복원", restore: b })
                    }
                  >
                    {b}
                  </button>
                ))}
              </>
            )}
            {modal.restore && (
              <>
                <p>{modal.restore} 시점으로 데이터를 복원합니다.</p>
                <button
                  className="primary"
                  onClick={async () => {
                    await action(
                      () => api("/restore", { file: modal.restore }),
                      "복원 중",
                    );
                    setModal(null);
                  }}
                >
                  복원 실행
                </button>
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
function FileTable({
  items,
  onMap,
}: {
  items: Row[];
  onMap: (s: Row) => void;
}) {
  return (
    <div className="scroll">
      <table>
        <thead>
          <tr>
            <th>파일명</th>
            <th>자료 유형</th>
            <th>상태</th>
            <th>등록일</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {items.map((s) => (
            <tr key={s.id}>
              <td className="filename">
                <Files size={17} />
                <a href={"/api/sources/" + s.id + "/download"}>{s.name}</a>
              </td>
              <td>{s.meta.type}</td>
              <td>
                <span className={"badge " + s.status}>
                  {
                    (
                      {
                        reference: "비교 기준",
                        pending: "열 연결 필요",
                        imported: "반영 완료",
                        error: "읽기 오류",
                      } as Row
                    )[s.status]
                  }
                </span>
              </td>
              <td>{s.created.slice(0, 10)}</td>
              <td>
                {s.status === "pending" && (
                  <button onClick={() => onMap(s)}>
                    열 연결 <ChevronRight size={14} />
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!items.length && (
        <div className="empty compact">등록된 파일이 없습니다.</div>
      )}
    </div>
  );
}
function Evidence({rows}:{rows:Row[]}){
 if(rows[0]?.['항목'])return <div className="scroll"><table><thead><tr>{['거래처','항목','기준 값','현재 계산','차이'].map(k=><th key={k}>{k}</th>)}</tr></thead><tbody>{rows.map((r,i)=><tr key={i}><td>{r.customer}</td><td>{r['항목']}</td>{['기준 값','현재 계산','차이'].map(k=><td key={k}>{fmt(r[k])}</td>)}</tr>)}</tbody></table><a className="download" href={'/api/sources/'+rows[0].source_id+'/download'}>기준 엑셀 다운로드</a></div>;
 const names:Row={...fields,kind:'자료 구분',opening:'전월 이월',receipt:'당월 입고',settlement:'당월 정산',closing:'당월 미결',opening_amount:'이월 금액(원)',receipt_amount:'입고 금액(원)',settlement_amount:'정산 금액(원)',closing_amount:'미결 금액(원)',file:'원본 파일',sheet:'시트',row:'원본 행',reason:'수정 사유',prior_period:'이월 기준월',message:'확인 사항',plan:'계획 수량',factory:'공장',supplier:'공급업체',vehicle:'차종',price_type:'단가 구분','항목':'항목','기준 값':'기준 값','현재 계산':'현재 계산','차이':'차이'};
 return <div style={{padding:24}}>{rows.map((row,i)=><section className="panel" key={i}><table><tbody>{Object.entries(row).filter(([k,v])=>names[k]&&v!==null&&typeof v!=='object').map(([key,value])=><tr key={key}><th>{names[key]}</th><td style={{whiteSpace:'normal'}}>{key==='kind'?labels[value]:String(value)}</td></tr>)}</tbody></table>{row.source_id&&<a className="download" href={'/api/sources/'+row.source_id+'/download'}>원본 파일 다운로드</a>}{Array.isArray(row.evidence)&&<details style={{padding:16}}><summary>계산에 사용한 원본 행</summary><Evidence rows={row.evidence}/></details>}<details style={{padding:16}}><summary>전체 기록</summary><pre>{JSON.stringify(row,null,2)}</pre></details></section>)}</div>;
}
function PartLinks({onSave}:{onSave:()=>Promise<void>}){
 const empty={part:'',customer:'',factory:'',supplier:'',vehicle:'',price_type:'',reason:''};
 const [rows,setRows]=useState<Row[]>([]),[form,setForm]=useState<Row>(empty),[message,setMessage]=useState(''),[saving,setSaving]=useState(false);
 const names:Row={part:'품번',customer:'거래처',factory:'공장',supplier:'공급업체',vehicle:'차종',price_type:'단가 구분',reason:'변경 사유'};
 const refresh=async()=>setRows(await api('/part-links'));
 useEffect(()=>{refresh().catch(e=>setMessage(e.message));},[]);
 return <section className="panel"><div className="panelTitle"><h2>품번·거래처·공장 연결</h2><span>행을 눌러 수정</span></div><div className="formGrid">{Object.entries(names).map(([key,label])=><label key={key}>{label}<input value={form[key]} onChange={e=>setForm({...form,[key]:e.target.value})}/></label>)}</div><div className="formFooter"><span>{message}</span><button className="primary" disabled={saving} onClick={async()=>{setSaving(true);try{await api('/part-links',form);await refresh();await onSave();setForm(empty);setMessage('연결 정보를 저장했습니다');}catch(e:any){setMessage(e.message);}finally{setSaving(false);}}}>연결 정보 저장</button></div>{rows.length>0&&<div className="scroll"><table><thead><tr>{Object.entries(names).filter(([k])=>k!=='reason').map(([k,v])=><th key={k}>{v}</th>)}</tr></thead><tbody>{rows.map(row=><tr key={row.id} onClick={()=>setForm({...row,reason:''})}>{Object.keys(names).filter(k=>k!=='reason').map(k=><td key={k}>{row[k]}</td>)}</tr>)}</tbody></table></div>}</section>;
}
function PriceEstimates({period,details,onSave}:{period:string;details:Row[];onSave:()=>Promise<void>}){
 const blank=()=>({period,part:'',customer:'',price:'',reason:'',enabled:true});
 const [rows,setRows]=useState<Row[]>([]),[form,setForm]=useState<Row>(blank),[message,setMessage]=useState(''),[saving,setSaving]=useState(false);
 const refresh=async()=>setRows(await api('/price-estimates'));
 useEffect(()=>{setForm(blank());refresh().catch(e=>setMessage(e.message));},[period]);
 const names:Row={period:'대상 월',part:'품번',customer:'거래처',price:'예상 정산 단가(원)',reason:'추정·변경 사유'};
return <section className="panel"><div className="panelTitle"><h2>예상 정산 단가</h2><span>실제 적용 단가와 별도 관리</span></div><p className="help">선택한 월의 미결 수량 × 예상 단가입니다. 실제 정산·이월 금액은 바꾸지 않으며 다음 달로 자동 적용하지 않습니다. 엑셀의 별도 참고표에 구분하여 출력합니다.</p><div className="formGrid">{Object.entries(names).map(([key,label])=><label key={key}>{label}<input type={key==='period'?'month':'text'} value={form[key]} onChange={e=>setForm({...form,[key]:e.target.value})}/></label>)}<label>사용 여부<select value={String(form.enabled)} onChange={e=>setForm({...form,enabled:e.target.value==='true'})}><option value="true">사용</option><option value="false">사용 안 함</option></select></label></div><div className="formFooter"><span role="status">{message}</span><button className="primary" disabled={saving} onClick={async()=>{setSaving(true);try{await api('/price-estimates',form);await refresh();await onSave();setForm(blank());setMessage('예상 단가를 저장했습니다. 실제 단가는 변경하지 않았습니다.');}catch(e:any){setMessage(e.message);}finally{setSaving(false);}}}>예상 단가 저장</button></div><div className="scroll"><table><thead><tr>{['월','품번','거래처','예상 단가','미결 수량','기록 기준 미결금액','예상 정산금액','사용','사유'].map(x=><th key={x}>{x}</th>)}</tr></thead><tbody>{rows.filter(r=>r.period===period).map(r=>{const d=details.find(d=>d.part===r.part&&d.customer===r.customer);return <tr key={r.period+r.customer+r.part}><td>{r.period}</td><td><button onClick={()=>setForm({...r,enabled:!!r.enabled,reason:''})}>{r.part} 수정</button></td><td>{r.customer}</td><td>{fmt(r.price)}</td><td>{fmt(d?.closing)}</td><td>{fmt(d?.closing_amount)}</td><td>{r.enabled?fmt(d?.estimated_closing_amount):'—'}</td><td>{r.enabled?'사용':'사용 안 함'}</td><td>{r.reason}</td></tr>})}</tbody></table></div></section>;
}
createRoot(document.getElementById("root")!).render(<App />);
