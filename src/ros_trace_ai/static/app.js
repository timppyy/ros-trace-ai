const $ = (id) => document.getElementById(id);

const input = $("log-input");
const fileInput = $("file-input");
const analyzeButton = $("analyze-button");
const sampleButtons = [$("sample-button"), $("empty-sample-button")];
const errorBanner = $("error-banner");
const results = $("results");
let toastTimer;

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
  } catch (error) {
    showError(error.message);
  }
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
  meta.textContent = `${text(incident.node, "unknown node")} · ${incident.count || 1} occurrence${incident.count === 1 ? "" : "s"}`;
  top.append(badge, meta);

  const title = document.createElement("h4");
  title.textContent = text(incident.title, "Unclassified incident");
  const cause = document.createElement("p");
  cause.textContent = text(incident.root_cause, incident.message);

  const recommendation = document.createElement("div");
  recommendation.className = "recommendation";
  recommendation.textContent = text(incident.recommendation, "Inspect the cited evidence and surrounding log context.");

  const copy = document.createElement("button");
  copy.type = "button";
  copy.className = "copy-button";
  copy.textContent = "COPY NEXT STEP";
  copy.addEventListener("click", async () => {
    await navigator.clipboard.writeText(recommendation.textContent);
    showToast("Next step copied");
  });

  const details = document.createElement("details");
  details.className = "evidence";
  const summary = document.createElement("summary");
  summary.textContent = `VIEW EVIDENCE (${(incident.evidence || []).length})`;
  const pre = document.createElement("pre");
  pre.textContent = (incident.evidence || [])
    .map((event) => `L${event.line_number || "?"} ${event.raw || event.message || ""}`)
    .join("\n");
  details.append(summary, pre);
  item.append(top, title, cause, recommendation, copy, details);
  return item;
}

function render(payload) {
  const report = payload.report;
  const summary = report.summary;
  const counts = summary.severity_counts || {};
  $("error-count").textContent = (counts.ERROR || 0) + (counts.FATAL || 0);
  $("warning-count").textContent = counts.WARN || 0;
  $("node-count").textContent = (summary.nodes || []).length;
  $("incident-count").textContent = summary.incident_count || 0;
  $("analysis-state").textContent = payload.ai_used ? "GPT-5.6 ENRICHED" : "OFFLINE COMPLETE";

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

sampleButtons.forEach((button) => button.addEventListener("click", loadSample));
$("upload-button").addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => loadFile(fileInput.files[0]));
input.addEventListener("input", () => updateInputMeta($("file-name").textContent));
analyzeButton.addEventListener("click", analyze);

for (const eventName of ["dragenter", "dragover"]) {
  document.addEventListener(eventName, (event) => { event.preventDefault(); document.body.classList.add("dragging"); });
}
for (const eventName of ["dragleave", "drop"]) {
  document.addEventListener(eventName, (event) => { event.preventDefault(); document.body.classList.remove("dragging"); });
}
document.addEventListener("drop", (event) => loadFile(event.dataTransfer.files[0]));
updateInputMeta();
