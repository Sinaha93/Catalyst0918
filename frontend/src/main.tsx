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
  Settings2,
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
    [period, setPeriod] = useState(() => {try {const saved=localStorage.getItem('catalyst-period');return saved&&/^\d{4}-(0[1-9]|1[0-2])$/.test(saved)?saved:'2026-08';}catch{return '2026-08';}}),
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
    try {localStorage.setItem('catalyst-period',period);}catch {/* Storage may be disabled. */}
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
  function openMapping(source: Row, advanced = false) {
    if(source.meta.type==='월계획 등록 자료') {setModal({title:'월계획 등록',plan:source});return;}
    if(['한국유미코아 마감자료','희성촉매 마감자료'].includes(source.meta.type)) {
      setModal({title:source.meta.type+' 등록',supplier:source});
      return;
    }
    if(source.meta.type==='ERP 월 입고현황') {
      setModal({title:'ERP 월 입고 등록',erp:source});
      return;
    }
    if(!advanced) {setModal({title:'새 양식 확인',advancedSource:source});return;}
    setModal(null);
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
    "고급기능",
  ];
  const Icons = [LayoutDashboard, Files, Database, TriangleAlert, FolderClock, Settings2];
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
                    "새 양식의 열 연결과 월중 단가 적용일을 설정합니다.",
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
                <FileTable items={sources.filter(s=>s.status!=='cancelled').slice(0, 4)} onMap={openMapping} />
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
              </div>
              <section className="panel">
                <div className="panelTitle">
                  <h2>입력 자료</h2>
                  <span>{sources.length}개 파일</span>
                  <button disabled={!!busy||!sources.length} onClick={async()=>{const result=await action(()=>api('/registration-reset/preview'),'초기화 범위 확인 중');if(result)setModal({title:'등록 자료 전체 초기화',resetRegistrations:result,confirmText:''});}}>등록 자료 전체 초기화</button>
                </div>
                <p className="help">다음 달에는 상단에서 마감 월을 바꾸고 새 월의 ERP·촉매사 마감·계획 자료를 등록하세요. BOM·단가·보고 양식은 변경될 때만 갱신합니다. 전월 확정 이월은 자동으로 이어집니다. 아래 삭제는 프로그램 등록만 제거하며 원본 파일은 삭제하지 않습니다.</p>
                <SourceManager items={sources} onMap={openMapping} onSave={reload}/>
              </section>
              <RequiredSources items={sources} period={period} runs={runs} snapshot={preview?.input_snapshot||[]} allocation={preview?.supplier_allocation}/>
              <SupplierAllocation preview={preview} onSave={reload}/>
              <MasterImport items={sources} period={period} onSave={reload}/>
            </>
          )}
          {tab === 5 && <>
            <section className="panel"><div className="panelTitle"><h2>열 연결</h2><span>자동 인식하지 못한 새 양식용</span></div><p className="help">일반 등록은 자료 등록 메뉴를 이용하세요. 아래 설정은 새로운 양식의 품번·수량 열을 직접 지정할 때만 필요합니다.</p>
              {sources.filter(s=>s.status==='pending'&&!['월계획 등록 자료','ERP 월 입고현황','한국유미코아 마감자료','희성촉매 마감자료','BOM 마스터','구매단가등록'].includes(s.meta.type)).map(s=><div className="formFooter" key={s.id}><span>{s.name}</span><button onClick={()=>openMapping(s,true)}>열 연결 설정</button></div>)}
              {!sources.some(s=>s.status==='pending'&&!['월계획 등록 자료','ERP 월 입고현황','한국유미코아 마감자료','희성촉매 마감자료','BOM 마스터','구매단가등록'].includes(s.meta.type))&&<p className="help">열 연결이 필요한 새 양식이 없습니다.</p>}
            </section>
            <MasterImport key={'advanced-'+period} items={sources} period={period} advanced onSave={reload}/>
            <ExceptionRules key={'rules-'+period} period={period} onSave={reload}/>
            <AllocationManagement preview={preview} onSave={reload}/>
            <ChangeHistory key={preview?.fingerprint}/>
          </>}
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
                        {i.explanation ? i.explanation.summary : i.code === "import"
                          ? "원본의 열 연결과 입력값을 확인해주세요."
                          : "자료를 보완하면 다음 계산에 자동 반영됩니다."}
                      </p>
                      {i.explanation && <div className="issueContext"><div>수량이 있는 곳: {i.explanation.found.map((r:Row)=>`${r.file}${r.sheet?' · '+r.sheet:''}${r.row?' '+r.row+'행':''} (${labels[r.kind]||r.kind}, ${r.customer||'공통'})`).join(' / ')}</div><div>대조한 기준: {i.explanation.checked.map((r:Row)=>`${r.file} — ${r.state}`).join(' / ')}</div><div>해결 방법: {i.explanation.action}</div></div>}
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
                      <p>{s.meta.type.includes('마감자료')||s.meta.type==='ERP 월 입고현황'?'양식을 자동으로 찾았습니다. 대상 월을 확인해주세요.':'자료 유형과 반영 방법을 확인해주세요.'}</p>
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
                  <div key={name} style={{display:'flex',alignItems:'center'}}>
                  <a
                    className="download"
                    href={"/api/outputs/" + encodeURIComponent(name)}
                    key={name}
                  >
                    <Files size={18} />
                    {name}
                    <Download size={18} />
                  </a>
                  <button disabled={!!busy} onClick={()=>setModal({title:'생성 보고서 삭제',deleteOutput:name})}>삭제</button>
                  </div>
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
              <h2>고급 설정 · 열 연결</h2>
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
            {modal.resetRegistrations && <><p><strong>선택한 월뿐 아니라 모든 월의 등록 자료</strong>를 프로그램 목록과 미확정 계산에서 제외합니다.</p><p>등록 파일 {modal.resetRegistrations.sources.length}개 · 반영 내역 {fmt(modal.resetRegistrations.count)}건 · 대상 월: {modal.resetRegistrations.periods.join(', ')||'반영 전 자료'}</p><details><summary>초기화할 파일 보기</summary>{modal.resetRegistrations.sources.map((s:Row)=><p key={s.id}>{s.name}</p>)}</details><p>원본·업로드·보관 파일은 삭제하지 않습니다. 확정 마감 {modal.resetRegistrations.runs}건, 생성 보고서, 별도 직접 입력 {modal.resetRegistrations.manual_count}건, 직접 관리한 품번 연결·예상 단가·열 연결 양식은 유지합니다. BOM·구매단가도 등록 자료이면 초기화되므로 다시 등록해야 합니다.</p><p>실행 전 자동 백업합니다. 기존 파일이 자동 수집으로 다시 나타나지는 않으며, 직접 업로드하면 재등록할 수 있습니다.</p><label>실행하려면 ‘초기화’를 입력하세요<input value={modal.confirmText} onChange={e=>setModal({...modal,confirmText:e.target.value})}/></label><div className="formFooter"><button disabled={!!busy} onClick={()=>setModal(null)}>취소</button><button className="primary" disabled={!!busy||modal.confirmText!=='초기화'} onClick={async()=>{const result=await action(()=>api('/registration-reset',{fingerprint:modal.resetRegistrations.fingerprint,confirm_text:modal.confirmText}),'등록 자료 초기화 중');if(result){setModal(null);setMapping(null);setMapped(null);setToast(`등록 자료 ${result.sources}개를 초기화했습니다. 실제 파일은 보존했습니다.`);}}}>등록 자료 초기화 실행</button></div></>}
            {modal.advancedSource && <><p>이 파일은 아직 자동으로 읽을 수 없는 양식입니다. 새 양식의 열 연결은 왼쪽 고급기능 메뉴에서 설정합니다.</p><button onClick={()=>{setModal(null);setTab(5);}}>고급기능으로 이동</button></>}
            {modal.erp && <ErpImport source={modal.erp} busy={!!busy} onPreview={p=>api('/sources/'+modal.erp.id+'/erp-preview',{period:p})} onApply={async payload=>{const result=await action(()=>api('/sources/'+modal.erp.id+'/erp-apply',payload),'ERP 입고 반영 중');if(result)setModal(null);}}/>}
            {modal.supplier && <SupplierImport source={modal.supplier} busy={!!busy} onApply={async payload=>{const result=await action(()=>api('/sources/'+modal.supplier.id+'/supplier-apply',payload),'촉매사 마감자료 등록 중');if(result)setModal(null);}}/>}
            {modal.plan && <PlanImport source={modal.plan} selectedPeriod={period} busy={!!busy} onApply={async payload=>{const result=await action(()=>api('/sources/'+modal.plan.id+'/plan-apply',payload),'월계획 반영 중');if(result)setModal(null);}}/>}
            {modal.deleteOutput && <><p>{modal.deleteOutput}</p><p>생성된 파일을 실제로 삭제합니다. 복원 기능은 없습니다. 확정 마감 이력은 유지되므로 필요하면 보고서를 다시 생성할 수 있습니다.</p><button className="primary" disabled={!!busy} onClick={async()=>{const result=await action(()=>api('/outputs/'+encodeURIComponent(modal.deleteOutput)+'/delete',{confirm:true}),'보고서 삭제 중');if(result)setModal(null);}}>파일 영구 삭제</button></>}
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
  onManage,
}: {
  items: Row[];
  onMap: (s: Row) => void;
  onManage?: (s: Row) => void;
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
                <div className="sourceFileInfo"><a href={"/api/sources/" + s.id + "/download"}>{s.name}</a><SourceLocation source={s}/></div>
              </td>
              <td>{s.meta.type}<div className="sourceRequirement">{s.requirement_label}</div></td>
              <td>
                <span className={"badge " + s.status}>
                  {
                    (
                      {
                        reference: s.meta.supplier_registration?.active?`${s.meta.supplier_registration.period} 등록됨`:"비교 기준",
                        pending: s.meta.type==='월계획 등록 자료'?'계획 확인 필요':s.meta.type==='ERP 월 입고현황'||s.meta.type.includes('촉매 마감자료')||s.meta.type==='한국유미코아 마감자료'?"대상 월 확인 필요":"등록 설정 필요",
                        imported: "반영 완료",
                        error: "읽기 오류",
                        cancelled: "삭제·반영 취소",
                      } as Row
                    )[s.status]
                  }
                </span>
              </td>
              <td>{s.created.slice(0, 10)}</td>
              <td>
                {(s.status === "pending" || s.status==='reference'&&['한국유미코아 마감자료','희성촉매 마감자료'].includes(s.meta.type)) && !['BOM 마스터','구매단가등록'].includes(s.meta.type) && (
                  <button onClick={() => onMap(s)}>
                    {s.meta.type==='월계획 등록 자료'?'계획 확인':['한국유미코아 마감자료','희성촉매 마감자료'].includes(s.meta.type)?(s.meta.supplier_registration?.active?'수량 비교':'마감자료 등록'):s.meta.type==='ERP 월 입고현황'?'입고 등록':'등록 설정'} <ChevronRight size={14} />
                  </button>
                )}
                {onManage && <button onClick={()=>onManage(s)}>삭제</button>}
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
function PlanImport({source,selectedPeriod,busy,onApply}:{source:Row;selectedPeriod:string;busy:boolean;onApply:(payload:Row)=>Promise<void>}) {
  const [result,setResult]=useState<Row|null>(null),[message,setMessage]=useState(''),[loading,setLoading]=useState(false);
  async function check(){setLoading(true);setResult(null);try{setResult(await api('/sources/'+source.id+'/plan-preview',{}));setMessage('');}catch(e:any){setMessage(e.message);}finally{setLoading(false);}}
  useEffect(()=>{check();},[source.id]);
  return <section className="supplierImport"><p>날짜·품번·납품처·수량·금액을 자동으로 연결합니다. 열 설정은 필요 없습니다.</p>
    {loading&&<p>계획 자료를 확인하고 있습니다…</p>}<p role="status">{message}</p>
    {result&&<><h3>{result.period} 계획 · {result.count}행</h3><p>계획 수량 {fmt(result.quantity)}개 / 계획 금액 {fmt(result.amount)}원</p>
      {selectedPeriod!==result.period&&<p role="alert">현재 화면은 {selectedPeriod}이지만, 파일 안의 일자는 {result.period}입니다. 아래 버튼은 파일에 적힌 {result.period}에만 반영합니다.</p>}
      {result.replace_count>0&&<p>같은 월 계획 {result.replace_count}행을 이 수정본으로 교체합니다. 다른 월·실제 단가·입고는 바꾸지 않습니다.</p>}
      <div className="scroll"><table><thead><tr><th>납품처</th><th>계획 수량</th><th>계획 금액(원)</th></tr></thead><tbody>{result.customers.map((r:Row)=><tr key={r.customer}><td>{r.customer}</td><td>{fmt(r.quantity)}</td><td>{fmt(r.amount)}</td></tr>)}</tbody></table></div>
      {result.errors.map((e:string,i:number)=><p role="alert" key={i}>{e}</p>)}
      <div className="formFooter"><button disabled={busy||loading} onClick={check}>다시 확인</button><button className="primary" disabled={busy||loading||!!result.errors.length} onClick={()=>onApply({fingerprint:result.fingerprint})}>{result.period} 계획 반영</button></div></>}
    {!result&&!loading&&<button disabled={busy} onClick={check}>다시 확인</button>}
  </section>;
}
function SupplierImport({source,busy,onApply}:{source:Row;busy:boolean;onApply:(payload:Row)=>Promise<void>}) {
  const [month,setMonth]=useState(source.meta.supplier_registration?.period||'');
  const [result,setResult]=useState<Row|null>(null),[loading,setLoading]=useState(false),[message,setMessage]=useState('');
  return <section className="supplierImport">
    <p className="supplierIntro">열을 연결하실 필요 없습니다. <strong>{source.meta.type}</strong> 양식을 자동으로 찾았습니다.</p>
    <p>마감 월만 선택하면 품번·납품·이월·정산 수량을 구분해서 읽습니다.</p>
    <div className="supplierControls"><label>이 파일은 몇 월 마감자료인가요?<input type="month" value={month} disabled={busy||loading} onChange={e=>{setMonth(e.target.value);setResult(null);setMessage('');}}/></label>
      <button disabled={!month||busy||loading} onClick={async()=>{setLoading(true);setResult(null);try{setResult(await api('/sources/'+source.id+'/supplier-preview',{period:month}));setMessage('');}catch(e:any){setMessage(e.message);}finally{setLoading(false);}}}>{loading?'읽는 중…':'자료 확인'}</button></div>
    <p role="status">{message}</p>
    {result&&<>
      <p><strong>{month} · {result.parts}개 품번</strong>을 읽었습니다.</p>
      <div className="scroll"><table><thead><tr><th>전월 이월</th><th>{result.quantity_label} · ERP 비교 대상</th><th>당월 정산</th><th>남은 수량</th></tr></thead><tbody><tr>{['opening','delivery','settlement','closing'].map(k=><td key={k}>{fmt(result.totals[k])}개</td>)}</tr></tbody></table></div>
      <p>ERP 입고에 중복 합산하지 않습니다. 등록하면 원본 납품처·BOM으로 이월·정산을 자동 연결합니다. 구분할 수 없는 품목만 자료 등록의 ‘이월·정산 연결 확인’에 표시됩니다.</p>
      {!result.comparison.erp_available?<p>이 월의 ERP 입고가 아직 반영되지 않았습니다. 먼저 이 자료를 등록해도 됩니다. ERP 반영 후 ‘수량 비교’에서 확인하세요.</p>:<><p>이 파일에 있는 품번 기준: 일치 {result.comparison.matched}개 / 차이·확인 필요 {result.comparison.differences.length}개. 차이는 ERP 입고 − 촉매사 수량입니다.</p>
        {result.comparison.differences.length>0&&<div className="scroll"><table><thead><tr><th>품번</th><th>촉매사 수량</th><th>ERP 입고</th><th>차이</th></tr></thead><tbody>{result.comparison.differences.map((r:Row)=><tr key={r.part}><td>{r.part}</td><td>{fmt(r.supplier_quantity)}</td><td>{fmt(r.erp_quantity)}</td><td>{r.overlap?'두 촉매사에 동일 품번 · 확인 필요':fmt(r.difference)}</td></tr>)}</tbody></table></div>}
        <p>ERP에만 있고 이 파일에는 없는 품번은 이 표의 비교 범위에 포함되지 않습니다. 차이는 자동 보정하지 않습니다.</p></>}
      <details><summary>자동으로 읽은 품목 보기</summary><div className="scroll"><table><thead><tr><th>품번</th><th>이월</th><th>{result.quantity_label}</th><th>정산</th><th>잔량</th><th>원본</th></tr></thead><tbody>{result.items.map((r:Row,i:number)=><tr key={i}><td>{r.part}</td>{['opening','delivery','settlement','closing'].map(k=><td key={k}>{fmt(r[k])}</td>)}<td>{r.sheet} {r.row}행</td></tr>)}</tbody></table></div></details>
      {result.replaces.length>0&&<p>등록하면 같은 월·촉매사의 이전 비교 자료를 대체합니다: {result.replaces.map((r:Row)=>r.name).join(', ')}</p>}
      {result.errors.map((e:string,i:number)=><p role="alert" key={i}>{e}</p>)}
      {result.warnings.map((e:string,i:number)=><p key={'w'+i}>{e}</p>)}
      <div className="formFooter">{result.registered?<span>이미 등록한 자료입니다. ERP 비교 결과는 현재 입력 기준입니다.</span>:<button className="primary" disabled={busy||loading||!!result.errors.length} onClick={()=>onApply({period:month,fingerprint:result.fingerprint})}>{month} 마감자료로 등록</button>}</div>
    </>}
  </section>;
}
function ErpImport({source,busy,onPreview,onApply}:{source:Row;busy:boolean;onPreview:(period:string)=>Promise<Row>;onApply:(payload:Row)=>Promise<void>}) {
  const [period,setPeriod]=useState(''),[result,setResult]=useState<Row|null>(null),[message,setMessage]=useState(''),[loading,setLoading]=useState(false),[confirmed,setConfirmed]=useState(false);
  return <section style={{padding:24}}><p>{source.name}</p><p>품번과 거래처별 수량을 자동 연결합니다. 파일명 날짜는 조회 월이 아닙니다. ERP에서 조회한 대상 월을 직접 선택해주세요.</p><label>대상 월<input type="month" value={period} disabled={busy||loading} onChange={e=>{setPeriod(e.target.value);setResult(null);setConfirmed(false);setMessage('');}}/></label><button disabled={!period||busy||loading} onClick={async()=>{setLoading(true);setResult(null);setConfirmed(false);try{setResult(await onPreview(period));setMessage('');}catch(e:any){setMessage(e.message);}finally{setLoading(false);}}}>{loading?'검증 중':'입고 미리보기'}</button><p role="status">{message}</p>{result&&<><p>ERP 전체 {fmt(result.total)}개 − 제외 품목 {fmt(result.excluded_total)}개 = 촉매 입고 {fmt(result.receipt_total)}개</p><p>품번 {result.parts}개 / 거래처별 내역 {result.count}건. {result.replace_count?`같은 월 ERP 내역 ${result.replace_count}건을 교체합니다.`:'새 월 입고 자료로 반영합니다.'}</p><p>입고 기준일 {result.date}는 월 집계용이며 실제 개별 입고일을 뜻하지 않습니다. 금액은 적용 단가로 계산하며, 단가 누락은 마감 현황에서 확인합니다.</p><div className="scroll"><table><thead><tr><th>거래처</th><th>입고 수량</th></tr></thead><tbody>{result.customers.map((r:Row)=><tr key={r.customer}><td>{r.customer}</td><td>{fmt(r.quantity)}</td></tr>)}</tbody></table></div>{result.excluded.length>0&&<p>기존 합의에 따른 제외: {result.excluded.map((r:Row)=>`${r.part} (${fmt(r.quantity)}개)`).join(', ')}</p>}{result.errors.map((error:string,i:number)=><p key={i}>{error}</p>)}<label style={{display:'block',margin:'16px 0'}}><input type="checkbox" checked={confirmed} disabled={busy} onChange={e=>setConfirmed(e.target.checked)}/> 이 파일이 {period} ERP 월 입고 자료임을 확인했습니다.</label><button className="primary" disabled={busy||loading||!confirmed||!!result.errors.length} onClick={()=>onApply({period,fingerprint:result.fingerprint,confirm_period:true})}>확인한 월에 입고 반영</button></>}</section>;
}
function SupplierAllocation({preview,onSave}:{preview:Row|null;onSave:()=>Promise<void>}) {
  const allocation=preview?.supplier_allocation;
  if(!allocation?.source_ids?.length)return null;
  return <section className="panel"><div className="panelTitle"><h2>{preview?.period} 이월·정산 연결 확인</h2><span>열 연결 없이 자동 계산</span></div>
    <p className="help">이월 {allocation.connected.opening}건 · 정산 {allocation.connected.settlement}건을 자동 연결했습니다. 전월 확정본과 기존 직접 입력은 중복 합산하지 않습니다.</p>
    {!allocation.pending.length?<p className="help">납품처 배부 확인 항목이 없습니다. 다른 누락·단가·수량 오류는 마감 현황에서 확인해주세요.</p>:<p className="help">아래 항목만 확인해주세요. 한 곳이면 전량을, 여러 곳이면 각각의 수량을 입력하세요. 합계는 원본과 같아야 합니다.</p>}
    {allocation.pending.map((r:Row)=><AllocationEditor key={`${preview?.fingerprint}:${r.source_id}:${r.part}:${r.kind}`} item={r} preview={preview!} onSave={onSave}/>)}
  </section>;
}
function AllocationEditor({item,preview,onSave}:{item:Row;preview:Row;onSave:()=>Promise<void>}) {
  const [values,setValues]=useState<Row[]>(item.candidates.length?item.candidates.map((customer:string)=>({customer,quantity:item.values?.[customer]??''})):[{customer:'',quantity:''}]);
  const [reason,setReason]=useState(''),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
  const customers=['기아 화성','기아 광명','기아 광주','현대 아산','현대 울산','현대 전주','현대 글로비스','현대 위아','세종공업','현대 모비스'];
  return <details className="allocationEditor"><summary>{item.part} · {item.kind==='opening'?'전월 이월':'당월 정산'} {fmt(item.total)}개 — 납품처 확인</summary>
    <p>{item.message}</p><small>{item.file}</small>
    {item.editable&&<><div className="allocationInputs">{values.map((r,i)=><div key={i}><select aria-label="납품처" value={r.customer} onChange={e=>setValues(values.map((x,n)=>n===i?{...x,customer:e.target.value}:x))}><option value="">납품처 선택</option>{customers.map(c=><option key={c}>{c}</option>)}</select><input aria-label="배부 수량" type="number" min="0" step="1" placeholder="수량" value={r.quantity} onChange={e=>setValues(values.map((x,n)=>n===i?{...x,quantity:e.target.value}:x))}/><button disabled={busy} onClick={()=>setValues(values.filter((_,n)=>n!==i))}>행 제거</button></div>)}</div>
      <button disabled={busy} onClick={()=>setValues([...values,{customer:'',quantity:''}])}>납품처 추가</button>
      <label>확인 사유<input value={reason} onChange={e=>setReason(e.target.value)} placeholder="예: 전월 미정산 내역 확인"/></label>
      <p>입력 합계 {fmt(values.reduce((sum,r)=>sum+Number(r.quantity||0),0))} / 원본 {fmt(item.total)}개</p>
      <button className="primary" disabled={busy||!reason.trim()} onClick={async()=>{setBusy(true);try{const selected=values.filter(r=>r.quantity!=='');if(!selected.length||selected.some(r=>!r.customer)||new Set(selected.map(r=>r.customer)).size!==selected.length)throw Error('납품처와 수량을 입력하고 중복 납품처를 합쳐주세요.');await api('/supplier-allocation',{period:preview.period,fingerprint:preview.fingerprint,source_id:item.source_id,part:item.part,kind:item.kind,values:Object.fromEntries(selected.map(r=>[r.customer,r.quantity])),reason});await onSave();}catch(e:any){setMessage(e.message);}finally{setBusy(false);}}}>확인한 수량으로 연결</button><p role="status">{message}</p></>}
  </details>;
}
function RequiredSources({items,period,runs,snapshot,allocation}:{items:Row[];period:string;runs:Row[];snapshot:Row[];allocation?:Row}) {
  const [year,month]=period.split('-').map(Number);
  const previous=month===1?`${year-1}-12`:`${year}-${String(month-1).padStart(2,'0')}`;
  const requirements=[
    ['bom','BOM 마스터','품번·마감처·촉매사 기준'],
    ['price','구매단가등록','실제 단가 기준. 적용일 확인 후 반영'],
    ['receipt','ERP 월 입고현황','해당 월 입고 수량 대사'],
    ['umicore','한국유미코아 마감 자료','Total 납품과 ERP 비교. 대상 기간 확인'],
    ['heesung','희성촉매 마감 자료','출하 수량과 ERP 비교. 계는 이월 포함 가능'],
    ['settlement','당월 정산 자료','촉매사 마감파일에서 자동 연결. 불명확한 납품처만 아래에서 확인'],
    ['opening','전월 이월 자료','전월 확정본 우선. 없으면 촉매사 이월을 납품처별 연결'],
    ['plan','월계획 등록 자료','계획 대비 실적 보고에 필요'],
    ['template','마감 보고 Excel 양식','기존 마감 Excel. 보고서 출력에 필요'],
  ];
  return <section className="panel"><div className="panelTitle"><h2>{period} 필수 자료 안내</h2><span>파일 역할 기준</span></div><p className="help">같은 파일이 여러 역할을 맡을 수 있습니다. 등록 여부와 계산 반영을 구분하며, 등록만으로 해당 월 대사가 완료된 것은 아닙니다. 주문전송·PPT·월계획 계산용 매크로 파일은 마감 등록 필수가 아닙니다.</p><div className="scroll"><table><thead><tr><th>필수 자료</th><th>현재 상태</th><th>등록 파일</th><th>용도</th></tr></thead><tbody>{requirements.map(([role,label,note])=>{
    const isAllocation=['opening','settlement'].includes(role);
    const matches=items.filter(s=>s.status!=='cancelled'&&(s.roles?.includes(role)||(isAllocation&&s.meta.supplier_registration?.active&&s.meta.supplier_registration.period===period)));
    const prior=role==='opening'&&runs.some(r=>r.period===previous);
    const monthly=['receipt','settlement','opening','plan'].includes(role);
    const applied=matches.some(s=>monthly?s.applied_months?.[role]?.includes(period):s.master_effective_from&&s.master_effective_from<=period+'-31')||(isAllocation&&snapshot.some(r=>r.kind===role&&r.date?.startsWith(period)));
    const direct=monthly&&snapshot.some(r=>r.kind===role&&r.date?.startsWith(period)&&!r.source_id);
    const supplierRegistered=matches.some(s=>s.meta.supplier_registration?.active&&s.meta.supplier_registration.period===period);
    const unresolved=isAllocation?(allocation?.pending||[]).filter((r:Row)=>r.kind===role).length:0;
    const supplierFiles=items.some(s=>s.roles?.some((r:string)=>['umicore','heesung'].includes(r)));
    const state=unresolved?`파일 있음 · 납품처 확인 ${unresolved}건`:prior?'전월 확정본 사용':direct&&!matches.length?'선택 월 직접 입력됨':!matches.length?(isAllocation&&supplierFiles?'파일 있음 · 마감 월 등록 필요':'파일 없음 · 등록 필요'):matches.some(s=>s.storage_exists===false)?'보관 파일 확인 필요':monthly?(applied||direct?'선택 월 계산 연결됨':'파일 있음 · 계산 연결 확인'):['bom','price'].includes(role)?(applied?'적용일 기준 반영됨':'등록됨 · 적용일/반영 확인'):role==='template'?'양식 등록됨':supplierRegistered?'선택 월 등록됨 · 수량 비교 가능':'마감자료 등록에서 월 선택 필요';
    return <tr key={role}><td>{label}</td><td>{state}</td><td style={{whiteSpace:'normal'}}>{matches.map(s=>s.name).join(', ')||(prior?previous+' 확정 마감':'—')}</td><td style={{whiteSpace:'normal'}}>{note}</td></tr>;
  })}</tbody></table></div><p className="help">BOM·구매단가로 전환하기 전의 촉매 관리 현황은 기존 계산에 사용될 수 있습니다. 새 파일의 등록·미반영 표시와 기존 계산 상태는 별개입니다. 직접 입력 내역은 마감 현황에서 확인해주세요.</p></section>;
}
function SourceLocation({source}:{source:Row}) {
  const [message,setMessage]=useState('');
  async function copy(value:string) {
    try {await navigator.clipboard.writeText(value);setMessage('경로를 복사했습니다');}
    catch {setMessage('경로 텍스트를 선택하여 Ctrl+C로 복사해주세요');}
  }
  return <details className="sourceLocation"><summary>저장 위치 확인</summary>
    <div className="sourcePath"><span>프로그램 보관 사본{source.storage_exists===false?' (파일 없음)':''}</span><code>{source.storage_path}</code>{source.storage_path&&<button type="button" onClick={()=>copy(source.storage_path)}>경로 복사</button>}</div>
    <div className="sourcePath"><span>{source.registered_from_kind==='input'?'등록 시 input 위치':'등록 시 읽어온 위치'}</span>{source.registered_from?<><code>{source.registered_from}</code><button type="button" onClick={()=>copy(source.registered_from)}>경로 복사</button></>:<span>이전에 등록한 자료라 위치 기록이 없습니다.</span>}</div>
    {source.registered_from_kind==='input'&&<p>업로드·자동 수집용 위치입니다. 브라우저에서 선택한 원본 폴더 경로는 전달되지 않습니다.</p>}
    <span role="status">{message}</span></details>;
}
function SourceManager({items,onMap,onSave}:{items:Row[];onMap:(s:Row)=>void;onSave:()=>Promise<void>}){
 const [impact,setImpact]=useState<Row|null>(null),[reason,setReason]=useState(''),[message,setMessage]=useState(''),[busy,setBusy]=useState(false);
 return <><div className="formFooter"><span role="status">{message}</span></div><FileTable items={items} onMap={onMap} onManage={async s=>{try{const result=await api('/sources/'+s.id+'/impact');setImpact({...result,sid:s.id});setReason('');setMessage('');}catch(e:any){setMessage(e.message);}}}/>{impact&&<div className="formGrid"><section><h3>프로그램 등록 삭제</h3><p>{impact.sources.map((s:Row)=>s.name).join(', ')}</p><p>연결 자료 {impact.sources.length}개, 계산에서 제외할 반영 내역 {fmt(impact.count)}건. 대상: {impact.periods.join(', ')||'반영 내역 없음'}.</p>{impact.sources.length>1&&<p>함께 계산한 자료이므로 위 파일을 한 묶음으로 처리합니다.</p>}<p>원본·업로드 파일·보관 사본은 모두 그대로 둡니다. 프로그램 목록과 미확정 계산에서만 제외합니다. 확정 마감·이월 근거·백업은 유지됩니다.</p>{impact.master&&<p>주의: BOM·단가는 다음 달에도 사용하는 기준입니다. 삭제하면 미확정 월 계산에 영향을 줍니다. 월이 바뀌었다는 이유로 삭제할 필요는 없습니다.</p>}<p>자동 수집으로 다시 나타나지 않으며, 필요하면 파일을 직접 업로드해 재등록할 수 있습니다.</p><label>삭제 사유<input value={reason} onChange={e=>setReason(e.target.value)}/></label><button disabled={busy||!reason.trim()} onClick={async()=>{setBusy(true);try{await api('/sources/'+impact.sid+'/delete',{fingerprint:impact.fingerprint,reason,confirm:true});await onSave();setImpact(null);setMessage('프로그램에서 등록을 삭제했습니다. 실제 파일은 그대로 보존했습니다.');}catch(e:any){setMessage(e.message);}finally{setBusy(false);}}}>등록만 삭제</button><button disabled={busy} onClick={()=>setImpact(null)}>닫기</button></section></div>}</>;
}
function MasterImport({items,period,onSave,advanced=false}:{items:Row[];period:string;onSave:()=>Promise<void>;advanced?:boolean}){
 const [form,setForm]=useState<Row>({bom_id:'',price_id:'',effective_date:period+'-01',reason:''}),[result,setResult]=useState<Row|null>(null),[message,setMessage]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{setForm(f=>({...f,effective_date:period+'-01'}));setResult(null);setMessage('');},[period]);
 const update=(k:string,v:string)=>{setForm({...form,[k]:v});setResult(null);};
 return <section className="panel"><div className="panelTitle"><h2>{advanced?'단가 적용일 상세 설정':'BOM·구매단가 연결'}</h2><span>{advanced?'실제 월중 단가 변경 시에만 사용':'마감 월 기준 등록'}</span></div><p className="help">BOM에서 품번·마감처·촉매사를, ERP에서 구매단가를 가져옵니다. 월계획 매크로는 실행하지 않습니다. {advanced?'실제 단가가 바뀐 날짜를 지정합니다. 적용일 이전 거래에는 이 단가를 사용하지 않습니다.':'사용할 마감 월을 선택하면 그달 1일부터 적용합니다. 최초 이월에도 사용할 단가인지 확인해주세요. 월중 변경은 고급기능에서 설정합니다.'} 파일명 날짜·입력일을 적용일로 간주하지 않습니다. 기존 월계획 수량과 확정 마감은 변경하지 않습니다.</p><div className="formGrid">{[['bom_id','BOM 마스터'],['price_id','구매단가등록']].map(([key,label])=><label key={key}>{label}<select value={form[key]} onChange={e=>update(key,e.target.value)}><option value="">파일 선택</option>{items.filter(s=>s.status!=='cancelled'&&s.meta.type===label).map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label>)}<label>{advanced?'적용 기준일':'사용할 마감 월'}<input type={advanced?'date':'month'} value={advanced?form.effective_date:form.effective_date.slice(0,7)} onChange={e=>update('effective_date',e.target.value?(advanced?e.target.value:e.target.value+'-01'):'')}/></label><label>변경 사유<input value={form.reason} onChange={e=>update('reason',e.target.value)}/></label></div><div className="formFooter"><span role="status">{message}</span><button disabled={busy||!form.bom_id||!form.price_id||!form.effective_date} onClick={async()=>{setBusy(true);setResult(null);try{setResult(await api('/master-import/preview',form));setMessage('');}catch(e:any){setMessage(e.message);}finally{setBusy(false);}}}>연결·단가 변경 미리보기</button></div>{result&&<><p className="help">적용 기준일 {result.effective_date} · 품번 {result.parts}개 / 마감처 연결 {result.links}개 / 단가 {result.prices}개. 미사용 품번도 단가가 없으면 0원으로 만들지 않습니다.</p>{result.errors.map((e:string,i:number)=><p className="help" key={i}>{e}</p>)}{result.missing.length>0&&<p className="help">단가 없음: {result.missing.join(', ')}</p>}<div className="scroll"><table><thead><tr><th>품번</th><th>기존 단가(원)</th><th>새 단가(원)</th></tr></thead><tbody>{result.changes.map((r:Row)=><tr key={r.part}><td>{r.part}</td><td>{fmt(r.before)}</td><td>{fmt(r.after)}</td></tr>)}</tbody></table></div><div className="formFooter"><button className="primary" disabled={busy||!!result.errors.length||!form.reason.trim()} onClick={async()=>{setBusy(true);try{await api('/master-import/apply',{...form,fingerprint:result.fingerprint});await onSave();setResult(null);setMessage('BOM·구매단가를 반영했습니다.');}catch(e:any){setMessage(e.message);}finally{setBusy(false);}}}>변경 확인 및 반영</button></div></>}</section>;
}
function ExceptionRules({period,onSave}:{period:string;onSave:()=>Promise<void>}) {
 const blank={part:'',customer:'',reason:'',enabled:true};
 const [rows,setRows]=useState<Row[]>([]),[form,setForm]=useState<Row>(blank),[before,setBefore]=useState<Row|null>(null),[message,setMessage]=useState(''),[saving,setSaving]=useState(false);
 const refresh=async()=>setRows(await api('/advanced/rules'));
 useEffect(()=>{refresh().catch(e=>setMessage(e.message));},[]);
 return <section className="panel"><div className="panelTitle"><h2>품번별 예외 규칙</h2><span>{period}에만 적용</span></div><p className="help">촉매사 이월·정산을 지정 납품처에 전량 연결합니다. ERP 입고·원본 파일·확정 마감은 바꾸지 않습니다. 전월 확정 이월과 직접 입력이 우선이고, 별도로 저장한 배부 수정도 우선합니다. 다른 월에는 자동 적용하지 않습니다. 28991-4C520은 기존 전주 직사급 규칙을 유지합니다.</p><div className="formGrid"><label>품번<input value={form.part} disabled={!!before} onChange={e=>setForm({...form,part:e.target.value})}/></label><label>예외 납품처<select value={form.customer} onChange={e=>setForm({...form,customer:e.target.value})}><option value="">선택</option>{['기아 화성','기아 광명','기아 광주','현대 아산','현대 울산','현대 전주','현대 글로비스','현대 위아','세종공업','현대 모비스'].map(c=><option key={c}>{c}</option>)}</select></label><label>사용 여부<select value={String(form.enabled)} onChange={e=>setForm({...form,enabled:e.target.value==='true'})}><option value="true">사용</option><option value="false">사용 안 함</option></select></label><label>변경 사유<input value={form.reason} onChange={e=>setForm({...form,reason:e.target.value})}/></label></div><p className="help">변경 전: {before?`${before.customer} · ${before.enabled?'사용':'사용 안 함'}`:'등록 없음'} → 변경 후: {form.customer||'미선택'} · {form.enabled?'사용':'사용 안 함'}</p><div className="formFooter"><span role="status">{message}</span><button disabled={saving} onClick={()=>{setForm(blank);setBefore(null);}}>새 규칙</button><button disabled={saving||!form.part||!form.customer||!form.reason.trim()} onClick={async()=>{setSaving(true);try{await api('/advanced/rules',{...form,period,before});await refresh();await onSave();setForm(blank);setBefore(null);setMessage('해당 월 예외 규칙을 저장했습니다.');}catch(e:any){setMessage(e.message);}finally{setSaving(false);}}}>변경 확인 및 저장</button></div><div className="scroll"><table><thead><tr><th>품번</th><th>납품처</th><th>사용</th><th>사유</th><th></th></tr></thead><tbody>{rows.filter(r=>r.period===period).map(r=><tr key={r.part}><td>{r.part}</td><td>{r.customer}</td><td>{r.enabled?'사용':'사용 안 함'}</td><td>{r.reason}</td><td><button onClick={()=>{setBefore(r);setForm({...r,enabled:!!r.enabled,reason:''});}}>수정</button></td></tr>)}</tbody></table></div></section>;
}
function AllocationManagement({preview,onSave}:{preview:Row|null;onSave:()=>Promise<void>}) {
 const [search,setSearch]=useState('');const entries=preview?.supplier_allocation?.entries||[];
 return <section className="panel"><div className="panelTitle"><h2>납품처 배부 수정</h2><span>{preview?.period} · {entries.length}개 항목</span></div><p className="help">자동 배부 또는 이전에 확인한 배부를 수정합니다. 원본 총수량은 유지해야 하며 수정 사유가 필요합니다. 원본 파일과 확정 마감은 바뀌지 않습니다. 전월 확정 이월·직접 입력과 일치하는 항목은 여기서 수정하지 않습니다.</p><div className="formFooter"><input aria-label="배부 품번 검색" placeholder="품번 검색" value={search} onChange={e=>setSearch(e.target.value)}/></div>{entries.filter((r:Row)=>r.part.includes(search.toUpperCase())).map((r:Row)=><AllocationEditor key={`${preview?.fingerprint}:${r.source_id}:${r.part}:${r.kind}`} item={r} preview={preview!} onSave={onSave}/>)}{!entries.length&&<p className="help">해당 월에 수정 가능한 촉매사 배부 자료가 없습니다.</p>}</section>;
}
function ChangeHistory() {
 const [open,setOpen]=useState(false);
 return <section className="panel"><details onToggle={e=>setOpen(e.currentTarget.open)}><summary className="historyHeading">자료 반영 이력 <span>필요할 때 펼쳐 조회 · 한 페이지 20건</span></summary>{open&&<HistoryBrowser/>}</details></section>;
}
function HistoryBrowser() {
 const blank={action:'',query:'',since:'',until:''};
 const [filters,setFilters]=useState(blank),[applied,setApplied]=useState(blank),[rows,setRows]=useState<Row[]>([]),[actions,setActions]=useState<string[]>([]),[next,setNext]=useState<number|null>(null),[cursors,setCursors]=useState<number[]>([0]),[message,setMessage]=useState(''),[busy,setBusy]=useState(false);
 const names:Row={part_rule:'품번 예외 규칙 변경',supplier_allocation:'납품처 배부 수정',master_link:'품번·납품처 연결 수정',bom_erp_master:'BOM·구매단가 반영',delete_source:'등록 삭제',reset_registrations:'등록 자료 전체 초기화',supplier_registration:'촉매사 마감 등록',finalize:'마감 확정',import:'자료 반영',register:'파일 등록'};
 const load=async(f=filters,stack=[0])=>{setBusy(true);try{const params=new URLSearchParams({...f,before:String(stack[stack.length-1]),limit:'20'});const r=await api('/advanced/history?'+params);setRows(r.items);setNext(r.next);setActions(r.actions);setCursors(stack);setApplied(f);setMessage('');}catch(e:any){setMessage(e.message);}finally{setBusy(false);}};
 useEffect(()=>{load(blank);},[]);
 return <div className="historyBrowser"><form onSubmit={e=>{e.preventDefault();load();}}><fieldset disabled={busy} className="historyFilters"><label>유형<select value={filters.action} onChange={e=>setFilters({...filters,action:e.target.value})}><option value="">전체 유형</option>{actions.map(a=><option key={a} value={a}>{names[a]||a}</option>)}</select></label><label>검색<input placeholder="파일명 · 품번 · 변경 사유" value={filters.query} onChange={e=>setFilters({...filters,query:e.target.value})}/></label><label>작업일 시작<input type="date" value={filters.since} onChange={e=>setFilters({...filters,since:e.target.value})}/></label><label>작업일 종료<input type="date" value={filters.until} onChange={e=>setFilters({...filters,until:e.target.value})}/></label><button type="submit">조회</button><button type="button" onClick={()=>{setFilters(blank);load(blank);}}>검색 초기화</button></fieldset></form><p className="help">날짜는 마감 월이 아닌 작업한 날짜입니다. 검색은 전체 이력에서 수행합니다. 조회 후 페이지를 이동하면 목록이 교체됩니다.</p><p role="status">{busy?'조회 중…':message}</p><div className="historyResults" aria-busy={busy}>{rows.map(r=><details key={r.id} className="allocationEditor"><summary>{r.created} · {names[r.action]||r.action}</summary>{r.files.map((f:string)=><p key={f}>{f}</p>)}{r.detail.reason&&<p>사유: {r.detail.reason}</p>}{('before' in r.detail||'after' in r.detail)&&<div className="formGrid"><section><h3>변경 전</h3><pre>{JSON.stringify(r.detail.before??'기록 없음',null,2)}</pre></section><section><h3>변경 후</h3><pre>{JSON.stringify(r.detail.after??'기록 없음',null,2)}</pre></section></div>}<details><summary>반영 상세 기록</summary><pre>{JSON.stringify(r.detail,null,2)}</pre></details></details>)}{!rows.length&&!busy&&<p className="help">조회 조건에 맞는 이력이 없습니다.</p>}</div><div className="formFooter"><button disabled={busy||cursors.length===1} onClick={()=>load(applied,cursors.slice(0,-1))}>이전</button><span>{cursors.length}페이지 · {rows.length}건</span><button disabled={busy||!next} onClick={()=>next&&load(applied,[...cursors,next])}>다음</button></div></div>;
}
function Evidence({rows}:{rows:Row[]}){
 if(rows[0]?.explanation) {const e=rows[0].explanation;return <div className="issueExplanation"><h3>① 수량이 확인된 원본</h3>{e.found.map((r:Row,i:number)=><p key={i}>{r.file}<br/>{r.sheet||'시트 정보 없음'}{r.row?` · ${r.row}행`:''} · {labels[r.kind]||r.kind} {fmt(r.quantity)}개 · {r.customer||'공통'} · {r.date}{r.source_id&&<><br/><a href={`/api/sources/${r.source_id}/download`}>이 원본 다운로드</a></>}</p>)}<h3>② 대조한 기준 자료와 누락 사유</h3>{e.checked.map((r:Row,i:number)=><p key={i}>{r.file} — {r.state}{r.source_id&&<><br/><a href={`/api/sources/${r.source_id}/download`}>기준 파일 다운로드</a></>}</p>)}<p>{e.missing}</p><h3>③ 보완할 내용</h3><p>{e.action}</p><small>{e.scope_note}</small><details><summary>전체 기록</summary><pre>{JSON.stringify(rows[0],null,2)}</pre></details></div>;}
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
