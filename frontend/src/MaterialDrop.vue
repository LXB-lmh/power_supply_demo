<template>
  <div
    class="material-drop"
    :class="{ dragover, compact }"
    @dragenter.prevent="onDragEnter"
    @dragover.prevent="dragover = true"
    @dragleave.prevent="onDragLeave"
    @drop.prevent="onDrop"
  >
    <p class="drop-title">{{ title }}</p>
    <p v-if="!compact" class="drop-hint">{{ single ? "可拖入或选择 1 个 Word 文件（不支持文件夹）。" : allowFolder ? "可拖入文件或整个文件夹；子文件夹里的材料也会收进来。" : "可拖入或选择 Word 文件。" }}</p>
    <p v-else class="drop-hint">{{ single ? "可放入 1 个 Word 文件。" : allowFolder ? "可放入文件或整个文件夹，子文件夹和 Excel 工作表都会查。" : "可放入 Word 文件。" }}</p>
    <div class="drop-actions">
      <button type="button" class="drop-btn" @click="pickFiles">选择文件</button>
      <button v-if="allowFolder" type="button" class="drop-btn" @click="pickFolder">选择文件夹</button>
      <button v-if="showClear && items.length" type="button" class="drop-btn drop-btn-danger" @click="clearAll">
        一键删除
      </button>
    </div>
    <input
      ref="fileInput"
      type="file"
      :multiple="!single"
      :accept="accept"
      hidden
      @change="onFileInput"
    />
    <input v-if="allowFolder" ref="folderInput" type="file" multiple hidden @change="onFolderInput" />
    <ul v-if="items.length && !compact" class="drop-list">
      <li v-for="item in items" :key="item.uid">
        <span :title="item.name">{{ item.name }}</span>
        <button type="button" class="drop-remove" @click="remove(item)">删除</button>
      </li>
    </ul>
    <p v-else-if="!items.length" class="drop-empty">尚未放入文件</p>
    <p v-if="items.length" class="drop-count">已放入 {{ items.length }} 个文件</p>
  </div>
</template>

<script setup>
/**
 * 材料拖放区。左侧分拣袋与右侧评估上传各用一个实例，列表互不相通。
 */
/** 材料拖放区：收文件或整个文件夹；评估框与分拣框共用，列表由父组件按专业/章分开存。 */
import { onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

const props = defineProps({
  title: { type: String, default: "将评估材料拖到此处" },
  items: { type: Array, default: () => [] },
  compact: { type: Boolean, default: false },
  showClear: { type: Boolean, default: false },
  /** false 时隐藏「选择文件夹」，逻辑性检测页专用，不影响其它上传区默认行为。 */
  allowFolder: { type: Boolean, default: true },
  /** true 时一次只允许放入一个文件（新文件覆盖旧文件），并拒绝文件夹，逻辑性检测页专用。 */
  single: { type: Boolean, default: false },
  accept: { type: String, default: ".docx,.doc,.xlsx,.xls,.pdf,.txt,.json" },
});
const emit = defineEmits(["update:items"]);

const fileInput = ref(null);
const folderInput = ref(null);
const dragover = ref(false);
let dragDepth = 0; // 子元素也会触发 dragleave，用进入次数判断是否还在区内

const ALLOWED = new Set([".docx", ".doc", ".xlsx", ".xls", ".pdf", ".txt", ".json"]);

onMounted(() => {
  if (!props.allowFolder) return;
  const el = folderInput.value;
  if (!el) return;
  el.setAttribute("webkitdirectory", "");
  el.setAttribute("directory", "");
});

function filePath(file) {
  return String(file?.relativePath || file?.webkitRelativePath || file?.name || "").replace(/\\/g, "/");
}

function suffix(name) {
  const text = String(name || "");
  const i = text.lastIndexOf(".");
  return i >= 0 ? text.slice(i).toLowerCase() : "";
}

/** 把相对路径写到 File 上，后端才能按子文件夹分拣，不能只靠 file.name。 */
function withPath(file, relativePath) {
  const path = String(relativePath || filePath(file) || file.name).replace(/\\/g, "/");
  const copy = new File([file], file.name, { type: file.type, lastModified: file.lastModified });
  Object.defineProperty(copy, "relativePath", { value: path, configurable: true });
  try {
    Object.defineProperty(copy, "webkitRelativePath", { value: path, configurable: true });
  } catch {
    copy.relativePath = path;
  }
  return copy;
}

/** 丢掉 Office 临时文件、系统垃圾和非文档后缀。 */
function isAllowed(file) {
  const path = filePath(file);
  const base = path.split("/").pop() || "";
  if (!base || base.startsWith("~$") || base.startsWith(".")) return false;
  if (["thumbs.db", "desktop.ini"].includes(base.toLowerCase())) return false;
  return ALLOWED.has(suffix(base));
}

function fileKey(file) {
  return `${filePath(file)}:${file.size || 0}:${file.lastModified || 0}`;
}

function toItem(file) {
  const path = filePath(file) || file.name;
  return {
    uid: `${fileKey(file)}:${Math.random().toString(36).slice(2, 8)}`,
    name: path,
    raw: file,
  };
}

/** 按路径+大小+修改时间去重后并入列表，已在框里的不再加一遍。 */
function mergeFiles(incoming) {
  const kept = incoming.filter(isAllowed);
  const skipped = incoming.length - kept.length;
  // 单文件模式：只保留一个文件，新文件覆盖旧文件；文件夹由 onDrop 提前拦截。
  if (props.single) {
    if (!kept.length) {
      ElMessage.warning(skipped ? "文件格式不支持，请放入 Word 文件" : "未识别到文件");
      return;
    }
    const file = kept[0];
    emit("update:items", [toItem(file)]);
    if (kept.length > 1) ElMessage.warning("一次只能放入一个文件，已保留第 1 个：" + (file.name || ""));
    else ElMessage.success("已放入 1 个文件");
    return;
  }
  const seen = new Set(props.items.map((item) => fileKey(item.raw)));
  const added = [];
  for (const file of kept) {
    const key = fileKey(file);
    if (seen.has(key)) continue;
    seen.add(key);
    added.push(toItem(file));
  }
  if (added.length) emit("update:items", [...props.items, ...added]);
  if (skipped) ElMessage.info(`已加入 ${added.length} 个材料，跳过 ${skipped} 个非文档文件`);
  else if (added.length) ElMessage.success(`已加入 ${added.length} 个材料`);
  else if (incoming.length) ElMessage.warning("没有新的文档材料（已在列表中，或格式不支持）");
}

function pickFiles() {
  fileInput.value?.click();
}

function pickFolder() {
  folderInput.value?.click();
}

function onFileInput(event) {
  mergeFiles([...event.target.files]);
  event.target.value = "";
}

function onFolderInput(event) {
  const files = [...event.target.files].map((file) => withPath(file, file.webkitRelativePath || file.name));
  mergeFiles(files);
  event.target.value = "";
}

function onDragEnter() {
  dragDepth += 1;
  dragover.value = true;
}

function onDragLeave() {
  dragDepth = Math.max(0, dragDepth - 1);
  if (!dragDepth) dragover.value = false;
}

async function onDrop(event) {
  dragDepth = 0;
  dragover.value = false;
  // 单文件模式禁止拖入文件夹：直接按拖入项判断，不展开目录树。
  if (props.single) {
    const droppedItems = [...(event.dataTransfer?.items || [])];
    const entries = droppedItems.map((item) => item.webkitGetAsEntry?.()).filter(Boolean);
    if (entries.some((entry) => entry.isDirectory)) {
      ElMessage.warning("一次只能放入一个 Word 文件，不能拖入文件夹");
      return;
    }
  }
  const files = await collectDropped(event.dataTransfer);
  mergeFiles(files);
}

/** webkit 目录读取器一次只给一批，必须循环读到空批次。 */
function readDir(dirEntry) {
  const reader = dirEntry.createReader();
  return new Promise((resolve, reject) => {
    const all = [];
    const tick = () => {
      reader.readEntries((batch) => {
        if (!batch.length) return resolve(all);
        all.push(...batch);
        tick();
      }, reject);
    };
    tick();
  });
}

function entryFile(entry) {
  return new Promise((resolve, reject) => entry.file(resolve, reject));
}

/** 递归展开拖入的文件夹，子目录里的材料一并收下。 */
async function filesFromEntry(entry, prefix = "") {
  if (!entry) return [];
  if (entry.isFile) {
    const file = await entryFile(entry);
    const rel = prefix ? `${prefix}/${entry.name}` : entry.name;
    return [withPath(file, rel)];
  }
  if (entry.isDirectory) {
    const children = await readDir(entry);
    const next = prefix ? `${prefix}/${entry.name}` : entry.name;
    const out = [];
    for (const child of children) {
      out.push(...(await filesFromEntry(child, next)));
    }
    return out;
  }
  return [];
}

/** 优先走 webkitGetAsEntry，才能拿到文件夹树；否则退回扁平 FileList。 */
async function collectDropped(data) {
  const items = [...(data?.items || [])];
  if (items.some((item) => item.webkitGetAsEntry?.())) {
    const out = [];
    for (const item of items) {
      const entry = item.webkitGetAsEntry?.();
      if (entry) out.push(...(await filesFromEntry(entry)));
      else if (item.kind === "file") {
        const file = item.getAsFile();
        if (file) out.push(withPath(file, file.name));
      }
    }
    return out;
  }
  return [...(data?.files || [])].map((file) => withPath(file, file.webkitRelativePath || file.name));
}

function remove(item) {
  emit(
    "update:items",
    props.items.filter((row) => row.uid !== item.uid),
  );
}

async function clearAll() {
  if (!props.items.length) return;
  try {
    await ElMessageBox.confirm(`删除当前已放入的 ${props.items.length} 个文件？`, "一键删除", {
      type: "warning",
      confirmButtonText: "全部删除",
      cancelButtonText: "取消",
    });
  } catch {
    return;
  }
  emit("update:items", []);
}
</script>
