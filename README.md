# PaperOrchestra — Claude Edition

Claude-only fork of [google-research/paper-orchestra](https://github.com/google-research/paper-orchestra), maintained at [lllfx/paper-orchestra](https://github.com/lllfx/paper-orchestra).

本版本使用 **Anthropic Claude** 完成提纲、文献筛选、分节写作、审稿、修稿和 PDF 排版检查。文献通过 Semantic Scholar、Crossref 和 arXiv 的公开接口查询；不调用 Gemini，不需要 Google / OpenAI 的 SDK 或密钥。

输入研究想法、已核实的实验日志和已有图片，输出可审阅的 LaTeX/PDF 初稿。**它不运行研究实验，也不以模型审稿分数代替数字核对、结论审查或引用全文核查。**

## 安装

推荐 Python 3.11；离线测试也覆盖 Python 3.10。

```bash
git clone --branch claude https://github.com/lllfx/paper-orchestra.git
cd paper-orchestra
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

系统还需要 `pdflatex` 和 `bibtex`，以及所用会议模板的 TeX 包。程序会在产生模型费用前检查两个可执行文件是否存在；模板缺包仍需在本机解决。

## 配置 Claude

```bash
cp .env.example .env
```

在本地 `.env` 中填写：

```dotenv
ANTHROPIC_API_KEY=your_private_key
ANTHROPIC_BASE_URL=https://api.anthropic.com
ANTHROPIC_MODEL=claude-opus-5-5
ANTHROPIC_MAX_TOKENS=16384

# 需要代理时填写你自己的地址
# HTTPS_PROXY=http://127.0.0.1:7890
# HTTP_PROXY=http://127.0.0.1:7890

# 可选；未配置时仍会尝试公开学术检索接口
SEMANTIC_SCHOLAR_API_KEY=
```

`.env` 已被 Git 忽略。密钥不写入执行日志和费用记录。已导出的环境变量优先于 `.env`，使用前应确认环境里的接口地址和代理符合预期。模型 ID 必须是账户可用的 `claude-*` 模型；不自动退回其他供应商或模型。

## 准备材料

```text
my_materials/
├── idea_sparse.md          # 研究问题、方法、允许的贡献主张
├── experimental_log.md     # 已核实的实验结果与局限，标明原始结果文件
├── claims.md               # 可选：明确允许/禁止的结论，传给写作与审稿阶段
└── figures/
    ├── info.json
    └── verified_plot.pdf
```

`figures/info.json` 是列表；没有图片时可填写 `[]`：

```json
[
  {"name": "verified_plot.pdf", "caption": "Author-verified figure caption."}
]
```

使用真实结果文件生成的表格和图片，不让模型重算实验数值。把失败结果、事后设计的分析和样本缺失也写进日志。`claims.md` 是模型上下文中的约束，不是自动证明结论正确的校验器。

仓库提供 `examples/minimal/` 作为文件结构示例，内容均为合成演示材料，不代表研究结果。

## 运行

```bash
python paper_writing_cli.py \
  --raw_materials_dir /path/to/my_materials \
  --latex_template_dir templates/iclr2025 \
  --output_dir /path/to/new_output \
  --use_plotting false
```

或：

```bash
bash paper_writing_cli.sh /path/to/my_materials /path/to/new_output templates/iclr2025
```

输出目录必须是新的或空的，不能放在输入材料目录之内。程序不会覆盖已有初稿。默认不在控制台打印正文或结果表，只打印 Markdown 报告路径。

模型可分别指定：

```bash
python paper_writing_cli.py \
  --raw_materials_dir /path/to/my_materials \
  --latex_template_dir /path/to/kdd_template \
  --output_dir /path/to/new_output \
  --writer_model_name claude-opus-5-5 \
  --reflection_model_name claude-opus-5-5
```

自定义会议模板目录需包含 `template.tex`、`guidelines.md` 及编译依赖；原仓库仅附带 CVPR/ICLR 模板，没有内置 KDD 模板。

## 输出与人工复核

- `RUN_REPORT.md`：运行结果、文件链接，明确标注 **human review required**。
- `final_paper.pdf` / `final_paper.tex`：PDF 和最终主 LaTeX 文件。完整图片、BibTeX 和编译资源在 `content_refinement_workdir/`，只复制主 `.tex` 无法独立编译。
- `materials_manifest.json`：输入材料逐文件 SHA256。
- `run_config.json`、`run.log`：配置与执行过程，不包含 API 密钥。
- `usage.jsonl`：每个已收到完整 API 响应的用量、模型、请求/响应 ID 和停止原因；截断或解析失败的响应也记录。网络中断前的未完整响应可能无法取得最终用量，应与服务商账单核对。
- `literature_agent_output/search_audit/`：查询、来源记录、失败来源、候选与选择结果。
- `literature_agent_output/citation_map.json`：引用元数据、DOI/URL、检索时间及证据级别。

提交论文前必须将正文和表格中的数字与原始结果逐项核对，并审查结论边界和引用是否得到原文支持。`abstract_only` 表示只取得摘要，`metadata_only` 只能确认书目信息，均不等于全文核查。

需要费用估算时，在 `.env` 中填入运行当天的官方输入/输出单价（美元 / 百万 token）：

```dotenv
ANTHROPIC_PRICE_INPUT_PER_MILLION=...
ANTHROPIC_PRICE_OUTPUT_PER_MILLION=...
```

不填则只记录 token，不假定价格。本版本没有实现硬性总预算上限；每次写作的账本独立于其他实验。默认使用流式响应，SDK 只对可重试的网络/服务错误重试；无效 JSON、输出截断等不会自动再次付费请求。主流水线失败也不会整套自动重跑。

## 文献检索的变化

Claude 生成最多三个查询词，然后从接口返回的真实候选里按 ID 选择论文；不能直接增加模型记忆中的标题。各来源有频率限制，返回不完整时保留失败记录，全部来源失败则终止。

`--research_cutoff 2025-11` 表示严格早于 **2025-11-01**；也接受 `YYYY-MM-DD`。缺少足够日期信息的同年论文保守排除，不会猜测月份。默认截止时间是运行所在月份的第一天。

不截断原始摘要，但仍需人工核查支撑核心论断的全文。没有开放数据集的部分不宣称复现上游论文评测。

## 已禁用的功能

自动绘图、模型生成 Python 的执行、位图图片生成均不启用；`--use_plotting true` 会直接报错。Claude 可以读已有图片并检查版式，这不需要图片生成模型。

旧的 Gemini/OpenAI 适配器已移除；原有审稿评分逻辑保留，但所有评审调用也改为 Claude。

## 测试

```bash
python -m unittest discover -s tests -v
```

测试使用真实 Anthropic SDK 配合内存 HTTP 模拟，包括贯穿写作流水线的集成测试。不会访问模型或学术接口，不需要真实密钥、不产生 API 费用。集成测试模拟 LaTeX 编译；它不证明本机的 TeX 环境已经完整安装。验证范围见 [迁移说明](docs/CLAUDE_MIGRATION.md) 和 [测试报告](docs/TEST_REPORT.md)。

## 可选网页界面

```bash
pip install -r requirements-frontend.txt
streamlit run frontend/app.py
```

网页使用同一 Claude 后端，自动图片生成选项关闭。网页界面的交互体验仍需在实际浏览器中验收。

## 原项目与许可证

原作者：Yiwen Song、Yale Song、Tomas Pfister、Jinsung Yoon，Google Cloud AI Research。

本 fork 沿用 Apache 2.0 许可证，保留原项目署名；不是 Google 或 Anthropic 官方产品。原论文：

```bibtex
@article{song2026paperorchestra,
  title={PaperOrchestra: A Multi-Agent Framework for Automated AI Research Paper Writing},
  author={Song, Yiwen and Song, Yale and Pfister, Tomas and Yoon, Jinsung},
  journal={arXiv preprint arXiv:2604.05018},
  year={2026}
}
```
