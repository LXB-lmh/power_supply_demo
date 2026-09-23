/** 与后端的 HTTP 封装。classifyMaterials 只做「本章建议」，真正评估走 createJob。 */
import axios from "axios";

/** 优先用拖放补上的相对路径，便于后端按文件夹结构识别材料。 */
function relPath(file) {
  return String(file?.relativePath || file?.webkitRelativePath || file?.name || "").replace(/\\/g, "/");
}

/** MaterialDrop 存的是 { uid, name, raw }；评估框有时直接是 File。统一成可上传的 Blob。 */
function asUploadFile(item) {
  if (!item) return null;
  if (typeof Blob !== "undefined" && item instanceof Blob) return item;
  const raw = item.raw;
  if (raw && typeof Blob !== "undefined" && raw instanceof Blob) return raw;
  return null;
}

function appendFiles(form, files) {
  const paths = [];
  for (const item of files || []) {
    const file = asUploadFile(item);
    if (!file) continue;
    const rel = relPath(file) || file.name || item.name || "material.bin";
    paths.push(rel);
    form.append("files", file, file.name || item.name || "material.bin");
  }
  if (!paths.length) {
    throw new Error("没有可上传的文件（请重新放入 Word 后再检测）");
  }
  form.append("file_relpaths", JSON.stringify(paths));
}

export function getCatalog() {
  return axios.get("/api/catalog");
}

/** 材料分拣：先挑供电（纯触网不看），再对照去年报告目录全文分到第 3～11 章。 */
export function classifyMaterials(
  files,
  domainId = "power_supply",
  useLlm = true,
  onUploadProgress,
  assessmentYear,
  priorFile,
  useCached = false,
) {
  const form = new FormData();
  appendFiles(form, files);
  form.append("domain_id", domainId);
  form.append("use_llm", useLlm ? "true" : "false");
  form.append("use_cached", useCached ? "true" : "false");
  if (assessmentYear) form.append("assessment_year", String(assessmentYear));
  if (priorFile) {
    form.append("prior_report", priorFile, priorFile.name || "prior.docx");
  }
  return axios.post("/api/classify-materials", form, {
    timeout: 600000,
    onUploadProgress(event) {
      if (!onUploadProgress || !event.total) return;
      onUploadProgress(Math.round((event.loaded / event.total) * 28));
    },
  });
}

/** 上次分拣结果（服务端 parse_cache，无需重新解析 Word）。 */
export function reuseClassifyCache(domainId = "power_supply", assessmentYear) {
  const form = new FormData();
  form.append("domain_id", domainId);
  if (assessmentYear) form.append("assessment_year", String(assessmentYear));
  return axios.post("/api/classify-materials/reuse", form, { timeout: 120000 });
}

export function getParseCacheInfo(domainId = "power_supply") {
  return axios.get("/api/parse-cache", { params: { domain_id: domainId } });
}

/** 从 parse_cache/materials 取上次分拣落盘的文件（供本章建议加入）。 */
export function fetchParseCacheFile(domainId, relpath) {
  return axios.get("/api/parse-cache/file", {
    params: { domain_id: domainId, relpath },
    responseType: "blob",
    timeout: 120000,
  });
}

/** 评估上传后的预览（线路/区段），与分拣接口分开。 */
export function previewFiles(files) {
  const form = new FormData();
  appendFiles(form, files);
  return axios.post("/api/preview", form);
}

/** 开始评估：把当前章上传框里的材料交给后端，不是分拣。去年完整报告单独字段，不并进 files。 */
export function createJob(
  files,
  mode = "llm",
  selectedLines = [],
  selectedSegments = [],
  assessmentYear,
  domainId = "power_supply",
  subsystemId = "stray_current",
  chapterId = "ch3",
  priorFile,
) {
  const form = new FormData();
  appendFiles(form, files);
  form.append("mode", mode);
  form.append("auto_confirm", "false");
  form.append("selected_lines", JSON.stringify(selectedLines));
  form.append("selected_segments", JSON.stringify(selectedSegments));
  form.append("assessment_year", String(assessmentYear || new Date().getFullYear()));
  form.append("domain_id", domainId);
  form.append("subsystem_id", subsystemId);
  form.append("chapter_id", chapterId);
  if (priorFile) {
    form.append("prior_report", priorFile, priorFile.name || "prior.docx");
  }
  return axios.post("/api/jobs", form);
}

export function getJob(jobId) {
  return axios.get(`/api/jobs/${jobId}`);
}

export function listReports(fingerprint) {
  return axios.get("/api/reports", { params: { fingerprint } });
}

export function deleteReports(payload) {
  return axios.post("/api/reports/delete", payload);
}

export function reportUrl(jobId) {
  return `/api/jobs/${jobId}/report`;
}

/** 逻辑性检测：上传完整报告或单章 Word。结果只返回条目，不生成报告。 */
export function runLogicCheck(files, { mode = "full", chapterId = "", domainId = "", assessmentYear } = {}) {
  const form = new FormData();
  appendFiles(form, files);
  form.append("mode", mode);
  if (chapterId) form.append("chapter_id", chapterId);
  if (domainId) form.append("domain_id", domainId);
  if (assessmentYear) form.append("assessment_year", String(assessmentYear));
  return axios.post("/api/logic-check", form, { timeout: 300000 });
}

/**
 * 逻辑性检测（流式）：后端逐行推送 NDJSON，前端拿到真实阶段进度。
 * onProgress(percent, label) 在每个检测阶段回调；Promise resolve 的最终结果与 runLogicCheck 一致。
 */
export async function runLogicCheckStream(
  files,
  { mode = "full", chapterId = "", domainId = "", assessmentYear } = {},
  onProgress,
) {
  const form = new FormData();
  appendFiles(form, files);
  form.append("mode", mode);
  if (chapterId) form.append("chapter_id", chapterId);
  if (domainId) form.append("domain_id", domainId);
  if (assessmentYear) form.append("assessment_year", String(assessmentYear));

  const resp = await fetch("/api/logic-check/stream", { method: "POST", body: form });
  if (!resp.ok || !resp.body) {
    let detail = `检测请求失败（HTTP ${resp.status}）`;
    try {
      const errBody = await resp.json();
      if (errBody && errBody.detail) detail = errBody.detail;
    } catch (_) {
      /* 错误体不是 JSON，沿用默认文案 */
    }
    throw new Error(detail);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let result = null;
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let nl;
    while ((nl = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, nl).trim();
      buffer = buffer.slice(nl + 1);
      if (!line) continue;
      let evt;
      try {
        evt = JSON.parse(line);
      } catch (_) {
        continue;
      }
      if (evt.type === "progress") {
        if (typeof onProgress === "function") {
          onProgress(Number(evt.percent) || 0, evt.label || "");
        }
      } else if (evt.type === "result") {
        result = evt.data;
      } else if (evt.type === "error") {
        throw new Error(evt.detail || "检测失败");
      }
    }
  }
  if (!result) throw new Error("检测未返回结果，请重试");
  return result;
}

/**
 * 导出逻辑性检测结果 Word：把前端结果 JSON 回传，后端内存生成 docx，返回 Blob。
 * 不重新检测、不落盘，不影响检测与报告生成。
 */
export async function exportLogicCheck(payload) {
  const resp = await fetch("/api/logic-check/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    let detail = `导出失败（HTTP ${resp.status}）`;
    try {
      const errBody = await resp.json();
      if (errBody && errBody.detail) detail = errBody.detail;
    } catch (_) {
      /* 错误体不是 JSON，沿用默认文案 */
    }
    throw new Error(detail);
  }
  return resp.blob();
}

/** 团标附录 A 单台设备评估（不进出报告生成）。 */
export function getDeviceEvalCatalog(standardId) {
  return axios.get("/api/device-eval/catalog", { params: { standard_id: standardId } });
}

export function runDeviceEval(payload) {
  return axios.post("/api/device-eval/evaluate", payload);
}
