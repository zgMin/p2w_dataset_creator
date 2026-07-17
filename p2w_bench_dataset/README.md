# P2W-Bench-ZHEN

面向 Prompt-to-Weight 方法的中英文测试数据集构建流水线。项目从公共数据下载开始，经过查询筛选、prompt 构造、冗余长度扩展、配对和一致性检查，生成可直接用于后续实验的 JSONL 数据。

当前版本只构建数据，不生成 full-prompt 参考输出，也不运行任何权重转换实验。实验输入在运行时按以下方式组合：

```text
{prompt}
{query}
```

## 快速开始

只需要 Python 3.9 或更新版本，不要求安装第三方包：

```bash
cd p2w_bench_dataset
python3 scripts/run_pipeline.py
```

也可以分阶段运行：

```bash
python3 scripts/download_sources.py
python3 scripts/build_dataset.py
python3 scripts/validate_dataset.py
```

下载器支持断点式缓存：目标文件已经存在时不会重复下载。使用 `python3 scripts/download_sources.py --force` 可强制重新下载。

## 当前规模

每种语言包含：

| 类别 | 指令组数 | 每组查询数 | 查询数 |
|---|---:|---:|---:|
| 公共知识问答 | 10 | 1 | 10 |
| 虚构或反事实知识 | 2 | 1 | 2 |
| 描述性任务 | 6 | 3 | 18 |
| 风格约束 | 6 | 1 | 6 |
| 格式约束 | 6 | 1 | 6 |
| 输出控制 | 4 | 1 | 4 |
| 合计 | 34 | - | 46 |

每个样本组具有三档语义不变的冗余 prompt：

- `short`：30-95 个近似 token（知识类保留完整的局部证据窗口）。
- `medium_redundant`：90-150 个近似 token。
- `long_redundant`：180-280 个近似 token。

中英文共 68 个 prompt group、92 个 query、204 个 prompt variant 和 276 个 prompt-query 配对。描述性任务中，同一指令的三个长度版本会分别与该指令下的三个查询组合。近似 token 统计不依赖模型；实验阶段可额外使用目标模型 tokenizer 记录精确 token 数。

## 目录

```text
benchmark_config.json          样本数量、长度范围、下载地址
config/
  prompt_templates.json        风格、格式和输出控制模板
  synthetic_knowledge.json     少量虚构与反事实知识
data/
  raw/                         下载的公共原始数据和校验清单
  interim/                     选中的 query 池与 prompt group
  final/                       最终数据集
scripts/
  download_sources.py          公共数据下载
  build_dataset.py             数据选择和构建
  validate_dataset.py          结构、数量、长度和校验和检查
  check_output.py              对单条模型输出运行 validator
  run_pipeline.py              完整流水线入口
src/p2w_bench/                 公共工具和输出 validators
METHODS_OVERVIEW.md            后续可选实验方法简表
DATA_SOURCES.md                公共数据来源、用途和许可证边界
DATA_SCHEMA.md                 全部配置、数据和 validator 字段说明
../DATASET_OPERATIONS.md       扩样、构建和排错操作手册
../DATASET_HANDOFF.md          架构、约束和维护交接说明
```

## 最终文件

- `queries_zh.jsonl`、`queries_en.jsonl`：分离的中英文 query。
- `prompt_groups.jsonl`：每组 prompt 的语义核心、事实和约束。
- `prompt_variants.jsonl`：三档长度的实际 prompt。
- `pairings.jsonl`：允许组合的 query 与 prompt，以及 gold answer/validator。
- `dataset.jsonl`：便于实验脚本读取的扁平版本，仍保持 `prompt` 和 `query` 为两个字段。
- `stats.json`：数据规模和来源分布。
- `sources.json`：实际下载来源、许可证说明和原始文件校验和。
- `build_manifest.json`：最终数据文件的大小与 SHA-256。
- `answer_verifiable.jsonl`：`gold_answers` 非空的答案可验证部分。
- `answer_nonverifiable.jsonl`：没有独立标准答案、主要与 full prompt 比较的部分。
- `answer_verifiability_manifest.json`：两部分的判定规则、数量和 SHA-256。

数据中不会出现 `full_input` 或 `full_prompt_output` 字段。

## 扩展数据集

增加指令数量时修改 `benchmark_config.json` 中的 `counts_per_language`，增加每条指令的查询数时修改 `queries_per_instruction`。如果模板和公共 query 池足够，构建脚本无需修改。完整步骤见 [DATASET_OPERATIONS.md](../DATASET_OPERATIONS.md)。

增加新的 prompt 类型时：

1. 在 `config/prompt_templates.json` 添加模板和 validator 描述。
2. 在 `build_dataset.py` 中注册新的 family 配额。
3. 在 `src/p2w_bench/output_validators.py` 添加对应验证逻辑。

增加新的公共来源时，在 `benchmark_config.json` 注册 URL，再为其增加标准化解析器。原始来源 ID、主页、许可证说明和 SHA-256 都会保留。

## 数据来源

- SQuAD：10 个英文知识 query。
- Databricks Dolly 15K：34 个英文描述与通用 query 分配记录。
- CMRC 2018：5 个简体中文知识 query。
- DRCD：5 个繁体中文知识 query。
- BELLE seed tasks：34 个中文描述与通用 query 分配记录；安全池共 26 个上游 query，允许不同指令复用，不允许同一指令内重复。
- 本项目合成：中英文各 2 个虚构或反事实知识 query。

完整来源、实际文件、构造边界和许可证说明见 [DATA_SOURCES.md](DATA_SOURCES.md)。其中 BELLE 的数据条款要求仅研究、非商业使用，不能用其代码仓库的 Apache-2.0 许可证替代。发布或再分发数据前，应重新核对各上游条款。`data/raw/download_manifest.json` 保存了本次实际下载文件的来源与校验和。

全部 JSON/JSONL 字段、文件关系和 validator 参数见 [DATA_SCHEMA.md](DATA_SCHEMA.md)。
