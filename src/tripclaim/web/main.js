const API_BASE = window.location.origin;
const stateSteps = ["待命", "创建案例", "读取资料", "材料识别", "规则校验", "结论生成", "已完成"];
const DEFAULT_FOLDER = "D:\\GitProgram\\TripClaim Pilot\\报销材料";

let currentCaseId = null;
let lastCase = null;
let currentFolder = DEFAULT_FOLDER;

function esc(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function addLog(tag, msg) {
  const root = document.getElementById("logContainer");
  const line = document.createElement("div");
  line.className = "log-line";
  line.innerHTML = `<span class="log-time">[${new Date().toLocaleTimeString()}]</span><b>${esc(tag)}</b> ${esc(msg)}`;
  root.appendChild(line);
  root.scrollTop = root.scrollHeight;
}

function renderState(activeIndex) {
  const row = document.getElementById("stateRow");
  row.innerHTML = "";
  stateSteps.forEach((step, i) => {
    const node = document.createElement("div");
    node.className = "state-node";
    if (i < activeIndex) node.classList.add("done");
    if (i === activeIndex) node.classList.add("active");
    node.textContent = step;
    row.appendChild(node);
    if (i < stateSteps.length - 1) {
      const arrow = document.createElement("div");
      arrow.className = "state-arrow";
      arrow.textContent = "→";
      row.appendChild(arrow);
    }
  });
  document.getElementById("stageText").textContent = stateSteps[activeIndex] || "待命";
}

function renderFileTable(files) {
  const root = document.getElementById("leftFileTable");
  document.getElementById("leftFileCount").textContent = `${files.length} 个`;
  if (!files.length) {
    root.textContent = "暂无文件";
    return;
  }
  root.innerHTML = `
    <table class="table">
      <thead><tr><th>文件</th><th>类型</th><th>大小KB</th></tr></thead>
      <tbody>
        ${files.map((f) => `<tr><td>${esc(f.name)}</td><td>${esc(f.type)}</td><td>${esc(f.size_kb)}</td></tr>`).join("")}
      </tbody>
    </table>
  `;
}

function renderCaseStats(runData) {
  const stats = runData?.result?.stats || {};
  document.getElementById("caseSummary").textContent = `${runData?.case_id ?? "--"} / ${runData?.decision ?? "--"}`;
  const fraudTotal = runData?.result?.fraud_score_total || 0;
    document.getElementById("caseStats").innerHTML = `
      <div>总文件数：${esc(stats.total_files ?? 0)}</div>
      <div>高风险问题：${esc(stats.high_issues ?? 0)}</div>
      <div>中风险问题：${esc(stats.medium_issues ?? 0)}</div>
      <div style="color: ${fraudTotal > 0 ? '#ff4d4f' : 'inherit'}">防伪分：${esc(fraudTotal)}</div>
    `;
}

function statusClass(status) {
  if (status === "合规") return "tag-ok";
  if (status === "待复核") return "tag-warn";
  return "tag-bad";
}

function renderBadFiles(fileChecks) {
  const bad = (fileChecks || []).filter((x) => x.status === "不合规" || x.status === "待复核");
  const root = document.getElementById("badFiles");
  if (!bad.length) {
    root.innerHTML = '<span class="tag-ok">无问题文件</span>';
    return;
  }
  root.innerHTML = `
    <table class="table">
      <thead><tr><th>文件</th><th>状态</th><th>原因</th></tr></thead>
      <tbody>
        ${bad.map((f) => `<tr><td>${esc(f.file)}</td><td class="${statusClass(f.status)}">${esc(f.status)}</td><td>${esc(f.reasons || "-")}</td></tr>`).join("")}
      </tbody>
    </table>
  `;
}

function logFileChecks(fileChecks) {
  for (const item of fileChecks || []) {
    const name = item.file || "(未知文件)";
    const status = item.status || "待复核";
    if (status === "合规") {
      addLog("文件通过", `${name}`);
    } else {
      const reason = item.reasons || "未提供原因";
      addLog("文件未通过", `${name} | ${status} | 原因：${reason}`);
    }
  }
}

function setTopChips(apiConnected) {
  const apiChip = document.getElementById("apiChip");
  apiChip.className = `chip ${apiConnected ? "green" : "red"}`;
  apiChip.textContent = `API: ${apiConnected ? "connected" : "disconnected"}`;
  document.getElementById("caseChip").textContent = `案例: ${currentCaseId ?? "--"}`;
  const decision = lastCase?.decision || "待命";
  document.getElementById("decisionChip").textContent = `结论: ${decision}`;
}

function setProgress(total, checked) {
  const pct = total <= 0 ? 0 : Math.round((checked / total) * 100);
  document.getElementById("progressText").textContent = `${checked}/${total}`;
  document.getElementById("progressBar").style.width = `${pct}%`;
}

async function pingApi() {
  try {
    const r = await fetch(`${API_BASE}/health`, { cache: "no-store" });
    setTopChips(r.ok);
    if (!r.ok) addLog("系统", `后端不可用: ${r.status}`);
  } catch (e) {
    setTopChips(false);
    addLog("系统", `后端连接失败: ${e.message || e}`);
  }
}

async function listFiles() {
  const folder = (currentFolder || "").trim();
  if (!folder) {
    addLog("系统", "当前目录为空");
    return;
  }
  try {
    const resp = await fetch(`${API_BASE}/files/list`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder_path: folder }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      addLog("错误", data?.detail || "读取目录失败");
      return;
    }
    renderFileTable(data.files || []);
    setProgress((data.files || []).length, 0);
    addLog("系统", `读取到 ${data.files.length} 个文件`);
  } catch (e) {
    addLog("错误", e.message || String(e));
  }
}

async function pickFolder() {
  const current = (currentFolder || "").trim();
  try {
    const resp = await fetch(`${API_BASE}/folders/pick`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ initial_path: current || null }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      addLog("错误", data?.detail || "选择目录失败");
      return;
    }
    currentFolder = data.folder_path || currentFolder;
    document.getElementById("currentFolder").textContent = currentFolder;
    addLog("系统", `已选择目录: ${currentFolder}`);
  } catch (e) {
    addLog("错误", e.message || String(e));
  }
}

async function runAudit() {
  const folder = (currentFolder || "").trim();
  if (!folder) {
    addLog("系统", "当前目录为空");
    return;
  }
  try {
    await listFiles();
    renderState(1);
    const created = await fetch(`${API_BASE}/cases`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder_path: folder }),
    });
    const createData = await created.json();
    if (!created.ok) {
      addLog("错误", createData?.detail || "创建案例失败");
      return;
    }
    currentCaseId = createData.case_id;
    setTopChips(true);
    addLog("案例", `创建成功 case_id=${currentCaseId}`);

    renderState(4);
    const runResp = await fetch(`${API_BASE}/cases/${currentCaseId}/run`, { method: "POST" });
    const runData = await runResp.json();
    if (!runResp.ok) {
      addLog("错误", runData?.detail || "审批执行失败");
      return;
    }
    lastCase = runData;
    const fileChecks = runData?.result?.file_checks || [];
    renderBadFiles(fileChecks);
    renderCaseStats(runData);
    logFileChecks(fileChecks);
    setProgress(fileChecks.length, fileChecks.length);
    renderState(6);
    setTopChips(true);
    addLog("结果", `审批完成: ${runData.decision}`);
  } catch (e) {
    addLog("错误", e.message || String(e));
  }
}

async function submitManualReview() {
  if (!currentCaseId) {
    addLog("系统", "请先执行自动校验");
    return;
  }
  const reviewer = document.getElementById("reviewer").value.trim() || "财务老师";
  const decision = document.getElementById("manualDecision").value;
  const comment = document.getElementById("manualComment").value.trim();
  try {
    const resp = await fetch(`${API_BASE}/cases/${currentCaseId}/manual-review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reviewer, decision, comment }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      addLog("错误", data?.detail || "人工复核失败");
      return;
    }
    addLog("人工复核", `已提交: ${decision}`);
  } catch (e) {
    addLog("错误", e.message || String(e));
  }
}

function boot() {
  document.getElementById("currentFolder").textContent = currentFolder;
  renderState(0);
  setTopChips(false);
  document.getElementById("btnPickFolder").addEventListener("click", pickFolder);
  document.getElementById("btnListFiles").addEventListener("click", listFiles);
  document.getElementById("btnRunAudit").addEventListener("click", runAudit);
  document.getElementById("btnManualReview").addEventListener("click", submitManualReview);
  document.getElementById("btnClearLog").addEventListener("click", () => {
    document.getElementById("logContainer").innerHTML = "";
  });
  pingApi();
  addLog("系统", "界面就绪");
}

document.addEventListener("DOMContentLoaded", boot);
