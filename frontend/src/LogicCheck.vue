<script setup>
/** 逻辑性检测页：供电/触网分开；完整报告与单章都只在右侧列出错误，不生成报告。 */
import { computed, ref } from "vue";
import { ElMessage } from "element-plus";
import MaterialDrop from "./MaterialDrop.vue";
import { exportLogicCheck, runLogicCheckStream } from "./api";

const props = defineProps({
  chapters: { type: Array, default: () => [] },
  assessmentYear: { type: [Number, String], default: () => new Date().getFullYear() },
});

const fullItems = ref([]);
const chapterItems = ref([]);
const chapterId = ref("ch3");
const domainFull = ref("power_supply");
const domainChapter = ref("power_supply");
const fullLoading = ref(false);
const chapterLoading = ref(false);
const fullResult = ref(null);
const chapterResult = ref(null);
// 真实阶段进度 { percent: 0~100, label: '当前步骤' }，仅在对应检测进行中显示
const fullProg = ref(null);
const chapterProg = ref(null);
// 导出 Word 的按钮 loading（与检测互不影响）
const fullExporting = ref(false);
const chapterExporting = ref(false);

const _CN_NUMS = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二"];

const domainOptions = [
  { id: "power_supply", label: "供电报告" },
  { id: "overhead", label: "触网报告" },
];

const chapterOptions = computed(() =>
  (props.chapters || [])
    .filter((c) => Number(c.no) >= 3 && Number(c.no) <= 11)
    .map((c) => ({
      id: c.id,
      label: `第${c.no}章 ${c.name}`,
    })),
);

async function runFull() {
  if (!fullItems.value.length) {
    ElMessage.warning("请先放入完整评估报告（Word）");
    return;
  }
  fullLoading.value = true;
  fullResult.value = null;
  fullProg.value = { percent: 1, label: "正在上传文件…" };
  try {
    const data = await runLogicCheckStream(
      fullItems.value,
      { mode: "full", domainId: domainFull.value, assessmentYear: props.assessmentYear },
      (percent, label) => {
        fullProg.value = { percent, label };
      },
    );
    fullResult.value = data;
    fullProg.value = { percent: 100, label: "检测完成" };
    if (data.finding_count) ElMessage.warning(data.message);
    else ElMessage.success(data.message || "未发现问题");
  } catch (e) {
    ElMessage.error(e?.message || "检测失败");
  } finally {
    fullLoading.value = false;
  }
}

async function runChapter() {
  if (!chapterItems.value.length) {
    ElMessage.warning("请先放入单章或完整报告（Word）");
    return;
  }
  chapterLoading.value = true;
  chapterResult.value = null;
  chapterProg.value = { percent: 1, label: "正在上传文件…" };
  try {
    const data = await runLogicCheckStream(
      chapterItems.value,
      {
        mode: "chapter",
        chapterId: chapterId.value,
        domainId: domainChapter.value,
        assessmentYear: props.assessmentYear,
      },
      (percent, label) => {
        chapterProg.value = { percent, label };
      },
    );
    chapterResult.value = data;
    chapterProg.value = { percent: 100, label: "检测完成" };
    if (data.finding_count) ElMessage.warning(data.message);
    else ElMessage.success(data.message || "未发现问题");
  } catch (e) {
    ElMessage.error(e?.message || "检测失败");
  } finally {
    chapterLoading.value = false;
  }
}

function kindLabel(kind) {
  if (kind === "severe") return "逻辑错误";
  if (kind === "year") return "年份错误";
  if (kind === "logic") return "计算错误";
  if (kind === "typo") return "错别字";
  if (kind === "punct") return "标点错误";
  if (kind === "language") return "语言不通顺";
  return kind || "其它";
}

// 左栏：轻微问题；右栏：逻辑问题（计算/年份/上下文逻辑矛盾）
const MINOR_KINDS = ["typo", "punct", "language"];
const MAJOR_KINDS = ["logic", "year", "severe"];

function splitFindings(list) {
  const items = list || [];
  return {
    minor: items.filter((i) => MINOR_KINDS.includes(i.kind)),
    major: items.filter((i) => MAJOR_KINDS.includes(i.kind)),
  };
}

const fullGroups = computed(() => splitFindings(fullResult.value?.findings));
const chapterGroups = computed(() => splitFindings(chapterResult.value?.findings));

function chapterRows(result) {
  const found = new Map((result?.chapters_found || []).map((c) => [Number(c.no), c]));
  return Array.from({ length: 9 }, (_, i) => i + 3).map((no) => ({ no, found: found.get(no) || null }));
}
const fullChapterRows = computed(() => chapterRows(fullResult.value));
const chapterChapterRows = computed(() => chapterRows(chapterResult.value));
const selectedChapterNo = computed(() => {
  const m = String(chapterId.value || "").match(/\d+/);
  return m ? Number(m[0]) : null;
});
const selectedChapterFound = computed(() => {
  const no = selectedChapterNo.value;
  if (!no || !chapterResult.value) return false;
  return (chapterResult.value.chapters_found || []).some((c) => Number(c.no) === no);
});

// ── 一键导出检测结果 Word（只读当前结果，不重新检测） ─────────────────────
function exportPayload(result) {
  return {
    findings: result.findings,
    finding_count: result.finding_count,
    summary: result.summary,
    domain_label: result.domain_label,
    assessment_year: props.assessmentYear,
    mode: result.mode,
    chapter_id: result.chapter_id,
    source: result.source,
  };
}

function exportFilename(result) {
  const ymd = new Date().toISOString().slice(0, 10).replace(/-/g, "");
  const domain = result.domain_label || "评估报告";
  let name = `逻辑性检测结果-${domain}-${ymd}`;
  if (result.mode === "chapter") {
    const m = String(result.chapter_id || "").match(/\d+/);
    if (m) name += `-第${_CN_NUMS[Number(m[0])] || m[0]}章`;
  }
  return name + ".docx";
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function doExport(result, flag) {
  if (!result || !result.findings) {
    ElMessage.warning("暂无可导出的检测结果");
    return;
  }
  flag.value = true;
  try {
    const blob = await exportLogicCheck(exportPayload(result));
    downloadBlob(blob, exportFilename(result));
    ElMessage.success("已导出 Word");
  } catch (e) {
    ElMessage.error(e?.message || "导出失败");
  } finally {
    flag.value = false;
  }
}

function exportFull() {
  return doExport(fullResult.value, fullExporting);
}

function exportChapter() {
  return doExport(chapterResult.value, chapterExporting);
}
</script>

<template>
  <div class="logic-page">
    <div class="logic-stack">
      <section class="logic-row">
        <div class="logic-panel logic-upload">
          <header class="logic-card-head">
            <div>
              <h2>完整评估报告逻辑性检测</h2>
              <p>上传整本年报或合并稿，检查第3章到第11章的错别字、标点、语言、计算、年份，以及跨章矛盾。</p>
            </div>
            <div class="logic-actions">
              <el-select v-model="domainFull" style="width: 128px">
                <el-option v-for="opt in domainOptions" :key="'f' + opt.id" :label="opt.label" :value="opt.id" />
              </el-select>
              <el-button type="primary" :loading="fullLoading" :disabled="!fullItems.length" @click="runFull">
                {{ fullLoading ? "检测中…" : "开始检测" }}
              </el-button>
            </div>
          </header>
          <div v-if="fullLoading" class="logic-progress">
            <el-progress :percentage="fullProg?.percent || 0" :stroke-width="8" />
            <p class="logic-progress-label">
              <span class="logic-progress-dot"></span>{{ fullProg?.label || "检测中…" }}
            </p>
          </div>
          <MaterialDrop
            :key="'logic-full'"
            title="放入完整评估报告"
            :items="fullItems"
            :allow-folder="false"
            :single="true"
            accept=".docx,.doc"
            @update:items="fullItems = $event"
          />
          <div v-if="fullResult" class="chapter-recogn">
            <div class="cr-head">
              <span class="cr-title">已识别章节（第3-11章）</span>
              <span :class="fullResult.chapters_missing && fullResult.chapters_missing.length ? 'cr-count miss' : 'cr-count ok'">
                {{ fullResult.chapters_found ? fullResult.chapters_found.length : 0 }}/9
              </span>
            </div>
            <ul class="cr-list">
              <li
                v-for="row in fullChapterRows"
                :key="'fcr' + row.no"
                :class="row.found ? 'cr-item ok' : 'cr-item miss'"
              >
                <span class="cr-flag">{{ row.found ? "✓" : "✗" }}</span>
                <span class="cr-name">第{{ row.no }}章{{ row.found ? " " + row.found.title : " 未识别" }}</span>
                <span v-if="row.found && row.found.source === 'llm'" class="cr-badge llm">LLM</span>
                <span v-else-if="row.found && row.found.confidence === 'low'" class="cr-badge low">低置信</span>
              </li>
            </ul>
          </div>
        </div>
        <div class="logic-panel logic-result-panel">
          <h3>评估结果</h3>
          <template v-if="fullResult">
            <div class="logic-stats">
              <span>{{ fullResult.domain_label || "报告" }}</span>
              <span>来源 {{ fullResult.source }}</span>
              <span>共 {{ fullResult.finding_count }} 处</span>
              <span>错别字 {{ fullResult.summary?.typo || 0 }}</span>
              <span>标点 {{ fullResult.summary?.punct || 0 }}</span>
              <span>语言 {{ fullResult.summary?.language || 0 }}</span>
              <span>计算 {{ fullResult.summary?.number || 0 }}</span>
              <span>年份 {{ fullResult.summary?.year || 0 }}</span>
              <span>逻辑 {{ fullResult.summary?.severe || 0 }}</span>
              <span v-if="fullResult.llm_used" class="llm-badge">LLM 复核 {{ fullResult.llm_finding_count || 0 }} 处</span>
            </div>
            <p class="logic-msg">{{ fullResult.message }}</p>
            <div class="logic-export-bar">
              <el-button size="small" :loading="fullExporting" @click="exportFull">导出 Word</el-button>
            </div>
            <div class="logic-columns">
              <div class="logic-col logic-col-minor">
                <div class="logic-col-head">
                  <span class="logic-col-title">轻微问题</span>
                  <span class="logic-col-count">{{ fullGroups.minor.length }} 处</span>
                </div>
                <p class="logic-col-sub">错别字 · 标点 · 语言不通顺</p>
                <ul v-if="fullGroups.minor.length" class="logic-list">
                  <li v-for="(item, idx) in fullGroups.minor" :key="'fm' + idx" :data-kind="item.kind">
                    <span class="tag" :data-kind="item.kind">{{ kindLabel(item.kind) }}</span>
                    <span v-if="item.via === 'llm'" class="llm-tag">LLM</span>
                    <span v-if="item.section" class="sec">定位：{{ item.section }}</span>
                    <span v-if="item.issue" class="iss">{{ item.issue }}</span>
                    <span class="note">{{ item.note }}</span>
                    <span v-if="item.excerpt" class="excerpt">原文：{{ item.excerpt }}</span>
                  </li>
                </ul>
                <p v-else class="logic-empty-hint">未发现轻微问题。</p>
              </div>
              <div class="logic-col">
                <div class="logic-col-head">
                  <span class="logic-col-title">逻辑问题</span>
                  <span class="logic-col-count">{{ fullGroups.major.length }} 处</span>
                </div>
                <p class="logic-col-sub">计算错误 · 年份错误 · 上下文逻辑矛盾</p>
                <ul v-if="fullGroups.major.length" class="logic-list">
                  <li v-for="(item, idx) in fullGroups.major" :key="'fj' + idx" :data-kind="item.kind">
                    <span class="tag" :data-kind="item.kind">{{ kindLabel(item.kind) }}</span>
                    <span v-if="item.via === 'llm'" class="llm-tag">LLM</span>
                    <span v-if="item.section" class="sec">定位：{{ item.section }}</span>
                    <span v-if="item.issue" class="iss">{{ item.issue }}</span>
                    <span class="note">{{ item.note }}</span>
                    <span v-if="item.excerpt" class="excerpt">原文：{{ item.excerpt }}</span>
                  </li>
                </ul>
                <p v-else class="logic-empty-hint">未发现逻辑问题。</p>
              </div>
            </div>
          </template>
          <p v-else class="logic-empty-hint">检测后在此列出第几章、何处、什么错误。左侧为错别字、标点、语言问题，右侧为计算、年份、上下文逻辑矛盾等问题。</p>
        </div>
      </section>

      <section class="logic-row">
        <div class="logic-panel logic-upload">
          <header class="logic-card-head">
            <div>
              <h2>章节逻辑性检测</h2>
            </div>
            <div class="logic-actions">
              <el-select v-model="domainChapter" style="width: 128px">
                <el-option v-for="opt in domainOptions" :key="'c' + opt.id" :label="opt.label" :value="opt.id" />
              </el-select>
              <el-select v-model="chapterId" placeholder="选择章节" style="width: 220px">
                <el-option v-for="opt in chapterOptions" :key="opt.id" :label="opt.label" :value="opt.id" />
              </el-select>
              <el-button type="primary" :loading="chapterLoading" :disabled="!chapterItems.length" @click="runChapter">
                {{ chapterLoading ? "检测中…" : "开始检测" }}
              </el-button>
            </div>
          </header>
          <div v-if="chapterLoading" class="logic-progress">
            <el-progress :percentage="chapterProg?.percent || 0" :stroke-width="8" />
            <p class="logic-progress-label">
              <span class="logic-progress-dot"></span>{{ chapterProg?.label || "检测中…" }}
            </p>
          </div>
          <MaterialDrop
            :key="'logic-ch'"
            title="放入单章或完整报告"
            :items="chapterItems"
            :allow-folder="false"
            :single="true"
            accept=".docx,.doc"
            @update:items="chapterItems = $event"
          />
          <div v-if="chapterResult" class="chapter-recogn">
            <div class="cr-head">
              <span class="cr-title">章节定位</span>
              <span :class="selectedChapterFound ? 'cr-count ok' : 'cr-count miss'">
                {{ selectedChapterFound ? "已定位" : "未定位" }}
              </span>
            </div>
            <p :class="selectedChapterFound ? 'cr-selected ok' : 'cr-selected miss'">
              本次检测：第{{ selectedChapterNo }}章{{ selectedChapterFound ? "已在文中定位" : "未在文中找到该章标题" }}
            </p>
            <ul class="cr-list cr-list-grid">
              <li
                v-for="row in chapterChapterRows"
                :key="'ccr' + row.no"
                :class="[row.found ? 'cr-item ok' : 'cr-item miss', row.no === selectedChapterNo ? 'cr-item-current' : '']"
              >
                <span class="cr-flag">{{ row.found ? "✓" : "✗" }}</span>
                <span class="cr-name">第{{ row.no }}章</span>
                <span v-if="row.found && row.found.source === 'llm'" class="cr-badge llm">LLM</span>
              </li>
            </ul>
          </div>
        </div>
        <div class="logic-panel logic-result-panel">
          <h3>评估结果</h3>
          <template v-if="chapterResult">
            <div class="logic-stats">
              <span>{{ chapterResult.domain_label || "报告" }}</span>
              <span>来源 {{ chapterResult.source }}</span>
              <span>共 {{ chapterResult.finding_count }} 处</span>
              <span>错别字 {{ chapterResult.summary?.typo || 0 }}</span>
              <span>标点 {{ chapterResult.summary?.punct || 0 }}</span>
              <span>语言 {{ chapterResult.summary?.language || 0 }}</span>
              <span>计算 {{ chapterResult.summary?.number || 0 }}</span>
              <span>年份 {{ chapterResult.summary?.year || 0 }}</span>
              <span>逻辑 {{ chapterResult.summary?.severe || 0 }}</span>
              <span v-if="chapterResult.llm_used" class="llm-badge">LLM 复核 {{ chapterResult.llm_finding_count || 0 }} 处</span>
            </div>
            <p class="logic-msg">{{ chapterResult.message }}</p>
            <div class="logic-export-bar">
              <el-button size="small" :loading="chapterExporting" @click="exportChapter">导出 Word</el-button>
            </div>
            <div class="logic-columns">
              <div class="logic-col logic-col-minor">
                <div class="logic-col-head">
                  <span class="logic-col-title">轻微问题</span>
                  <span class="logic-col-count">{{ chapterGroups.minor.length }} 处</span>
                </div>
                <p class="logic-col-sub">错别字 · 标点 · 语言不通顺</p>
                <ul v-if="chapterGroups.minor.length" class="logic-list">
                  <li v-for="(item, idx) in chapterGroups.minor" :key="'cm' + idx" :data-kind="item.kind">
                    <span class="tag" :data-kind="item.kind">{{ kindLabel(item.kind) }}</span>
                    <span v-if="item.via === 'llm'" class="llm-tag">LLM</span>
                    <span v-if="item.section" class="sec">定位：{{ item.section }}</span>
                    <span v-if="item.issue" class="iss">{{ item.issue }}</span>
                    <span class="note">{{ item.note }}</span>
                    <span v-if="item.excerpt" class="excerpt">原文：{{ item.excerpt }}</span>
                  </li>
                </ul>
                <p v-else class="logic-empty-hint">未发现轻微问题。</p>
              </div>
              <div class="logic-col">
                <div class="logic-col-head">
                  <span class="logic-col-title">逻辑问题</span>
                  <span class="logic-col-count">{{ chapterGroups.major.length }} 处</span>
                </div>
                <p class="logic-col-sub">计算错误 · 年份错误 · 上下文逻辑矛盾</p>
                <ul v-if="chapterGroups.major.length" class="logic-list">
                  <li v-for="(item, idx) in chapterGroups.major" :key="'cj' + idx" :data-kind="item.kind">
                    <span class="tag" :data-kind="item.kind">{{ kindLabel(item.kind) }}</span>
                    <span v-if="item.via === 'llm'" class="llm-tag">LLM</span>
                    <span v-if="item.section" class="sec">定位：{{ item.section }}</span>
                    <span v-if="item.issue" class="iss">{{ item.issue }}</span>
                    <span class="note">{{ item.note }}</span>
                    <span v-if="item.excerpt" class="excerpt">原文：{{ item.excerpt }}</span>
                  </li>
                </ul>
                <p v-else class="logic-empty-hint">未发现逻辑问题。</p>
              </div>
            </div>
          </template>
          <p v-else class="logic-empty-hint">检测后在此列出该章何处有错别字、标点、语言、计算或年份错误；左侧为错别字、标点、语言问题，右侧为计算、年份、上下文逻辑矛盾等问题。</p>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.logic-export-bar {
  display: flex;
  justify-content: flex-end;
  margin: 4px 0 8px;
}
.logic-progress {
  margin: 12px 2px 2px;
}
.logic-progress-label {
  margin: 6px 0 0;
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  line-height: 1.4;
  color: var(--color-text-3, #86909c);
}
.logic-progress-dot {
  flex: none;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--el-color-primary, #2563eb);
  animation: logic-progress-pulse 1s ease-in-out infinite;
}
@keyframes logic-progress-pulse {
  0%,
  100% {
    opacity: 0.3;
  }
  50% {
    opacity: 1;
  }
}
.chapter-recogn {
  margin-top: 12px;
  border: 1px solid var(--color-border, #d9d9d9);
  border-radius: 8px;
  padding: 10px 12px;
  background: var(--color-fill-2, #fafafa);
}
.cr-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.cr-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text, #1f2329);
}
.cr-count {
  font-size: 12px;
  font-weight: 600;
  padding: 1px 8px;
  border-radius: 10px;
}
.cr-count.ok {
  color: #16a34a;
  background: #dcfce7;
}
.cr-count.miss {
  color: #dc2626;
  background: #fee2e2;
}
.cr-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.cr-list-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 4px 8px;
}
.cr-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  line-height: 1.5;
}
.cr-item-current {
  font-weight: 700;
}
.cr-item.ok .cr-flag {
  color: #16a34a;
}
.cr-item.miss .cr-flag {
  color: #dc2626;
}
.cr-item.miss .cr-name {
  color: #dc2626;
}
.cr-name {
  color: var(--color-text-1, #4e5969);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cr-list-grid .cr-name {
  white-space: normal;
}
.cr-badge {
  flex: none;
  font-size: 10px;
  padding: 0 5px;
  border-radius: 8px;
  line-height: 16px;
}
.cr-badge.llm {
  color: #92400e;
  background: #fef3c7;
}
.cr-badge.low {
  color: #92400e;
  background: #fef9c3;
}
.cr-selected {
  margin: 0 0 8px;
  font-size: 12px;
}
.cr-selected.ok {
  color: #16a34a;
}
.cr-selected.miss {
  color: #dc2626;
}
</style>
