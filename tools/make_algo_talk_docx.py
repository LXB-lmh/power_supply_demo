# -*- coding: utf-8 -*-
"""材料检索与一致性匹配算法说明（讲算法 + 附带注释代码）。"""
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor


def _font(run, *, size=12, bold=False, name="宋体", west="Times New Roman", color=None):
    run.bold = bold
    run.font.size = Pt(size)
    run.font.name = west
    if color is not None:
        run.font.color.rgb = color
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.get_or_add_rFonts()
    rFonts.set(qn("w:eastAsia"), name)


def _p(doc, text, *, size=12, bold=False, indent=True, after=6):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_after = Pt(after)
    pf.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    if indent:
        pf.first_line_indent = Cm(0.74)
    _font(p.add_run(text), size=size, bold=bold)
    return p


def _h(doc, text, level=1):
    p = doc.add_heading("", level=level)
    _font(p.add_run(text), size={1: 16, 2: 14, 3: 12}.get(level, 12), bold=True, name="黑体")
    return p


def _li(doc, items):
    for t in items:
        p = doc.add_paragraph(style="List Number" if False else "List Bullet")
        p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
        p.paragraph_format.space_after = Pt(3)
        _font(p.add_run(t), size=12)


def _src(doc, path_hint: str):
    """代码出处小字。"""
    p = doc.add_paragraph()
    p.paragraph_format.first_line_indent = Cm(0)
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(2)
    _font(p.add_run(f"【代码位置】{path_hint}"), size=10.5, name="楷体", color=RGBColor(0x55, 0x55, 0x55))


def _code(doc, lines: list[str]):
    """附带注释的代码块（等宽、浅灰感用小字号区分）。"""
    for line in lines:
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.first_line_indent = Cm(0)
        pf.space_before = Pt(0)
        pf.space_after = Pt(0)
        pf.line_spacing = 1.1
        left = line.lstrip(" ")
        # 整行注释用灰色
        if left.startswith("#"):
            _font(p.add_run(line), size=9.5, name="宋体", west="Consolas", color=RGBColor(0x2E, 0x7D, 0x32))
        else:
            _font(p.add_run(line), size=9.5, name="宋体", west="Consolas")
    # 代码块后空一行
    doc.add_paragraph().paragraph_format.space_after = Pt(6)


def build(out: Path) -> Path:
    doc = Document()
    for s in doc.sections:
        s.top_margin = Cm(2.4)
        s.bottom_margin = Cm(2.4)
        s.left_margin = Cm(2.6)
        s.right_margin = Cm(2.6)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_before = Pt(48)
    _font(title.add_run("供电评估报告辅助系统"), size=20, bold=True, name="黑体")

    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.paragraph_format.space_before = Pt(12)
    _font(sub.add_run("材料检索与一致性匹配算法说明"), size=16, bold=True, name="黑体")

    note = doc.add_paragraph()
    note.alignment = WD_ALIGN_PARAGRAPH.CENTER
    note.paragraph_format.space_before = Pt(18)
    _font(note.add_run("讲解用：算法步骤 + 关键代码（含中文注释）"), size=12, name="楷体")

    doc.add_page_break()

    # ---------- 1 ----------
    _h(doc, "1 问题定义", 1)
    _p(doc, "编制供电专业设施设备运营评估报告时，输入是一批异构材料（线路评估稿、设备总表、退运说明等）。系统需要完成两类判定：")
    _li(
        doc,
        [
            "材料检索：某文件是否属于供电材料；若属于，应归属第 3～11 章中的哪些章。",
            "一致性匹配：抽取正文时，段落须落在正确小节与正确号线；成文后还需检查表述与数字是否自洽。",
        ],
    )
    _p(doc, "二者都基于正文与表格内容，不以文件夹名称作为硬约束，以便材料存放位置变化后规则仍可用。")

    # ---------- 2 ----------
    _h(doc, "2 材料检索算法", 1)
    _p(doc, "入口模块：catalog/classify_materials.py。单文件主流程为 classify_document；批量入口为 classify_paths。")

    _h(doc, "2.1 算法流程", 2)
    _li(
        doc,
        [
            "解析文件为统一文档模型（段落、表格）。",
            "专业域分流：供电 / 接触网 / 混合 / 未知。",
            "若判定为纯接触网，供电侧不再分章。",
            "对照「各章需求词表」做全文命中；同时对各章做抽取试跑，能抽出有效结构则记为强证据。",
            "规则命中与（可选）大模型复核结果取并集，得到建议章节列表。",
        ],
    )

    _h(doc, "2.2 专业域分流：关键词加权计分", 2)
    _p(doc, "对全文统计供电词表与接触网词表的命中次数。排序时优先长词，避免「接触网」命中后再被「触网」重复计分。长度≥4 的词权重大于短词。比较两域得分得到分流结果；工作表名可加权。")
    _src(doc, "catalog/classify_materials.py → _keyword_score / _domain_from_content")
    _code(
        doc,
        [
            "def _keyword_score(text, keys):",
            "    # 关键词加权计分：长词优先，防止子串重复加分",
            "    accounted = []",
            "    score = 0",
            "    for key in sorted(set(keys), key=len, reverse=True):  # 先匹配更长的词",
            "        # 若已被更长词覆盖（如已计「接触网」），则跳过「触网」",
            "        if any(key != longer and key in longer for longer in accounted):",
            "            continue",
            "        n = text.count(key)",
            "        if not n:",
            "            continue",
            "        accounted.append(key)",
            "        # 长词权重 2，短词权重 1",
            "        score += n * (2 if len(key) >= 4 else 1)",
            "    return score",
            "",
            "# 分流逻辑（简化）：",
            "# power_score = 供电词表得分；oh_score = 接触网词表得分",
            "# 两者都有且供电分不低于触网分（或供电分≥2）→ 混合",
            "# 仅供电分 > 0 → 供电；仅触网分 > 0 → 接触网；否则未知",
        ],
    )

    _h(doc, "2.3 各章需求：去年目录映射", 2)
    _p(doc, "若提供去年完整年报，扫描其标题行，用「去年小节对照表」把标题关键词映射到第 3～11 章，形成各章需求集合。无去年报告时使用默认需求词表。对照表本身是静态配置，不绑定具体年份文件名。")
    _src(doc, "catalog/classify_materials.py → PRIOR_SECTION_MAP / build_prior_needs")
    _code(
        doc,
        [
            "# 去年小节标题关键词 → 章节编号（节选）",
            "PRIOR_SECTION_MAP = (",
            "    (\"ch3\", (\"设备功能有效性\", \"评估方法和内容\", \"管控措施\", ...)),",
            "    (\"ch4\", (\"运营契合\", \"年度生产指标\", \"MTBF\", \"MCBF\", ...)),",
            "    (\"ch7\", (\"运维表现\", \"生产组织\", \"生产计划执行\", \"运维质量\")),",
            "    (\"ch11\", (\"退运报废\", \"退运更换\", \"报废\", \"工器具配置\")),",
            "    # …其余章同理",
            ")",
            "",
            "# build_prior_needs：遍历去年报告标题",
            "# 若标题压缩串命中某章关键词 → 把该标题/关键词写入 needs[章号]",
        ],
    )

    _h(doc, "2.4 分章判定：需求命中 ∪ 抽取试跑", 2)
    _p(doc, "对供电材料，系统并行计算两类证据并合并：① 全文是否出现该章强特征词；② 调用该章抽取函数，是否得到有效段落或表格。仅有弱词不足以单独分章，以降低误报。")
    _src(doc, "catalog/classify_materials.py → classify_document")
    _code(
        doc,
        [
            "def classify_document(doc, ..., prior_needs=None):",
            "    # ① 专业域分流（供电 / 接触网 / 混合）",
            "    picked = pick_power_material(doc, use_llm=use_llm)",
            "    if picked[\"bucket\"] == \"overhead\":",
            "        return 空结果  # 纯接触网：供电分章直接结束",
            "",
            "    full = _full_text(doc)  # 全文（段+表），禁止只扫前几页",
            "    # ② 抽取试跑：各章 extract 能否抽出有效内容",
            "    extract_hits = _hits_power(doc, assessment_year)",
            "    # ③ 对照各章需求词表做全文命中",
            "    need_hits = _hits_from_needs(full, prior_needs)",
            "    rule_hits = _merge_hits(extract_hits, need_hits)  # 规则并集",
            "",
            "    # ④ 可选：大模型复核，再与规则取并集（模型命中须能在正文对上词表）",
            "    llm_hits = _llm_review_chapters(...) if use_llm else []",
            "    hits = _merge_hits(rule_hits, llm_hits)",
            "    return {\"chapters\": hits, \"bucket\": picked[\"bucket\"], ...}",
        ],
    )
    _p(doc, "检索的本质是「可服务性匹配」：材料能否支撑某章成文，而不只是文件名相似。")

    # ---------- 3 ----------
    _h(doc, "3 一致性匹配算法", 1)
    _p(doc, "一致性分三层：小节切片一致、号线归属一致、逻辑表述一致。")

    _h(doc, "3.1 命名节切片（防串章）", 2)
    _p(doc, "模块：chapters/common/section_slice.py。从起始关键词开始收录，遇到停词、其它章标题或外来大纲节号则停止。节号采用边界匹配：「4.2」不得命中「4.4.2」。短停词仅在短行或行首生效，避免正文偶然出现「退运」等词导致误截。培训课表「2024.7《…》」按年月条目处理，不视为目录节号。")
    _src(doc, "chapters/common/section_slice.py → hits_section_key / is_outline_title_line")
    _code(
        doc,
        [
            "def hits_section_key(compact, keys, title_only_words=False):",
            "    num = outline_num(compact)  # 行首节号，如 4.2 / 4.4.2",
            "    for k in keys:",
            "        if key_is_section_num(k):",
            "            # 边界匹配：相等，或 num 是 k 的下级（4.2 可匹配 4.2.1）",
            "            # 但「4.2」不能匹配「4.4.2」（前缀不是 4.2.）",
            "            if num == k or (num and num.startswith(k + \".\")):",
            "                return True",
            "            continue",
            "        # 普通关键词：默认要求短行/行首，降低正文误触发",
            "        ...",
            "",
            "def is_outline_title_line(compact):",
            "    # 2024.7《主题培训》是年月课表，不是 4.2 这类目录标题",
            "    if re.match(r\"^20\\d{2}[.．]\\d{1,2}\", compact) and \"培训\" in compact:",
            "        return False",
            "    return 是否匹配「数字.数字」开头的短标题行",
        ],
    )

    _h(doc, "3.2 号线归属一致（段首点名归线）", 2)
    _p(doc, "模块：chapters/power/extract.py（第 7 章按线路成文）。合订本中常见「文件名主线」与「段落主语线」不一致。算法：")
    _li(
        doc,
        [
            "以文件名解析的号线为主线默认归属。",
            "若段首（可带序号前缀）点名 N 号线且 N≠主线，则将该段落改挂到 N，并从主线剔除。",
            "全文补扫：段首号线可判定、且分项类型（计划/仪表/培训/智能）与目标小节一致时，并入对应号线（去重）。",
        ],
    )
    _src(doc, "chapters/power/extract.py → _leading_line_no / _foreign_line_subject / _harvest_ch7_named_line_paras")
    _code(
        doc,
        [
            "def _leading_line_no(text):",
            "    # 解析段首号线：支持「11号线…」「1、11号线…」「十一号线…」",
            "    t = compact_text(text)",
            "    t = re.sub(r\"^[（(]?\\d+[)）、．.]\\s*\", \"\", t)  # 去掉清单序号",
            "    m = re.match(r\"^(\\d{1,2})\\s*#?\\s*号线\", t)",
            "    if m:",
            "        n = int(m.group(1))",
            "        return n if 1 <= n <= 18 else None",
            "    # 再尝试中文号线：十一、十二、…",
            "    ...",
            "",
            "def _foreign_line_subject(text, host_line):",
            "    # 段首号线与文件名主线不同 → 返回旁线号，供改挂",
            "    n = _leading_line_no(text)",
            "    if n is None or n == host_line:",
            "        return None",
            "    return n",
            "",
            "# 抽取时：主线桶保留非旁线段落；旁线段落 merge 到 by_no[N]",
            "# 最后 _harvest_ch7_named_line_paras：全文再扫段首号线+分项类型，防止节名变更漏抽",
        ],
    )

    _h(doc, "3.3 运维四分法分桶（防串分项）", 2)
    _p(doc, "在「运维表现」整段内，按开段标记与关键词将内容分入计划、仪表、培训、智能四类。课表行「1、2025.5《…》培训」不触发换桶；「1、视频查看…」等可按智能关键词换桶，避免培训与智能互串。")
    _src(doc, "chapters/power/extract.py → _split_ch7_ops_blob / _ch7_marker_aspect")

    _h(doc, "3.4 逻辑一致性检测", 2)
    _p(doc, "模块：chapters/common/consistency_logic.py；数字与年份细则在 number_logic.py。将文档压成有序文本单元，对每个单元取邻域窗口，检测：评级良好与报废同现、总数与「其中」分项合计不符、截止年与评估年冲突等。")
    _src(doc, "chapters/common/consistency_logic.py → _scan_contradictions / check_document_logic")
    _code(
        doc,
        [
            "def _scan_contradictions(units, out):",
            "    for idx, unit in enumerate(units):",
            "        # 以当前句为中心，取前后各 4 个单元拼成上下文窗口",
            "        win = _window_text(units, idx, radius=4)",
            "        # 规则1：窗口内同时出现 A类/良好 与 报废/无再利用",
            "        if _GRADE_A.search(win) and _SCRAP.search(win):",
            "            _add(out, issue=\"上下文相悖\", note=\"评级与报废表述冲突\", ...)",
            "        # 规则2：运行正常 与 必须更换/严重隐患 同现",
            "        if _GOOD.search(win) and _BAD.search(win):",
            "            _add(out, issue=\"上下文相悖\", ...)",
            "",
            "def check_document_logic(path, assessment_year=None, ...):",
            "    units = _blocks_to_units(parse_file(path))  # 段+表 → 单元序列",
            "    findings = []",
            "    _scan_contradictions(units, findings)          # 表述相悖",
            "    _fix_numeric_section(units, findings, year)  # 数字合计 / 年份",
            "    # 另：表中含 A 级且邻近正文含报废 → 追加一条",
            "    return {\"findings\": findings, \"summary\": ...}",
        ],
    )

    # ---------- 4 ----------
    _h(doc, "4 设计约束", 1)
    _li(
        doc,
        [
            "内容优先于路径：文件夹名不决定专业域。",
            "规则为主、模型为辅：模型结果须有正文词表锚点。",
            "结构可迁移：节号边界、段首号线、滑动窗口等规则不绑定某年某线某目录。",
            "缺料可见：匹配失败则标题标黄，不编造；关键表禁止用往年数据顶替当年。",
        ],
    )

    # ---------- 5 ----------
    _h(doc, "5 讲解顺序建议", 1)
    _li(
        doc,
        [
            "材料检索：计分分流 → 去年小节对照 → 需求命中与抽取试跑并集（展示 classify_document）。",
            "一致性：切片边界（展示 hits_section_key）→ 段首归线（展示 _leading_line_no）→ 窗口相悖（展示 _scan_contradictions）。",
            "各举一例：合订本旁线段落；年月课表不作节号；A 类与报废同窗。",
        ],
    )

    _h(doc, "6 模块索引", 1)
    _li(
        doc,
        [
            "材料检索：catalog/classify_materials.py",
            "小节切片：chapters/common/section_slice.py",
            "号线归线与第7章分桶：chapters/power/extract.py",
            "逻辑检测：chapters/common/consistency_logic.py、number_logic.py",
            "接口：api/main.py（材料分拣、逻辑检测两个接口）",
        ],
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    return out


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(build(root / "docs" / "材料检索与一致性匹配算法说明.docx"))
