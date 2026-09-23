<template>
  <header class="app-header">
    <div class="header-row">
      <div>
        <h1>供电评估报告智能生成系统</h1>
        <p>{{ headerSubtitle }}</p>
      </div>
    </div>
    <nav class="domain-nav">
      <button
        v-for="item in domains"
        :key="item.id"
        type="button"
        class="domain-btn"
        :class="{ active: topTab === 'assess' && domainId === item.id }"
        @click="selectDomain(item.id)"
      >
        {{ item.name }}
      </button>
      <button
        type="button"
        class="domain-btn"
        :class="{ active: topTab === 'logic' }"
        @click="openLogicTab"
      >
        逻辑性检测
      </button>
      <button
        type="button"
        class="domain-btn"
        :class="{ active: topTab === 'device_eval' && deviceEvalStandard === 'main_hv' }"
        @click="openDeviceEval('main_hv')"
      >
        主变电系统设备评估
      </button>
      <button
        type="button"
        class="domain-btn"
        :class="{ active: topTab === 'device_eval' && deviceEvalStandard === 'power' }"
        @click="openDeviceEval('power')"
      >
        供电（含能源系统）设备评估
      </button>
    </nav>
  </header>

  <!-- KeepAlive：切换顶部页签时缓存这两个子组件，保留已上传文件与检测结果，切走再切回不丢失。 -->
  <KeepAlive>
    <LogicCheck
      v-if="topTab === 'logic'"
      :chapters="chapters"
      :assessment-year="assessmentYear"
    />
    <DeviceEval
      v-else-if="topTab === 'device_eval' && deviceEvalStandard === 'main_hv'"
      key="device-eval-main-hv"
      standard-id="main_hv"
    />
    <DeviceEval
      v-else-if="topTab === 'device_eval' && deviceEvalStandard === 'power'"
      key="device-eval-power"
      standard-id="power"
    />
  </KeepAlive>

  <div v-if="topTab !== 'logic' && topTab !== 'device_eval'" class="work-shell">
    <aside class="chapter-rail">
      <div class="prior-box">
        <p class="chapter-rail-title">去年报告</p>
        <button type="button" class="prior-btn" @click="pickPriorReport">{{ priorReportLabel }}</button>
        <p class="muted prior-note">
          有去年完整评估报告请放入（优先 .docx）：分拣与成文都按其目录/体例学。
          未放入或 .doc 无法转换时，自动用项目内 2025 {{ domainId === "overhead" ? "接触网" : "供电" }}年报作保底格式。
        </p>
        <p v-if="priorItems.length" class="prior-status">
          <span :title="priorFileName">已放入 {{ priorFileName }}</span>
          <button type="button" class="hint-clear" @click="clearPrior">清除</button>
        </p>
        <input
          ref="priorInput"
          type="file"
          accept=".docx,.doc,.xlsx,.xls,.pdf"
          hidden
          @change="onPriorFiles"
        />
      </div>
      <div class="parse-box">
        <p class="chapter-rail-title">材料分拣</p>
        <MaterialDrop
          :key="'parse-' + domainId"
          compact
          title="放入全年材料包"
          :items="parseItems"
          @update:items="onParseItems"
        />
        <div class="parse-actions">
          <el-button type="primary" size="small" :loading="domainParsing" :disabled="!parseItems.length" @click="runParse">
            {{ domainParsing ? `解析中 ${Math.round(domainParsePercent)}%` : "解析" }}
          </el-button>
          <el-button
            type="default"
            size="small"
            :loading="domainParsing"
            :disabled="!parseCacheAvailable"
            :title="parseCacheHint"
            @click="runParseReuse"
          >
            使用上次解析
          </el-button>
        </div>
        <div v-if="domainParsing || domainParsePercent > 0" class="parse-progress">
          <el-progress
            :percentage="Math.min(100, Math.round(domainParsePercent))"
            :stroke-width="8"
            :status="domainParsePercent >= 100 ? 'success' : undefined"
          />
        </div>
        <p v-if="parseSummary" class="parse-summary">{{ parseSummary }}</p>
      </div>
      <p class="chapter-rail-title">评估章节</p>      <div class="chapter-scroll">
        <button
          v-for="item in chapters"
          :key="item.id"
          type="button"
          class="chapter-btn"
          :class="{ active: chapterId === item.id }"
          @click="selectChapter(item.id)"
        >
          <span class="chapter-no">第{{ item.no }}章</span>
          <span class="chapter-name">{{ item.name }}</span>
        </button>
      </div>
    </aside>

    <div class="work-main">
  <p class="sub-hint">
    左侧按钮是第 3～11 章。点「{{ currentDomain?.name || "供电" }}」或「接触网」后各自一套章节，材料、进度、结果互不串用。
    当前：{{ currentDomain?.name || "—" }} · 第{{ currentChapter?.no || "—" }}章 {{ currentChapter?.name || "" }}。
    {{ domainReadyHint }}
  </p>

  <div class="layout">
    <div class="stack">
      <section class="panel">
        <h2>上传材料</h2>
        <p class="muted">
          支持 Word（.doc / .docx 均可，.doc 会自动转成 .docx）/ Excel / PDF / TXT / JSON。
          可一次丢进整个文件夹，里面的子文件夹也会收。
          本框属于当前专业的当前章节，切换供电 / 接触网或切换章节后互不串用。Excel 会读取全部工作表。
        </p>
        <p class="muted hint-line">
          <span class="hint-label">本章建议：</span>
          <template v-if="parseResult && chapterSuggestions.length">
            <button type="button" class="hint-action" :disabled="!pendingSuggestions.length" @click="addAllSuggested">
              一键加入
            </button>
            <span class="hint-count">共 {{ chapterSuggestions.length }} 个</span>
          </template>
          <span v-else-if="parseResult" class="hint-empty">暂无</span>
        </p>
        <div v-if="parseResult && chapterSuggestions.length" class="hint-files-scroll">
          <button
            v-for="item in chapterSuggestions"
            :key="item.relpath"
            type="button"
            class="hint-file"
            :class="{ added: alreadySuggested(item) }"
            :title="item.reason || item.relpath"
            @click="addSuggested(item)"
          >
            {{ item.name }}
          </button>
        </div>
        <MaterialDrop
          :key="'sys-' + workspaceKey"
          show-clear
          :title="mainDropTitle"
          :items="uploadItems"
          @update:items="onMainItems"
        />
      </section>

      <section class="panel">
        <h2>评估范围</h2>
        <el-form label-width="72px">
          <el-form-item label="年份">
            <el-select v-model="assessmentYear" style="width: 100%">
              <el-option
                v-for="year in yearOptions"
                :key="year"
                :label="yearLabel(year)"
                :value="year"
              />
            </el-select>
            <p class="muted" style="margin: 6px 0 0">评估年份写入报告封面。</p>
          </el-form-item>
        </el-form>
        <el-button type="primary" :loading="starting" :disabled="!canStart" @click="startJob">
          开始评估
        </el-button>
      </section>
    </div>

    <div class="stack">
      <section class="panel">
        <h2>进度</h2>
        <el-progress
          :percentage="Math.min(100, Math.round(displayPercent))"
          :status="progressStatus"
          :stroke-width="14"
          style="margin-bottom: 12px"
        />
        <div class="time-row">
          <span>开始评估：{{ job?.started_at || "—" }}</span>
          <span>评估结束：{{ endTimeText }}</span>
          <span v-if="job?.assessment_year">评估年：{{ job.assessment_year }}年</span>
        </div>
        <el-steps :active="stepIndex" finish-status="success" align-center>
          <el-step title="解析" />
          <el-step title="抽取" />
          <el-step title="成文" />
        </el-steps>
        <p class="muted" style="margin-top: 12px">
          {{ job ? `${job.message || job.status}（${job.job_id || ""}）` : "尚未开始" }}
        </p>
        <el-alert v-if="job?.error" :title="job.error" type="error" show-icon :closable="false" />
      </section>

      <section class="panel">
        <h2>评估结果{{ sectionReviews.length ? `（${sectionReviews.length}）` : "" }}</h2>
        <div v-if="sectionReviews.length" class="review-split">
          <div class="review-col">
            <h3 class="review-col-title">标点 / 缺材料（{{ leftReviews.length }}）</h3>
            <div class="review-scroll">
              <ul v-if="leftReviews.length" class="review-list">
                <li
                  v-for="item in leftReviews"
                  :key="'L' + item.section + item.kind + item.issue + (item.note || '')"
                  :class="'review-' + item.kind"
                >
                  <span class="review-section">{{ item.section }}</span>
                  <span class="review-issue">{{ item.issue }}</span>
                  <span v-if="item.note" class="review-note">{{ item.note }}</span>
                </li>
              </ul>
              <p v-else class="muted review-empty">暂无标点错误或找不到材料。</p>
            </div>
          </div>
          <div class="review-col">
            <h3 class="review-col-title">逻辑 / 年份（{{ rightReviews.length }}）</h3>
            <div class="review-scroll">
              <ul v-if="rightReviews.length" class="review-list">
                <li
                  v-for="item in rightReviews"
                  :key="'R' + item.section + item.kind + item.issue + (item.note || '')"
                  :class="'review-' + item.kind"
                >
                  <span class="review-section">{{ item.section }}</span>
                  <span class="review-issue">{{ item.issue }}</span>
                  <span v-if="item.note" class="review-note">{{ item.note }}</span>
                </li>
              </ul>
              <p v-else class="muted review-empty">暂无逻辑或年份错误。</p>
            </div>
          </div>
        </div>
        <p v-else-if="job?.status === 'completed'" class="muted">各小节未见缺材料、逻辑不通、年份错误、语言不通顺或标点错误。</p>
        <p v-else class="muted">评估完成后，左侧列标点错误与缺材料，右侧列逻辑不通与年份错误。</p>
      </section>

      <section class="panel">
        <h2>报告</h2>
        <el-button type="success" :disabled="!job?.report_ready" @click="downloadReport">
          下载本次报告
        </el-button>

        <div v-if="historyList.length" class="history-block">
          <h3 class="subhead">同一台账的历史报告</h3>
          <div class="history-toolbar">
            <el-button size="small" @click="toggleSelectAll">
              {{ allHistorySelected ? "取消全选" : "全选" }}
            </el-button>
            <el-button size="small" type="danger" plain :disabled="!selectedHistoryIds.length" :loading="deleting" @click="deleteSelectedHistory">
              删除所选
            </el-button>
            <el-button size="small" type="danger" :loading="deleting" @click="deleteAllHistory">
              全部删除
            </el-button>
          </div>
          <el-table
            ref="historyTable"
            class="history-table"
            :data="historyList"
            size="small"
            border
            row-key="job_id"
            height="280"
            max-height="280"
            @selection-change="onHistorySelect"
          >
            <el-table-column type="selection" width="42" />
            <el-table-column label="评估范围" min-width="220">
              <template #default="{ row }">
                <div class="scope-wrap">
                  <el-tag v-for="label in (row.scope_labels || []).slice(0, 6)" :key="label" size="small" effect="plain">
                    {{ label }}
                  </el-tag>
                  <span v-if="(row.scope_count || 0) > 6" class="muted">等 {{ row.scope_count }} 个区段</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="生成时间" width="170" />
            <el-table-column label="操作" width="210" fixed="right">
              <template #default="{ row }">
                <el-button text type="primary" size="small" @click="viewHistory(row)">查看</el-button>
                <el-button text type="primary" size="small" :disabled="!row.report_ready" @click="downloadHistory(row)">下载</el-button>
                <el-button text type="danger" size="small" @click="deleteOneHistory(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </section>

      <el-dialog v-model="viewVisible" :title="viewing?.title || '历史报告'" width="760px" class="history-dialog" destroy-on-close>
        <p class="muted" v-if="viewing">
          生成时间：{{ viewing.created_at || "—" }}
          <span v-if="viewing.scope_count">　共 {{ viewing.scope_count }} 个区段</span>
        </p>
        <div class="scope-wrap" style="margin-bottom: 12px">
          <el-tag v-for="label in viewing?.scope_labels || []" :key="label" size="small" effect="plain">
            {{ label }}
          </el-tag>
        </div>
        <div v-if="viewingJob?.line_results?.length" class="scroll-pane" style="max-height: 360px">
          <el-table :data="viewingJob.line_results" size="small" border>
            <el-table-column prop="line_id" label="线路" width="90" />
            <el-table-column prop="segment" label="区段" width="120" />
            <el-table-column label="S1" width="80">
              <template #default="{ row }">{{ row.subsystem?.total_score }}</template>
            </el-table-column>
            <el-table-column label="等级" width="80">
              <template #default="{ row }">{{ row.subsystem?.grade }}</template>
            </el-table-column>
          </el-table>
        </div>
        <p v-else class="muted">这份报告的网页预览已不可用，仍可下载 Word。</p>
        <template #footer>
          <el-button @click="viewVisible = false">关闭</el-button>
          <el-button type="primary" :disabled="!viewing?.report_ready" @click="downloadHistory(viewing)">
            下载到本地
          </el-button>
        </template>
      </el-dialog>
    </div>
  </div>
    </div>
  </div>
</template>

<script setup>
/**
 * 工作台：左侧「材料分拣」与右侧「上传材料 / 开始评估」是两套列表。
 * 供电 / 接触网、各章的评估材料、进度、结果按 workspaceKey（专业+章）隔离，互不串用。
 */
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import MaterialDrop from "./MaterialDrop.vue";
import LogicCheck from "./LogicCheck.vue";
import DeviceEval from "./DeviceEval.vue";
import {
  classifyMaterials,
  createJob,
  deleteReports,
  getCatalog,
  getJob,
  fetchParseCacheFile,
  getParseCacheInfo,
  previewFiles,
  reportUrl,
  reuseClassifyCache,
} from "./api";

/** 目录接口失败时的第 3～11 章兜底，不代替后端规则是否就绪。 */
const FALLBACK_CHAPTERS = [
  { id: "ch3", no: 3, name: "设备功能有效性评估", short: "功能有效性", upload_hint: "设备评估结果总表、管控措施（设备树）", report_hint: "", rules_ready: false, ready_in: ["power_supply", "overhead"], upload_hint_by_domain: { power_supply: "设备评估结果总表、管控措施（设备树）", overhead: "接触网状态表、管控措施（接触网设备树）" } },
  { id: "ch4", no: 4, name: "运营契合满意度评估", short: "运营契合", upload_hint: "设备评估结果总表，及其他相关评估材料。", report_hint: "", rules_ready: false, ready_in: ["power_supply", "overhead"], upload_hint_by_domain: { power_supply: "设备评估结果总表，及其他相关评估材料。", overhead: "设备体量、维护周期、各线接触网故障趋势" } },
  { id: "ch5", no: 5, name: "管理体系合规性评估", short: "管理体系", upload_hint: "合规性材料（法律法规、企标、执行与评价）", report_hint: "", rules_ready: false, ready_in: ["power_supply", "overhead"], upload_hint_by_domain: { power_supply: "合规性材料（法律法规、企标、执行与评价）", overhead: "合规性材料（特种设备、法律法规、企标、执行与评价）" } },
  { id: "ch6", no: 6, name: "修程修制匹配性评估", short: "修程修制", upload_hint: "合规性材料中的修程修制、规程修订目录", report_hint: "", rules_ready: false, ready_in: ["power_supply", "overhead"], upload_hint_by_domain: { power_supply: "合规性材料中的修程修制、规程修订目录", overhead: "修程修制、上一年度建议整改材料" } },
  { id: "ch7", no: 7, name: "运维表现健康度评估", short: "运维表现", upload_hint: "生产计划执行表等运维质量材料", report_hint: "", rules_ready: false, ready_in: ["power_supply", "overhead"], upload_hint_by_domain: { power_supply: "生产计划执行表等运维质量材料", overhead: "生产组织模式、维修计划执行、维保/接管/新技术" } },
  { id: "ch8", no: 8, name: "风险隐患闭环度评估", short: "风险隐患", upload_hint: "安全隐患排查动态治理、隐患排查手册", report_hint: "", rules_ready: false, ready_in: ["power_supply", "overhead"], upload_hint_by_domain: { power_supply: "安全隐患排查动态治理、隐患排查手册", overhead: "突出事件分析、故障专稿、隐患材料" } },
  { id: "ch9", no: 9, name: "备件物资保障度评估", short: "备件物资", upload_hint: "安全库存清单（备件）", report_hint: "", rules_ready: false, ready_in: ["power_supply", "overhead"], upload_hint_by_domain: { power_supply: "安全库存清单（备件）", overhead: "接触网安全库存、备品备件清单" } },
  { id: "ch10", no: 10, name: "使用环境符合性评估", short: "使用环境", upload_hint: "使用环境说明", report_hint: "", rules_ready: false, ready_in: ["power_supply", "overhead"], upload_hint_by_domain: { power_supply: "使用环境说明", overhead: "使用环境、弓架次等环境因子材料" } },
  { id: "ch11", no: 11, name: "退运报废倾向性评估", short: "退运报废", upload_hint: "退运材料、报废情况说明", report_hint: "", rules_ready: false, ready_in: ["power_supply", "overhead"], upload_hint_by_domain: { power_supply: "退运材料、报废情况说明", overhead: "退运更换说明、工器具配置" } },
];

const currentYear = new Date().getFullYear();
const assessmentYear = ref(currentYear);
const yearOptions = Array.from({ length: currentYear - 2017 }, (_, i) => currentYear - i);
const displayPercent = ref(0);
let crawlTimer = null;
const domainId = ref("power_supply");
const topTab = ref("assess"); // assess=供电/接触网工作台；logic=逻辑性检测；device_eval=团标单台设备
const deviceEvalStandard = ref("main_hv");
const chapterId = ref("ch3");
const subsystemId = ref("stray_current");
const domains = ref([]);
const chapters = ref(FALLBACK_CHAPTERS);
const lastChapter = {}; // 切换专业时记住该专业上次停留的章
const fileList = ref([]); // 当前章评估上传（createJob 用）
const uploadItems = ref([]);
const parseItems = ref([]); // 左侧分拣袋，与评估上传分开
const parseResult = ref(null);
const parseCacheInfo = ref({ available: false });
const priorItems = ref([]); // 去年完整报告，按专业存，不进本章评估
const priorInput = ref(null);
const parseBags = reactive({
  // 分拣按专业隔离：供电袋与接触网袋不串
  power_supply: { items: [], result: null, parsing: false, percent: 0, priorItems: [] },
  overhead: { items: [], result: null, parsing: false, percent: 0, priorItems: [] },
});
const parseTimers = {};
const sharedFileList = ref([]);
const sharedUploadItems = ref([]);
const preview = ref(null);
const previewing = ref(false);
const selectedLines = ref([]);
const selectedSegmentKeys = ref([]);
const starting = ref(false);
const deleting = ref(false);
const job = ref(null);
const historyTable = ref(null);
const selectedHistoryIds = ref([]);
const viewVisible = ref(false);
const viewing = ref(null);
const viewingJob = ref(null);
let timer = null;
let previewToken = 0;

const stepMap = {
  upload: 0,
  parse: 0,
  extract: 1,
  write: 2,
  compose: 2,
  completed: 3,
};

const lineOptions = computed(() => (preview.value?.lines || []).map((item) => item.line_id));

const segmentOptions = computed(() => {
  const picked = selectedLines.value;
  const options = [];
  for (const item of preview.value?.lines || []) {
    if (picked.length && !picked.includes(item.line_id)) continue;
    for (const seg of item.segments || []) {
      options.push({
        value: `${item.line_id}|${seg}`,
        label: `${item.line_id} ${seg}`,
      });
    }
  }
  return options;
});

const canStart = computed(() => jobFiles().length > 0);

const historyList = computed(() => {
  const rows = job.value?.previous_reports || preview.value?.previous_reports || [];
  return rows.filter((row) => row.job_id && row.job_id !== job.value?.job_id);
});

const fileFingerprint = computed(
  () => job.value?.file_fingerprint || preview.value?.fingerprint || "",
);

const allHistorySelected = computed(
  () => historyList.value.length > 0 && selectedHistoryIds.value.length === historyList.value.length,
);

const currentDomain = computed(() => domains.value.find((item) => item.id === domainId.value) || null);
const currentChapter = computed(
  () => chapters.value.find((item) => item.id === chapterId.value) || chapters.value[0] || null,
);
const currentSubsystems = computed(() => currentDomain.value?.subsystems || []);
const currentSubsystem = computed(
  () => currentSubsystems.value.find((item) => item.id === subsystemId.value) || currentSubsystems.value[0] || null,
);
/** 评估工作区键：专业 + 章，切换供电/接触网或换章时各自一套材料与进度。 */
const workspaceKey = computed(() => `${domainId.value}::${chapterId.value}`);
const domainParsing = computed(() => !!parseBag(domainId.value).parsing);
const domainParsePercent = computed(() => Number(parseBag(domainId.value).percent) || 0);
const headerSubtitle = computed(() => {
  if (topTab.value === "logic") {
    return "逻辑性检测 · 完整报告 / 单章上下文相悖与数字口径";
  }
  if (topTab.value === "device_eval") {
    return deviceEvalStandard.value === "main_hv"
      ? "主变电系统 · 单台设备功能有效性（附录A）→ ABCD"
      : "供电（含能源系统）· 单台设备功能有效性（附录A）→ ABCD";
  }
  const domain = currentDomain.value;
  const chapter = currentChapter.value;
  if (!domain || !chapter) return "供电 / 接触网";
  const std = domain.standard ? ` · ${domain.standard}` : "";
  return `${domain.full_name || domain.name} · 第${chapter.no}章 ${chapter.name}${std}`;
});
/** 该专业是否已接入本章抽取规则；未接入时仍可上传，只收存、不套别章评分。 */
const thisChapterReady = computed(() => {
  const ch = currentChapter.value;
  if (!ch) return false;
  const readyIn = ch.ready_in || [];
  if (readyIn.length) return readyIn.includes(domainId.value);
  return !!ch.rules_ready;
});
const parseCacheAvailable = computed(() => !!parseCacheInfo.value?.available);
const parseCacheHint = computed(() => {
  const info = parseCacheInfo.value;
  if (!info?.available) {
    if (info?.file_count && info.stored_count != null && info.stored_count < info.file_count) {
      return "缓存不完整（材料未落盘），请重新完整解析一次";
    }
    return "请先完整解析一次，结果会保存在服务器 parse_cache 目录";
  }
  const names = (info.file_names || []).slice(0, 3).join("、");
  const more = (info.file_count || 0) > 3 ? ` 等 ${info.file_count} 个` : "";
  return `上次：${info.saved_at || "—"}${names ? ` · ${names}${more}` : ""}`;
});

const parseSummary = computed(() => {
  const data = parseResult.value;
  if (!data) return "";
  if (!data.total) return "没有解析到文档";
  const kept = data.kept_count ?? data.power_picked ?? data.assigned ?? 0;
  const dropped = data.dropped_count ?? data.overhead_dropped ?? 0;
  const assigned = data.assigned || 0;
  let base;
  if (domainId.value === "overhead") {
    base = `已解析 ${data.total} 个：接触网 ${kept} 个（${assigned} 个已分章），供电不看 ${dropped} 个。`;
  } else {
    base = `已解析 ${data.total} 个：供电 ${kept} 个（${assigned} 个已分章），触网不看 ${dropped} 个。`;
  }
  if (data.reused_parse_cache) {
    const when = data.parse_cache_saved_at || "";
    const hits = data.parse_cache_hits != null ? ` · 单文件缓存命中 ${data.parse_cache_hits}/${data.parse_cache_total || "?"}` : "";
    return `${base}（沿用上次解析${when ? " · " + when : ""}${hits}）`;
  }
  if (data.parse_cache_hits != null && data.parse_cache_total) {
    return `${base} · 单文件缓存 ${data.parse_cache_hits}/${data.parse_cache_total}`;
  }
  return base;
});
const sectionReviews = computed(() => job.value?.section_reviews || []);
/** 左栏：标点错误、缺材料（含措施未填）、语言不通顺；右栏：逻辑不通、年份错误。 */
const leftReviews = computed(() =>
  sectionReviews.value.filter((x) => ["punct", "missing", "language"].includes(x.kind))
);
const rightReviews = computed(() =>
  sectionReviews.value.filter((x) => ["logic", "year"].includes(x.kind))
);
/** 本章建议：只取分拣结果 by_chapter 里当前章的文件，点文件名才加入评估上传。 */
const chapterSuggestions = computed(() => {
  const rows = parseResult.value?.by_chapter?.[chapterId.value] || [];
  const seen = new Set();
  const out = [];
  for (const row of rows) {
    const key = row.relpath || row.name;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(row);
  }
  return out;
});
const pendingSuggestions = computed(() => chapterSuggestions.value.filter((item) => !alreadySuggested(item)));
const priorReportLabel = computed(() =>
  domainId.value === "overhead" ? "放入去年接触网报告" : "放入去年供电报告",
);
const priorFileName = computed(() => priorItems.value[0]?.name || "");
const domainReadyHint = computed(() => {
  if (thisChapterReady.value) {
    const name = currentDomain.value?.name || "本专业";
    return `${name}第3～11章已按「从材料抽取填入」接入：缺材料只留黄标题，不编造。`;
  }
  return "本章评估规则尚未制定，上传后只收存材料，不套用其他专业或其他章节的规则。";
});
const chapterUploadHint = computed(() => {
  const ch = currentChapter.value;
  if (!ch) return "设备评估结果总表，及其他相关评估材料。";
  const by = ch.upload_hint_by_domain || {};
  return by[domainId.value] || ch.upload_hint || "设备评估结果总表，及其他相关评估材料。";
});
const mainDropTitle = computed(() => {
  const name = currentChapter.value?.name || "本章";
  return `将「${name}」评估材料拖到此处，或选择文件 / 文件夹`;
});
const resultTypeColumns = computed(() => {
  const fromJob = job.value?.type_columns || [];
  if (fromJob.length) return fromJob;
  return currentChapter.value ? [currentChapter.value.short || currentChapter.value.name] : [];
});

const progressMap = {
  upload: 8,
  parse: 16,
  extract: 32,
  validate: 48,
  human: 58,
  confirm: 58,
  score: 72,
  retrieve: 80,
  write: 90,
  compose: 96,
  completed: 100,
};

const stepIndex = computed(() => {
  if (!job.value) return 0;
  if (job.value.status === "completed") return 3;
  return stepMap[job.value.step] ?? 0;
});

const nextProgressMap = {
  upload: 16,
  parse: 31,
  extract: 47,
  validate: 57,
  human: 71,
  confirm: 71,
  score: 79,
  retrieve: 89,
  write: 95,
  compose: 99,
};

const progressStatus = computed(() => {
  if (job.value?.status === "completed") return "success";
  if (job.value?.status === "failed") return "exception";
  return undefined;
});

const endTimeText = computed(() => {
  if (!job.value) return "—";
  if (job.value.finished_at) return job.value.finished_at;
  if (["running", "queued"].includes(job.value.status)) return "进行中";
  return "—";
});

/** 评估进行中把进度条缓爬到下一档上限，避免长时间停在阶跃值。 */
function crawlProgress() {
  const current = job.value;
  if (!current) {
    displayPercent.value = 0;
    return;
  }
  if (current.status === "completed") {
    displayPercent.value = 100;
    return;
  }
  if (current.status === "failed") {
    displayPercent.value = progressMap[current.step] ?? 20;
    return;
  }
  const floor = progressMap[current.step] ?? 8;
  const cap = nextProgressMap[current.step] ?? Math.min(99, floor + 10);
  if (displayPercent.value < floor) {
    displayPercent.value = floor;
    return;
  }
  if (displayPercent.value < cap) {
    const remain = cap - displayPercent.value;
    displayPercent.value = Math.round((displayPercent.value + Math.max(0.2, remain * 0.045)) * 10) / 10;
  }
}

function yearLabel(year) {
  if (year === currentYear) return `${year}年（今年）`;
  return `${year}年`;
}

function scoreSourceLabel(src) {
  if (src === "grade_table") return "总表";
  if (src === "ledger") return "材料";
  if (src === "engine") return "重算";
  return "抽取";
}

function typeScore(row, name) {
  const mapped = row?.type_scores?.[name];
  if (mapped !== undefined && mapped !== null && mapped !== "") return mapped;
  const found = (row?.subsystem?.contributions || []).find((item) => item.device_type === name);
  const value = found?.avg_device_score;
  if (value === undefined || value === null || value === "") return "/";
  return value;
}

function selectAllLines() {
  selectedLines.value = [...lineOptions.value];
}

function selectedSegmentPayload() {
  return selectedSegmentKeys.value.map((key) => {
    const [lineId, ...rest] = key.split("|");
    return { line_id: lineId, segment: rest.join("|") };
  });
}

function fileKey(file) {
  const path = file?.relativePath || file?.webkitRelativePath || file?.name || "";
  return `${path}:${file?.size || 0}:${file?.lastModified || 0}`;
}

/** 当前章评估上传去重后的 File 列表，交给 createJob，不含分拣袋。 */
function jobFiles() {
  const seen = new Set();
  const out = [];
  for (const file of fileList.value) {
    const key = fileKey(file);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(file);
  }
  return out;
}

async function refreshPreview() {
  const token = ++previewToken;
  const files = jobFiles();
  if (!files.length) {
    preview.value = null;
    selectedLines.value = [];
    selectedSegmentKeys.value = [];
    return;
  }
  previewing.value = true;
  try {
    const { data } = await previewFiles(files);
    if (token !== previewToken) return;
    preview.value = data;
    selectedLines.value = [];
    selectedSegmentKeys.value = [];
  } catch (err) {
    if (token !== previewToken) return;
    ElMessage.error(err.response?.data?.detail || err.message);
  } finally {
    if (token === previewToken) previewing.value = false;
  }
}

function onMainItems(list) {
  uploadItems.value = list;
  fileList.value = list.map((item) => item.raw).filter(Boolean);
}

/** 只改当前专业的分拣袋，不影响评估上传框。 */
function onParseItems(list) {
  const bag = parseBag(domainId.value);
  bag.items = list;
  parseItems.value = list;
}

function parseFileRel(file) {
  return String(file?.relativePath || file?.webkitRelativePath || file?.name || "").replace(/\\/g, "/");
}

/** 从分拣袋或 parse_cache 落盘副本找回 File，才能加入评估上传。 */
function rawForSuggestionFromBag(item) {
  const want = String(item.relpath || item.name || "").replace(/\\/g, "/");
  const base = want.split("/").pop();
  return (
    parseItems.value.find((row) => parseFileRel(row.raw) === want)?.raw ||
    parseItems.value.find((row) => (row.raw?.name || "") === base)?.raw ||
    null
  );
}

async function rawForSuggestion(item) {
  const local = rawForSuggestionFromBag(item);
  if (local) return local;
  if (!parseCacheInfo.value?.available) return null;
  const rel = String(item.relpath || item.name || "").replace(/\\/g, "/");
  try {
    const { data } = await fetchParseCacheFile(domainId.value, rel);
    const name = rel.split("/").pop() || item.name || "material.docx";
    const file = new File([data], name, { type: data.type || "application/octet-stream" });
    Object.defineProperty(file, "relativePath", { value: rel, configurable: true });
    return file;
  } catch {
    return null;
  }
}

function alreadySuggested(item) {
  const raw = rawForSuggestionFromBag(item);
  if (!raw) return false;
  const key = fileKey(raw);
  return fileList.value.some((file) => fileKey(file) === key);
}

/** 把「本章建议」里的文件拷进评估上传框，分拣袋本身不动。 */
async function addSuggested(item) {
  if (alreadySuggested(item)) {
    ElMessage.info("已在本章上传列表中");
    return;
  }
  const raw = await rawForSuggestion(item);
  if (!raw) {
    ElMessage.warning("找不到该文件，请重新解析");
    return;
  }
  const path = parseFileRel(raw) || item.relpath || raw.name;
  const next = [
    ...uploadItems.value,
    {
      uid: `${fileKey(raw)}:${Math.random().toString(36).slice(2, 8)}`,
      name: path,
      raw,
    },
  ];
  onMainItems(next);
  ElMessage.success(`已加入本章：${item.name}`);
}

async function addAllSuggested() {
  const pending = pendingSuggestions.value;
  if (!pending.length) {
    ElMessage.info(chapterSuggestions.value.length ? "建议文件已在本章上传列表中" : "暂无本章建议");
    return;
  }
  const next = [...uploadItems.value];
  let added = 0;
  let missing = 0;
  for (const item of pending) {
    const raw = await rawForSuggestion(item);
    if (!raw) {
      missing += 1;
      continue;
    }
    next.push({
      uid: `${fileKey(raw)}:${Math.random().toString(36).slice(2, 8)}`,
      name: parseFileRel(raw) || item.relpath || raw.name,
      raw,
    });
    added += 1;
  }
  if (added) onMainItems(next);
  if (added && missing) ElMessage.success(`已加入 ${added} 个，${missing} 个找不到请重新解析`);
  else if (added) ElMessage.success(`已加入本章建议 ${added} 个文件`);
  else ElMessage.warning("找不到建议文件，请重新解析");
}

function pickPriorReport() {
  priorInput.value?.click();
}

function onPriorFiles(event) {
  const file = event.target.files?.[0];
  event.target.value = "";
  if (!file) return;
  const item = {
    uid: `${fileKey(file)}:${Math.random().toString(36).slice(2, 8)}`,
    name: file.name,
    raw: file,
  };
  priorItems.value = [item];
  parseBag(domainId.value).priorItems = priorItems.value;
  ElMessage.success(`已放入去年报告：${file.name}`);
}

function clearPrior() {
  priorItems.value = [];
  parseBag(domainId.value).priorItems = [];
}

async function refreshParseCacheInfo(id = domainId.value) {
  try {
    const { data } = await getParseCacheInfo(id);
    if (domainId.value === id) parseCacheInfo.value = data || { available: false };
  } catch {
    if (domainId.value === id) parseCacheInfo.value = { available: false };
  }
}

/** 直接加载服务端上次分拣结果，不重新解析 Word（重启后仍可用）。 */
async function runParseReuse() {
  const domain = domainId.value;
  const bag = parseBag(domain);
  bag.parsing = true;
  bag.percent = 40;
  try {
    const { data } = await reuseClassifyCache(domain, assessmentYear.value);
    bag.result = data;
    bag.percent = 100;
    if (domainId.value === domain) parseResult.value = data;
    ElMessage.success(`已加载上次解析结果（${data.parse_cache_saved_at || "缓存"}）`);
  } catch (err) {
    bag.percent = 0;
    if (domainId.value === domain) {
      ElMessage.error(err.response?.data?.detail || err.message || "暂无可用缓存");
    }
  } finally {
    bag.parsing = false;
    refreshParseCacheInfo(domain);
  }
}

/** 分拣：调用 classifyMaterials，只刷新「本章建议」，不创建评估任务。 */
async function runParse() {
  const domain = domainId.value;
  const bag = parseBag(domain);
  const files = bag.items.map((item) => item.raw).filter(Boolean);
  if (!files.length) {
    ElMessage.warning("请先放入文件或文件夹");
    return;
  }
  if (!priorItems.value.length) {
    const label = domain === "overhead" ? "接触网" : "供电";
    ElMessage.info(`未放入去年报告，将使用项目内2025${label}年报作保底格式`);
  }
  bag.parsing = true;
  bag.percent = 2;
  startParseCrawl(domain);
  try {
    const { data } = await classifyMaterials(
      files,
      domain,
      true,
      (p) => {
        bag.percent = Math.max(bag.percent, p);
      },
      assessmentYear.value,
      priorItems.value[0]?.raw,
      true,
    );
    bag.result = data;
    bag.percent = 100;
    if (domainId.value === domain) parseResult.value = data;
    if (domainId.value !== domain) return;
    const kept = data.kept_count ?? data.power_picked ?? data.assigned ?? 0;
    const dropped = data.dropped_count ?? data.overhead_dropped ?? 0;
    if (kept || data.assigned) {
      if (domain === "overhead") {
        ElMessage.success(
          `已挑出接触网 ${kept} 个，其中 ${data.assigned || 0} 个已分章；供电 ${dropped} 个不看`,
        );
      } else {
        ElMessage.success(
          `已挑出供电 ${kept} 个，其中 ${data.assigned || 0} 个已分章；接触网 ${dropped} 个不看`,
        );
      }
    } else {
      const tip = domain === "overhead" ? "没有挑出可分章的接触网材料" : "没有挑出可分章的供电材料";
      ElMessage.warning(data.unused?.[0]?.skip_reason || tip);
    }
  } catch (err) {
    bag.percent = 0;
    if (domainId.value === domain) ElMessage.error(err.response?.data?.detail || err.message);
  } finally {
    stopParseCrawl(domain);
    bag.parsing = false;
    refreshParseCacheInfo(domain);
    if (bag.percent >= 100) {
      setTimeout(() => {
        if (!parseBag(domain).parsing) parseBag(domain).percent = 0;
      }, 1800);
    }
  }
}

function onSharedItems(list) {
  sharedUploadItems.value = list;
  sharedFileList.value = list.map((item) => item.raw).filter(Boolean);
  refreshPreview();
}

/** 评估：把当前章 uploadItems 交给 createJob，与左侧分拣材料无关。 */
async function startJob() {
  starting.value = true;
  try {
    const { data } = await createJob(
      jobFiles(),
      "material",
      [],
      [],
      assessmentYear.value,
      domainId.value,
      subsystemId.value,
      chapterId.value,
      priorItems.value[0]?.raw,
    );
    displayPercent.value = 8;
    job.value = data;
    if (data.status === "completed") {
      displayPercent.value = 100;
      if (!data.report_ready) {
        ElMessage.success(data.message || "材料已按本章收存");
      }
    } else {
      poll();
    }
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || err.message);
  } finally {
    starting.value = false;
  }
}

function poll() {
  stopPoll();
  timer = setInterval(async () => {
    if (!job.value?.job_id) return;
    const { data } = await getJob(job.value.job_id);
    job.value = data;
    if (["completed", "failed"].includes(data.status)) {
      stopPoll();
    }
  }, 1500);
}

function stopPoll() {
  if (timer) {
    clearInterval(timer);
    timer = null;
  }
}

function applyHistory(rows) {
  selectedHistoryIds.value = [];
  if (historyTable.value?.clearSelection) historyTable.value.clearSelection();
  if (job.value) job.value.previous_reports = rows;
  if (preview.value) preview.value.previous_reports = rows;
}

function onHistorySelect(rows) {
  selectedHistoryIds.value = rows.map((row) => row.job_id);
}

function toggleSelectAll() {
  if (!historyTable.value) return;
  if (allHistorySelected.value) historyTable.value.clearSelection();
  else historyTable.value.toggleAllSelection();
}

async function viewHistory(row) {
  viewing.value = row;
  viewingJob.value = null;
  viewVisible.value = true;
  try {
    const { data } = await getJob(row.job_id);
    viewingJob.value = data;
  } catch {
    viewingJob.value = null;
  }
}

function downloadHistory(row) {
  if (!row?.job_id) return;
  window.location.href = reportUrl(row.job_id);
}

async function deleteHistoryIds(jobIds, confirmText) {
  if (!fileFingerprint.value) {
    ElMessage.warning("请先上传台账");
    return;
  }
  try {
    await ElMessageBox.confirm(confirmText, "删除历史报告", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
  } catch {
    return;
  }
  deleting.value = true;
  try {
    const { data } = await deleteReports({
      fingerprint: fileFingerprint.value,
      job_ids: jobIds,
      keep_job_id: job.value?.job_id || "",
      subsystem_id: subsystemId.value,
      domain_id: domainId.value,
      chapter_id: chapterId.value,
    });
    applyHistory(data.reports || []);
    ElMessage.success(jobIds.length ? `已删除 ${data.removed?.length || 0} 份` : "已清空历史报告");
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || err.message);
  } finally {
    deleting.value = false;
  }
}

function deleteOneHistory(row) {
  return deleteHistoryIds([row.job_id], `删除「${row.title}」？删除后无法从网页恢复。`);
}

function deleteSelectedHistory() {
  if (!selectedHistoryIds.value.length) {
    ElMessage.warning("请先勾选要删除的报告");
    return;
  }
  return deleteHistoryIds(selectedHistoryIds.value, `删除已选的 ${selectedHistoryIds.value.length} 份报告？`);
}

function deleteAllHistory() {
  return deleteHistoryIds([], "删除该台账下的全部历史报告？本次正在查看的报告不会删。");
}

function downloadReport() {
  window.location.href = reportUrl(job.value.job_id);
}

const bags = {}; // 评估工作区快照，键为 workspaceKey
const sharedBags = {};

function snapshotWorkspace(key) {
  bags[key] = {
    files: fileList.value,
    uploadItems: uploadItems.value,
    preview: preview.value,
    selectedLines: [...selectedLines.value],
    selectedSegmentKeys: [...selectedSegmentKeys.value],
    job: job.value,
    displayPercent: displayPercent.value,
  };
}

function snapshotShared(key) {
  sharedBags[key] = {
    files: sharedFileList.value,
    uploadItems: sharedUploadItems.value,
  };
}

function applyShared(key) {
  const bag = sharedBags[key];
  sharedFileList.value = bag?.files || [];
  sharedUploadItems.value = bag?.uploadItems || [];
}

/** 恢复某专业+章的评估上传、预览与任务；空袋表示该章尚未上传。 */
function applyBag(bag) {
  stopPoll();
  if (!bag) {
    fileList.value = [];
    uploadItems.value = [];
    preview.value = null;
    selectedLines.value = [];
    selectedSegmentKeys.value = [];
    job.value = null;
    displayPercent.value = 0;
    return;
  }
  fileList.value = bag.files || [];
  uploadItems.value = bag.uploadItems || [];
  preview.value = bag.preview || null;
  selectedLines.value = bag.selectedLines || [];
  selectedSegmentKeys.value = bag.selectedSegmentKeys || [];
  job.value = bag.job || null;
  displayPercent.value = bag.displayPercent || 0;
  if (job.value?.job_id && ["running", "queued"].includes(job.value.status)) poll();
}

function domainSubsystem(id) {
  return id === "overhead" ? "oh_network" : "stray_current";
}

/** 分拣状态按专业取袋；接触网与供电各用各的。 */
function parseBag(id) {
  if (!parseBags[id]) parseBags[id] = { items: [], result: null, parsing: false, percent: 0, priorItems: [] };
  if (!parseBags[id].priorItems) parseBags[id].priorItems = [];
  return parseBags[id];
}

function stopParseCrawl(id) {
  if (parseTimers[id]) {
    clearInterval(parseTimers[id]);
    delete parseTimers[id];
  }
}

function startParseCrawl(id) {
  stopParseCrawl(id);
  parseTimers[id] = setInterval(() => {
    const bag = parseBag(id);
    if (!bag.parsing) {
      stopParseCrawl(id);
      return;
    }
    if (bag.percent < 94) {
      bag.percent = Math.round((bag.percent + Math.max(0.25, (94 - bag.percent) * 0.035)) * 10) / 10;
    }
  }, 280);
}

function snapshotParse(id) {
  const bag = parseBag(id);
  bag.items = parseItems.value;
  bag.result = parseResult.value;
  bag.priorItems = priorItems.value;
}

function applyParse(id) {
  const bag = parseBag(id);
  parseItems.value = bag.items;
  parseResult.value = bag.result;
  priorItems.value = bag.priorItems || [];
}

/** 换专业：先存当前评估工作区与分拣袋，再恢复目标专业（含该专业上次的章）。 */
function selectDomain(id) {
  topTab.value = "assess";
  if (domainId.value === id) return;
  const prev = workspaceKey.value;
  lastChapter[domainId.value] = chapterId.value;
  snapshotWorkspace(prev);
  snapshotShared(prev);
  snapshotParse(domainId.value);
  domainId.value = id;
  subsystemId.value = domainSubsystem(id);
  chapterId.value = lastChapter[id] || "ch3";
  const next = `${id}::${chapterId.value}`;
  applyShared(next);
  applyBag(bags[next]);
  applyParse(id);
  refreshParseCacheInfo(id);
}

function openLogicTab() {
  topTab.value = "logic";
}

function openDeviceEval(id) {
  deviceEvalStandard.value = id;
  topTab.value = "device_eval";
}

/** 换章：只切换评估上传/进度；分拣结果仍属当前专业，建议列表随章改读 by_chapter。 */
function selectChapter(id) {
  if (chapterId.value === id) return;
  const prev = workspaceKey.value;
  snapshotWorkspace(prev);
  snapshotShared(prev);
  chapterId.value = id;
  lastChapter[domainId.value] = id;
  const next = `${domainId.value}::${id}`;
  applyShared(next);
  applyBag(bags[next]);
}

function selectSubsystem(id) {
  if (subsystemId.value === id) return;
  subsystemId.value = id;
}

async function loadShell() {
  try {
    const { data: catalog } = await getCatalog();
    domains.value = catalog.domains || [];
    chapters.value = catalog.chapters?.length ? catalog.chapters : FALLBACK_CHAPTERS;
    if (catalog.default_domain) domainId.value = catalog.default_domain;
    if (catalog.default_chapter) chapterId.value = catalog.default_chapter;
    subsystemId.value = domainSubsystem(domainId.value);
  } catch {
    chapters.value = FALLBACK_CHAPTERS;
    if (!domains.value.length) {
      domains.value = [
        {
          id: "power_supply",
          name: "供电",
          full_name: "供电（含能源系统）",
          standard: "T/SHJX 089.7-2025",
          chapters: FALLBACK_CHAPTERS,
          subsystems: [],
        },
        {
          id: "overhead",
          name: "接触网",
          full_name: "接触网",
          standard: "接触网分册",
          chapters: FALLBACK_CHAPTERS,
          subsystems: [],
        },
      ];
    }
  }
}

onMounted(async () => {
  crawlTimer = setInterval(crawlProgress, 400);
  await loadShell();
  refreshParseCacheInfo(domainId.value);
});

onBeforeUnmount(() => {
  stopPoll();
  if (crawlTimer) {
    clearInterval(crawlTimer);
    crawlTimer = null;
  }
  Object.keys(parseTimers).forEach(stopParseCrawl);
});
</script>
