const $ = (id) => document.getElementById(id);

const input = $("log-input");
const fileInput = $("file-input");
const analyzeButton = $("analyze-button");
const errorBanner = $("error-banner");
const results = $("results");
let toastTimer;
let latestPayload = null;

async function loadCapabilities() {
  const toggle = $("ai-toggle");
  const status = $("model-status");
  const detail = $("ai-toggle-detail");
  toggle.disabled = true;
  try {
    const response = await fetch("/api/capabilities");
    if (!response.ok) throw new Error("Capability check failed");
    const capabilities = await response.json();
    if (capabilities.ai_available) {
      toggle.disabled = false;
      status.textContent = `${capabilities.model || "AI"} AVAILABLE`;
      detail.textContent = `Optional ${capabilities.model || "AI"} root-cause reasoning`;
    } else {
      toggle.checked = false;
      status.textContent = "AI: KEY REQUIRED";
      detail.textContent = "Unavailable · set OPENAI_API_KEY to enable";
    }
  } catch (_error) {
    toggle.checked = false;
    status.textContent = "AI: STATUS UNKNOWN";
    detail.textContent = "Availability check failed · offline analysis remains ready";
  }
}

function updateInputMeta(name = "untitled.log") {
  const count = input.value ? input.value.split(/\r?\n/).length : 0;
  $("line-count").textContent = `${count} line${count === 1 ? "" : "s"}`;
  $("file-name").textContent = name;
}

function showError(message) {
  errorBanner.textContent = message;
  errorBanner.hidden = false;
}

function clearError() {
  errorBanner.hidden = true;
  errorBanner.textContent = "";
}

function showToast(message) {
  $("toast").textContent = message;
  $("toast").classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $("toast").classList.remove("show"), 1800);
}

function setLoading(active) {
  results.setAttribute("aria-busy", String(active));
  $("loading-state").hidden = !active;
  if (active) {
    $("empty-state").hidden = true;
    $("analysis-content").hidden = true;
    $("analysis-state").textContent = "ANALYZING";
    analyzeButton.disabled = true;
    analyzeButton.querySelector(".button-label").textContent = "Analyzing…";
  } else {
    analyzeButton.disabled = false;
    analyzeButton.querySelector(".button-label").textContent = "Analyze trace";
  }
}

async function loadSample() {
  clearError();
  try {
    const response = await fetch("/api/sample");
    if (!response.ok) throw new Error(`Sample request failed (${response.status})`);
    const data = await response.json();
    input.value = data.log_text;
    updateInputMeta(data.name || "navigation_failure.log");
    input.focus();
    showToast("Sample trace loaded");
    return true;
  } catch (error) {
    showError(error.message);
    return false;
  }
}

async function runSampleAnalysis() {
  if (await loadSample()) await analyze();
}

function severityClass(value) {
  return String(value || "INFO").toLowerCase();
}

function text(value, fallback = "—") {
  return value === null || value === undefined || value === "" ? fallback : String(value);
}

function incidentCard(incident) {
  const item = document.createElement("li");
  item.className = "incident-card";

  const top = document.createElement("div");
  top.className = "incident-top";
  const badge = document.createElement("span");
  badge.className = `severity ${severityClass(incident.severity)}`;
  badge.textContent = text(incident.severity, "INFO");
  const meta = document.createElement("span");
  meta.className = "meta";
  const first = incident.first_timestamp;
  const last = incident.last_timestamp;
  const timeRange = first ? (last && last !== first ? `${first} → ${last}` : first) : "time unavailable";
  meta.textContent = `${text(incident.node, "unknown node")} · ${incident.count || 1} occurrence${incident.count === 1 ? "" : "s"} · ${timeRange}`;
  top.append(badge, meta);

  const title = document.createElement("h4");
  title.textContent = text(incident.title, "Unclassified incident");
  const causeLabel = document.createElement("p");
  causeLabel.className = "card-label";
  causeLabel.textContent = "Likely cause";
  const cause = document.createElement("p");
  cause.textContent = text(incident.root_cause, incident.message);

  const recommendationLabel = document.createElement("p");
  recommendationLabel.className = "card-label";
  recommendationLabel.textContent = "Recommended action";
  const recommendation = document.createElement("div");
  recommendation.className = "recommendation";
  recommendation.textContent = text(incident.recommendation, "Inspect the cited evidence and surrounding log context.");

  const copy = document.createElement("button");
  copy.type = "button";
  copy.className = "copy-button";
  copy.textContent = "COPY NEXT STEP";
  copy.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(recommendation.textContent);
      showToast("Next step copied");
    } catch (_error) {
      showError("Clipboard unavailable. Select and copy the recommended action manually.");
    }
  });

  const evidenceEvents = incident.evidence || [];
  const evidenceLabel = document.createElement("p");
  evidenceLabel.className = "card-label";
  evidenceLabel.textContent = "Primary evidence";
  const primaryEvidence = document.createElement("pre");
  primaryEvidence.className = "primary-evidence";
  const primary = evidenceEvents[0];
  primaryEvidence.textContent = primary
    ? `L${primary.line_number || "?"} [${text(primary.severity, "INFO")}] [${text(primary.node, "unknown node")}] ${primary.message || primary.raw || ""}`
    : "No structured evidence available.";

  const details = document.createElement("details");
  details.className = "evidence";
  const summary = document.createElement("summary");
  const omitted = incident.evidence_omitted || 0;
  summary.textContent = `VIEW ALL EVIDENCE (${evidenceEvents.length}${omitted ? ` + ${omitted} omitted` : ""})`;
  const pre = document.createElement("pre");
  pre.textContent = evidenceEvents
    .map((event) => `L${event.line_number || "?"} ${event.raw || event.message || ""}`)
    .join("\n");
  details.append(summary, pre);
  item.append(top, title, causeLabel, cause, recommendationLabel, recommendation, copy, evidenceLabel, primaryEvidence, details);
  return item;
}

function renderAiAnalysis(payload) {
  const ai = payload.ai || {
    requested: Boolean(payload.ai_used || payload.ai_error),
    used: Boolean(payload.ai_used),
    status: payload.ai_used ? "succeeded" : "not_requested",
    model: "GPT",
    analysis: payload.ai_analysis,
    error: payload.ai_error || null,
  };
  const panel = $("ai-panel");
  const status = $("ai-status-detail");
  const steps = $("ai-next-steps");
  steps.replaceChildren();

  if (!ai.requested && !ai.used) {
    panel.hidden = true;
    $("ai-root-cause").textContent = "";
    $("ai-confidence").textContent = "—";
    status.textContent = "";
    return;
  }

  panel.hidden = false;
  const contractAnalysis = payload.ai ? payload.ai.analysis : null;
  const analysis = contractAnalysis || payload.ai_analysis;
  if (ai.used && analysis) {
    $("ai-title").textContent = `${ai.model || "AI"} assessment`;
    $("ai-root-cause").textContent = text(analysis.root_cause, "No root cause returned.");
    const confidence = Number(analysis.confidence);
    $("ai-confidence").textContent = Number.isFinite(confidence)
      ? `${Math.round(confidence * 100)}% confidence`
      : "Confidence unavailable";
    status.textContent = `${ai.model || "AI"} enrichment completed. Model-generated recommendations — verify before acting.`;
    (analysis.next_steps || []).forEach((step) => {
      const item = document.createElement("li");
      item.textContent = step;
      steps.append(item);
    });
    if (!steps.children.length) {
      const item = document.createElement("li");
      item.textContent = "Review the deterministic incident recommendations.";
      steps.append(item);
    }
  } else {
    $("ai-title").textContent = "AI assessment";
    $("ai-root-cause").textContent = "AI enrichment did not run.";
    $("ai-confidence").textContent = String(ai.status || "unavailable").toUpperCase();
    status.textContent = ai.error || "Deterministic offline analysis is shown below.";
    const item = document.createElement("li");
    item.textContent = "Use the offline incident timeline and cited evidence.";
    steps.append(item);
  }
}

function exportAnalysis() {
  if (!latestPayload) {
    showError("Run an analysis before exporting a report.");
    return;
  }
  const blob = new Blob([JSON.stringify(latestPayload, null, 2)], {type: "application/json"});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "ros-trace-report.json";
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  showToast("JSON report exported");
}

function render(payload) {
  latestPayload = payload;
  $("export-button").hidden = false;
  const report = payload.report;
  const summary = report.summary;
  const counts = summary.severity_counts || {};
  $("error-count").textContent = (counts.ERROR || 0) + (counts.FATAL || 0);
  $("warning-count").textContent = counts.WARN || 0;
  $("node-count").textContent = (summary.nodes || []).length;
  $("incident-count").textContent = summary.incident_count || 0;
  const completedModel = payload.ai && payload.ai.model ? payload.ai.model.toUpperCase() : "AI";
  $("analysis-state").textContent = payload.ai_used ? `${completedModel} ENRICHED` : "OFFLINE COMPLETE";

  const range = summary.time_range || {};
  $("timeline-span").textContent = range.start ? `${range.start} → ${range.end}` : `${summary.total_lines || 0} lines`;
  const list = $("incident-list");
  list.replaceChildren();
  if ((report.incidents || []).length) {
    report.incidents.forEach((incident) => list.append(incidentCard(incident)));
  } else {
    const clean = document.createElement("li");
    clean.className = "incident-card";
    clean.innerHTML = "<h4>No warning or error incidents detected</h4><p>The parser completed successfully. Review informational lines if the robot still behaved unexpectedly.</p>";
    list.append(clean);
  }

  const nodeList = $("node-list");
  nodeList.replaceChildren();
  (summary.nodes || ["No named nodes"]).forEach((node) => {
    const chip = document.createElement("span");
    chip.className = "node-chip";
    chip.textContent = node;
    nodeList.append(chip);
  });

  renderAiAnalysis(payload);
  if (payload.ai_error) showError(payload.ai_error);
  $("empty-state").hidden = true;
  $("analysis-content").hidden = false;
}

async function analyze() {
  clearError();
  if (!input.value.trim()) {
    showError("Paste a ROS log or load the sample before analyzing.");
    input.focus();
    return;
  }
  setLoading(true);
  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({log_text: input.value, use_ai: $("ai-toggle").checked}),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail ? JSON.stringify(body.detail) : `Analysis failed (${response.status})`);
    }
    render(await response.json());
    results.scrollIntoView({behavior: "smooth", block: "start"});
    $("results-title").focus({preventScroll: true});
  } catch (error) {
    showError(error.message || "Analysis failed");
    $("empty-state").hidden = false;
    $("analysis-state").textContent = "FAILED";
  } finally {
    setLoading(false);
  }
}

function loadFile(file) {
  if (!file) return;
  if (file.size > 1_000_000) {
    showError("Keep demo logs under 1 MB.");
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    input.value = String(reader.result || "");
    updateInputMeta(file.name);
    showToast("Log file loaded");
  };
  reader.onerror = () => showError("Could not read that file.");
  reader.readAsText(file);
}

$("sample-button").addEventListener("click", loadSample);
$("empty-sample-button").addEventListener("click", runSampleAnalysis);
$("upload-button").addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => loadFile(fileInput.files[0]));
input.addEventListener("input", () => updateInputMeta($("file-name").textContent));
analyzeButton.addEventListener("click", analyze);
$("export-button").addEventListener("click", exportAnalysis);

for (const eventName of ["dragenter", "dragover"]) {
  document.addEventListener(eventName, (event) => { event.preventDefault(); document.body.classList.add("dragging"); });
}
for (const eventName of ["dragleave", "drop"]) {
  document.addEventListener(eventName, (event) => { event.preventDefault(); document.body.classList.remove("dragging"); });
}
document.addEventListener("drop", (event) => loadFile(event.dataTransfer.files[0]));
loadCapabilities();
updateInputMeta();
