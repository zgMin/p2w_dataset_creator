# 数据集构建操作手册

本文覆盖两个构建目录：`p2w_bench_dataset` 负责中英文完整基准，`p2w_verifiable_expanded` 负责可继续扩量的答案可验证子集。

## 1. 完整基准

### 1.1 默认构建

```bash
cd /Users/mac/Documents/Codex/2026-07-06/you/p2w_bench_dataset
python3 scripts/run_pipeline.py
```

已有原始数据时可跳过下载：

```bash
python3 scripts/run_pipeline.py --skip-download
```

输出位于 `data/final`。流水线依次执行下载、构建、按答案可验证性拆分和结构校验。自定义目录示例：

```bash
python3 scripts/run_pipeline.py \
  --config benchmark_config.json \
  --raw-dir /tmp/p2w/raw \
  --interim-dir /tmp/p2w/interim \
  --output-dir /tmp/p2w/final
```

### 1.2 扩展一条指令的查询数

修改 `benchmark_config.json`：

```json
"queries_per_instruction": {
  "knowledge": 1,
  "descriptive": 5,
  "style": 1,
  "format": 1,
  "output_control": 1
}
```

`descriptive=5` 表示每种语言的每条描述性指令分配 5 个查询。Prompt group 和 prompt variant 不会复制；`pairings.jsonl` 会展开该组每个长度 variant 与 5 个查询的组合。

中文通用查询来自 26 条经过筛选的 BELLE seed tasks。不同指令可以复用同一个上游 query，同一指令内保持不同。单条中文指令需要超过 26 个查询时，构建器会停止并要求先扩充查询来源。

### 1.3 扩展指令数量

1. 在 `config/prompt_templates.json` 对应 family 和语言下增加带稳定 `name` 的模板。
2. 增加 `benchmark_config.json` 的 `counts_per_language.<family>`。
3. 运行完整流水线和校验。

`counts_per_language` 对非知识 family 表示指令数，不表示最终 query 数。知识任务仍由 `knowledge_public` 和 `knowledge_synthetic` 控制。

### 1.4 规模计算

对单种语言，设：

- `K = knowledge_public + knowledge_synthetic`
- `I_f = counts_per_language[f]`
- `Q_f = queries_per_instruction[f]`
- `L = length_variants` 的档位数

则：

```text
prompt_group 数 = K + sum_f I_f
query 数        = K + sum_f (I_f * Q_f)
prompt_variant 数 = prompt_group 数 * L
pairing 数      = query 数 * L
```

默认每种语言为 34 个 group、46 个 query、102 个 prompt variant 和 138 个最终 pairing；中英文合计 68/92/204/276。

### 1.5 测试与检查

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 scripts/validate_dataset.py
```

结构校验会验证一对多归属、组内 query 序号、同组 variant 完整性、组内笛卡尔积、长度范围、gold answer 未被截掉以及文件校验和。

## 2. 答案可验证扩展集

### 2.1 默认构建

```bash
cd /Users/mac/Documents/Codex/2026-07-06/you/p2w_verifiable_expanded
python3 scripts/build_dataset.py
```

原始文件已下载时使用：

```bash
python3 scripts/build_dataset.py --no-download
```

### 2.2 修改样本数量

编辑 `config.json`：

```json
"base_rows": {
  "length_variant": "short",
  "limit": 24
},
"additional_counts": {
  "natural_questions": 100,
  "triviaqa": 100,
  "relation_extraction": 100,
  "cmrc2018": 100,
  "drcd": 100
}
```

`base_rows.limit=null` 表示保留指定长度档位的全部基础样本。某来源设为 `0` 会跳过下载和解析。改数量后先运行：

```bash
python3 scripts/build_dataset.py --plan-only
```

默认筛选条件下，本次容量报告中的唯一查询上限约为：Natural Questions 3,754、TriviaQA 6,653、RelationExtraction 2,111、CMRC2018 3,180、DRCD 3,518。筛选阈值或原始文件变化后应以新的 `capacity_report.json` 为准。

### 2.3 增加数据源

在 `config.json` 同时增加 `additional_counts` 和 `sources` 项。现有解析器：

- `mrqa`：MRQA JSONL gzip。
- `squad_zh`：中文 SQuAD 风格 JSON。

新格式需要在 `scripts/build_dataset.py` 增加解析函数，并在 `parse_source()` 注册 parser 名称。标准化行必须包含 `source`、`source_id`、`source_group`、`language`、`query`、`context`、`gold_answers` 和 `is_public_query`。

## 3. 扩样后的实验注意事项

- 实验读取 `dataset.jsonl` 或拆分后的扁平 JSONL，不要自行对全体 prompt 和 query 做笛卡尔积。
- 描述性任务按 `prompt_group_id` 汇总时，可以比较同一参数化指令在多个 query 上的均值和方差。
- 扩样后旧的固定行数参数需要同步更新，例如远程汇总脚本的 `--expected-rows`。
- 固定 `seed` 可复现选择；新增来源或改变某来源配额不会改变扩展集中已有公开样本的稳定 query ID，但可能改变被抽中的样本集合。
