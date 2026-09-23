<script setup>
/** 团标附录 A：一台设备填参数 → 百分数 → ABCD。不走各章报告。 */
import { computed, onMounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { getDeviceEvalCatalog, runDeviceEval } from "./api";

const props = defineProps({
  standardId: { type: String, required: true },
});

const loading = ref(false);
const evaluating = ref(false);
const catalog = ref(null);
const subsystemId = ref("");
const deviceId = ref("");
const weights = ref({});
const values = ref({});
const result = ref(null);

const subsystems = computed(() => catalog.value?.subsystems || []);
const devices = computed(() => {
  const sub = subsystems.value.find((s) => s.id === subsystemId.value);
  return sub?.devices || [];
});
const device = computed(() => devices.value.find((d) => d.id === deviceId.value) || null);
const params = computed(() => device.value?.params || []);

const weightSum = computed(() => {
  let sum = 0;
  for (const p of params.value) {
    const n = Number(weights.value[p.id]);
    if (!Number.isNaN(n)) sum += n;
  }
  return Math.round(sum * 10) / 10;
});
const weightOk = computed(() => Math.abs(weightSum.value - 100) <= 0.15);

function emptyPayload(param) {
  const row = {};
  for (const field of param.fields || []) {
    if (field.type === "checkbox") row[field.key] = !!field.default;
    else if (field.default !== undefined && field.default !== null) row[field.key] = field.default;
    else row[field.key] = undefined;
  }
  return row;
}

function initForm() {
  const w = {};
  const v = {};
  for (const p of params.value) {
    w[p.id] = p.weight_default;
    v[p.id] = emptyPayload(p);
  }
  weights.value = w;
  values.value = v;
  result.value = null;
}

function weightHint(param) {
  const lo = param.weight_min;
  const hi = param.weight_max;
  if (lo == null && hi == null) return "";
  if (lo === hi) return `建议取值 ${lo}%`;
  return `建议取值范围 ${lo}% – ${hi}%`;
}

async function loadCatalog() {
  loading.value = true;
  result.value = null;
  catalog.value = null;
  try {
    const { data } = await getDeviceEvalCatalog(props.standardId);
    catalog.value = data;
    subsystemId.value = data.subsystems?.[0]?.id || "";
    deviceId.value = data.subsystems?.[0]?.devices?.[0]?.id || "";
    initForm();
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || "目录加载失败");
  } finally {
    loading.value = false;
  }
}

watch(() => props.standardId, loadCatalog);
watch(deviceId, () => {
  initForm();
});

onMounted(loadCatalog);

async function evaluate() {
  if (!device.value) {
    ElMessage.warning("请先选择设备");
    return;
  }
  if (!weightOk.value) {
    ElMessage.warning(`权重合计为 ${weightSum.value}%，须为 100%`);
    return;
  }
  evaluating.value = true;
  result.value = null;
  try {
    const { data } = await runDeviceEval({
      standard_id: props.standardId,
      device_id: device.value.id,
      weights: weights.value,
      values: values.value,
    });
    result.value = data;
    if (!data.ok) ElMessage.warning((data.errors || []).join("；") || "请补全参数");
    else if (data.warnings?.length) ElMessage.warning(data.warnings.join("；"));
    else ElMessage.success(`综合得分 ${data.score}，等级 ${data.grade}`);
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || "评估失败");
  } finally {
    evaluating.value = false;
  }
}
</script>

<template>
  <div class="deval-page">
    <div v-if="loading" class="deval-loading">正在载入团标设备表…</div>

    <div v-else class="deval-layout">
      <section class="logic-panel deval-form">
        <header class="logic-card-head">
          <div>
            <h2>{{ catalog?.name || "设备评估" }}</h2>
            <p>{{ catalog?.standard }}</p>
          </div>
          <el-button type="primary" :loading="evaluating" :disabled="!params.length" @click="evaluate">
            {{ evaluating ? "计算中…" : "开始评估" }}
          </el-button>
        </header>

        <div class="deval-picks">
          <label>
            子系统
            <el-select v-model="subsystemId" @change="deviceId = devices[0]?.id || ''">
              <el-option v-for="s in subsystems" :key="s.id" :label="s.name" :value="s.id" />
            </el-select>
          </label>
          <label>
            设备
            <el-select v-model="deviceId" filterable>
              <el-option v-for="d in devices" :key="d.id" :label="d.name" :value="d.id" />
            </el-select>
          </label>
        </div>

        <p class="deval-weight-bar" :class="{ ok: weightOk, bad: !weightOk }">
          权重合计 <strong>{{ weightSum }}%</strong>（须为 100%）
        </p>

        <article v-for="p in params" :key="p.id" class="deval-param">
          <div class="deval-param-head">
            <h3>{{ p.name }}</h3>
            <div class="deval-weight">
              <span>权重</span>
              <el-input-number
                v-model="weights[p.id]"
                :min="0"
                :max="100"
                :step="0.1"
                :precision="1"
                :controls="false"
              />
              <span class="deval-range">%</span>
            </div>
          </div>
          <p v-if="weightHint(p)" class="deval-range-hint">{{ weightHint(p) }}</p>
          <p v-if="p.hint" class="deval-hint">{{ p.hint }}</p>
          <p class="deval-rule">{{ p.rule_text }}</p>
          <div v-if="values[p.id]" class="deval-fields">
            <div v-for="field in p.fields" :key="field.key" class="deval-field">
              <el-checkbox
                v-if="field.type === 'checkbox'"
                v-model="values[p.id][field.key]"
              >
                {{ field.label }}
              </el-checkbox>
              <template v-else>
                <label>{{ field.label }}<span v-if="field.unit">（{{ field.unit }}）</span></label>
                <el-select
                  v-if="field.type === 'select'"
                  v-model="values[p.id][field.key]"
                  placeholder="请选择"
                  filterable
                >
                  <el-option
                    v-for="opt in field.options"
                    :key="opt.value"
                    :label="opt.label"
                    :value="opt.value"
                  />
                </el-select>
                <el-input-number
                  v-else
                  v-model="values[p.id][field.key]"
                  :controls="false"
                  class="deval-num"
                />
              </template>
              <p v-if="field.hint" class="deval-hint">{{ field.hint }}</p>
            </div>
          </div>
        </article>
      </section>

      <section class="logic-panel deval-result">
        <h3>评估结果</h3>
        <ul class="deval-clause">
          <li
            v-for="b in catalog?.abcd_bands || []"
            :key="b.grade"
            :class="{ current: result?.ok && b.grade === result.grade }"
          >
            {{ b.line }}
          </li>
        </ul>
        <p v-if="!result" class="logic-empty-hint">填完参数并点「开始评估」后，这里给出百分数和 A/B/C/D。</p>
        <div v-else-if="!result.ok">
          <p class="deval-err" v-for="(e, i) in result.errors" :key="i">{{ e }}</p>
        </div>
        <div v-else class="deval-grade-box">
          <div class="deval-letter" :class="'g-' + result.grade">{{ result.grade }}</div>
          <p class="deval-score">综合得分 {{ result.score }}</p>
          <p class="deval-grade-cap">{{ result.grade_line }}</p>
          <p v-for="(w, i) in result.warnings || []" :key="'w' + i" class="deval-warn">{{ w }}</p>
          <table class="deval-table">
            <thead>
              <tr>
                <th>参数</th>
                <th>权重</th>
                <th>该项得分</th>
                <th>加权</th>
                <th>说明</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="it in result.items" :key="it.id">
                <td>{{ it.name }}</td>
                <td>{{ it.weight }}%</td>
                <td>{{ it.score }}{{ it.grade_label ? `（${it.grade_label}）` : "" }}</td>
                <td>{{ it.contribution }}</td>
                <td>{{ it.note }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  </div>
</template>
