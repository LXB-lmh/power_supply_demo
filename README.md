# 供电评估报告智能生成系统

基于 FastAPI + Vue 3 的本机 Web 应用，面向上海轨道交通运营设施设备年度评估报告编制场景。系统按专业（供电 / 接触网）隔离材料与成稿链路，支持第 3～11 章 Word 报告生成、报告逻辑性检测，以及团标附录口径下的单台设备评分。

默认服务地址：`http://127.0.0.1:8000`

---

## 功能概览

### 1. 分专业年度报告生成

- **供电（含能源系统）** 与 **接触网** 两套工作台，材料、任务进度、成稿互不串用。
- 覆盖第 3～11 章（设备功能有效性、运营契合、管理体系合规、修程修制、运维表现、风险隐患、备件物资、使用环境、退运报废等）。
- 支持上传「去年完整评估报告」学习目录与体例；未上传时使用项目内 2025 保底年报资产。
- **材料分拣**：上传全年材料包后解析，按章给出「本章建议」文件列表；可复用上次解析缓存。
- **按章评估**：将本章材料提交后端抽取并写成 Word；缺材料处标黄，不编造数字；各章「评估小结」固定黄标题留空。
- 评估结果区展示标点/缺材料、语言与年份等问题提示，并可下载成稿。

### 2. 逻辑性检测

- 独立页签，不进入报告生成链路。
- **完整报告检测**：检查第 3～11 章的错别字、标点、语言不通顺、段内计算、年份口径，以及跨章严重逻辑矛盾（如第 3 章评为 A/B 级、第 11 章写成报废）。
- **章节检测**：仅检查所选章；即使上传完整报告，也只切出该章正文。
- 供电 / 触网使用各自设备词表与错别字规则；章名末尾备注（如「待更新」）不影响章界识别。
- 检测结果可在页面查看，并支持导出 Word 结果稿（以当前前端实现为准）。

### 3. 团标单台设备评估

- **主变电系统设备评估**、**供电（含能源系统）设备评估**。
- 按团标附录设备表选择设备、填写参数与权重，输出百分制评分与 A/B/C/D 等级。
- 与各章年报生成相互独立。

---

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 后端 | Python 3.10+，FastAPI，Uvicorn |
| 文档处理 | python-docx，openpyxl，pdfplumber；旧版 `.doc`/`.xls` 经本机 Word COM 或 LibreOffice 转换 |
| 前端 | Vue 3，Vite，Element Plus，Axios |
| 可选模型 | DeepSeek API（触网 LLM 门控、逻辑检测语义复核）；无密钥时规则链路仍可运行 |

---

## 环境要求

- 操作系统：Windows 10 / 11（推荐）
- Python 3.10～3.13
- 若需重新构建前端：Node.js 18+（含 npm）
- 若材料含 `.doc` / `.xls`：本机安装 Microsoft Word，或 LibreOffice
- （可选）DeepSeek API Key，用于 LLM 相关能力

---

## 安装

### 1. 获取代码

将项目解压到本地目录（路径可含中文；若旧版 Office 转换失败，可优先使用 `.docx` / `.xlsx` 材料）。

### 2. 创建 Python 虚拟环境并安装依赖

在项目根目录执行：

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install -U pip
pip install -r requirements.txt
```

### 3. 配置环境变量

```bat
copy .env.example .env
```

编辑 `.env`（主要项）：

| 变量 | 说明 |
| --- | --- |
| `DEEPSEEK_API_KEY` | API 密钥；未配置时跳过依赖模型的步骤 |
| `DEEPSEEK_BASE_URL` | 默认 `https://api.deepseek.com`；可改为本地兼容接口 |
| `DEEPSEEK_MODEL` | 默认 `deepseek-chat` |
| `OVERHEAD_LLM_GATE` | `1` 开启触网抽取 LLM 门控，`0` 关闭 |

### 4. 前端静态资源

发行包若已包含 `frontend/dist/`，可跳过本步。

若无 `frontend/dist/index.html`，或修改了 `frontend/src` 后需要刷新页面：

```bat
cd frontend
npm install
npm run build
cd ..
```

启动脚本在检测到 `frontend/node_modules` 存在且源码新于 `dist` 时，会尝试自动执行 `npm run build`。

### 5. 验证安装

```bat
.venv\Scripts\activate
python -c "import fastapi, docx, openpyxl, pdfplumber; print('backend ok')"
pytest -q
```

---

## 启动与使用

### 启动服务

任选其一：

```bat
.venv\Scripts\activate
python run_web.py
```

或运行 `启动系统.py`（IDE / 双击均可）。

服务监听 `127.0.0.1:8000`，就绪后自动打开浏览器。

**注意：** Uvicorn 未开启热重载。修改 Python 后端后须结束进程并重新启动；仅刷新浏览器不会加载新后端逻辑。

### 报告生成（供电 / 接触网）

1. 顶栏选择 **供电** 或 **接触网**。
2. （可选）在左侧「去年报告」放入上年完整评估报告（优先 `.docx`）。
3. （可选）在「材料分拣」放入全年材料包，点击 **解析**；在「本章建议」中点选文件加入本章上传区，或使用 **使用上次解析**。
4. 左侧选择目标章节（第 3～11 章）。
5. 在右侧上传本章材料（支持文件与文件夹；Excel 读取全部工作表）。
6. 确认评估年份，点击 **开始评估**，等待进度完成后下载 Word。

### 逻辑性检测

1. 顶栏进入 **逻辑性检测**。
2. 选择 **供电报告** 或 **触网报告**。
3. **完整评估报告逻辑性检测**：上传整本年报 Word，检查第 3～11 章及跨章矛盾。
4. **章节逻辑性检测**：选择章节后上传单章或完整报告，仅检查该章。
5. 结果在右侧展示；可按页面提供的导出能力保存检测结果。

### 团标设备评估

1. 顶栏进入 **主变电系统设备评估** 或 **供电（含能源系统）设备评估**。
2. 选择设备，填写参数与权重。
3. 点击 **开始评估**，查看百分数与等级。

---

## 目录结构

```text
power_supply_demo/
├── api/                 # FastAPI 路由与任务状态
├── catalog/             # 专业/章节目录、材料分拣
├── chapters/            # 各章抽取与成文（power / overhead 分册）
│   ├── power/assets/    # 供电 2025 保底年报
│   └── overhead/assets/ # 触网 2025 保底年报与大纲
├── device_eval/         # 团标单台设备评分
├── engine/              # LLM 等配置入口
├── frontend/            # Vue 源码与构建产物（dist）
├── parsers/             # docx/xlsx/pdf 解析与旧格式转换
├── scope/               # 预览、台账、报告登记
├── tests/               # pytest
├── paths.py             # uploads / output / jobs / parse_cache
├── web_server.py        # 启动入口（端口、前端构建、打开浏览器）
├── run_web.py / 启动系统.py
├── requirements.txt
├── .env.example
└── README.md
```

运行时自动创建或写入（可不纳入发行包）：

| 路径 | 作用 |
| --- | --- |
| `uploads/` | 上传材料副本 |
| `output/` | 生成的报告与任务产物 |
| `jobs/` | 任务进度 JSON |
| `parse_cache/` | 解析与分拣缓存 |

---

## 依赖说明

见根目录 `requirements.txt`。

- 主流程：`fastapi`、`uvicorn`、`python-docx`、`openpyxl`、`pdfplumber`、`openai`、`python-dotenv`、`python-multipart`
- 测试：`pytest`、`lxml`
- 可选：`pywin32`（本机 Word COM 转换 `.doc`；未安装时依赖 LibreOffice，或直接使用 `.docx`）

---

## 发行与部署建议

打包给其他机器使用时建议：

**纳入压缩包**

- 全部业务源码与 `tests`
- `chapters/*/assets` 下的保底年报与大纲
- `requirements.txt`、`.env.example`、本 README
- `frontend/dist/`（避免目标机必须先装 Node）

**不要纳入（或解压后删除）**

- `.env`（避免泄露个人 API Key；目标机用 `.env.example` 复制配置）
- `uploads/`、`output/`、`jobs/`、`parse_cache/`
- `frontend/node_modules/`
- `__pycache__/`、`.pytest_cache/`、`.idea/` 等

目标机按「安装 → 配置 `.env` → 启动」即可使用；`uploads` 等目录会在首次运行时自动创建。

---

## 常见问题

**页面空白或仅有接口说明**  
缺少 `frontend/dist`。执行 `frontend` 下 `npm install` 与 `npm run build`。

**`.doc` / `.xls` 转换失败**  
安装 Microsoft Word 或 LibreOffice，或先转换为 `.docx` / `.xlsx` 再上传。

**端口 8000 被占用**  
结束占用该端口的旧进程后重新启动。

**修改代码后行为未变化**  
后端需重启进程；前端源码变更后需重新 `npm run build`（或确保存在 `node_modules` 并由启动脚本触发构建）。

**LLM 相关步骤未执行**  
检查 `.env` 中 `DEEPSEEK_API_KEY` 与网络；触网门控可设 `OVERHEAD_LLM_GATE=0`。

---

## 许可与数据

本仓库用于评估报告编制辅助。上传材料与生成报告默认仅保存在本机对应目录，请按单位数据管理要求处理。
