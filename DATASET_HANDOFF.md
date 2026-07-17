# 数据集代码交接说明

## 1. 目标与边界

当前代码只负责数据下载、筛选、指令构造、长度扩展、配对和结构验证，不生成模型输出，也不计算 KL、BLEU、ROUGE 或正确率。模型实验继续读取最终扁平 JSONL。

完整基准与答案可验证扩展集相互独立，但扩展集默认从完整基准的 `answer_verifiable.jsonl` 保留 24 条 short 样本。

## 2. 完整基准的数据模型

```text
PromptGroup（可复用指令） 1 ── N Query
PromptGroup              1 ── L PromptVariant
PromptVariant × 同组 Query ── Pairing
Pairing + 文本字段 ── dataset.jsonl
```

v0.2 的关键变化是删除 `prompt_groups.jsonl` 中的单个 `query_id`，改由每条 query 保存 `prompt_group_id`。因此描述性任务可以在不复制指令的情况下扩展多个查询。

主要不变量：

- 每个 query 只属于一个 prompt group。
- 每个 prompt group 至少有一个 query。
- 同一 prompt group 的 query 使用连续的 `query_index_within_group`。
- 每个 prompt group 恰有配置中全部长度 variant。
- Pairing 只展开同组的 `variant × query`。
- 知识 prompt 中必须保留至少一个 gold answer。

## 3. 代码职责

- `p2w_bench_dataset/scripts/download_sources.py`：下载与原始文件 manifest。
- `p2w_bench_dataset/scripts/build_dataset.py`：来源解析、选择、query/group 构造、variant/pairing 展开。
- `p2w_bench_dataset/scripts/split_by_answer_verifiability.py`：按 `gold_answers` 是否为空拆分。
- `p2w_bench_dataset/scripts/validate_dataset.py`：数量公式、外键、一对多关系、长度与校验和。
- `p2w_bench_dataset/scripts/run_pipeline.py`：可传目录的统一入口。
- `p2w_verifiable_expanded/scripts/build_dataset.py`：可验证来源下载、parser 分派、容量分析、稳定 ID 和最终合并。

模板由 `p2w_bench_dataset/config/prompt_templates.json` 管理。描述性模板已与其他 family 统一为 `{name, text, validator?}`，构建器仍兼容旧字符串格式。

## 4. 查询分配策略

英文 Dolly 池按任务类别轮转选择，并为四类输出控制保留适合的查询槽位。中文 BELLE 安全池只有 26 条单实例任务：构建器优先顺序确定，允许跨 prompt group 复用，但单组内不得超过 26 条。

这里的 `query_id` 表示“查询在某条指令下的评测分配”，不是上游问题的全局身份。跨版本追溯上游数据应使用 `source + source_id`；同一个上游问题被不同指令使用时会有不同 `query_id`。

## 5. 答案可验证扩展器

扩展器 v1.1 不再硬编码来源循环。`config.json` 的每个 source 带 `parser`，`parse_source()` 负责分派。选择时先保证不同 `source_group`，数量增大后可在同一上下文组选择不同 query，但规范化 query 永不重复。

新增公开样本的 query ID 使用 `language + source + SHA256(source, source_id)`，因此提高配额不会因为列表位置变化而重编号。`capacity_report.json` 是扩样前的主要检查依据。

## 6. 兼容性与下游影响

- 直接逐行读取 `dataset.jsonl` 的评测脚本无需改输入字段，但默认行数从 204 增为 276。
- 读取 `prompt_groups.jsonl.query_id` 的旧脚本必须改为从 query 按 `prompt_group_id` 反向分组。
- 旧的 `pair_id=pair--<variant_id>` 已变为包含 query ID；不要解析字符串，直接读取各 ID 字段。
- 答案可验证拆分仍有 72 行，因为知识任务仍是一组一个 query、三档长度。
- 描述性拆分现为 108 行，中英文各 54 行。

## 7. 验证基线

交接时已通过：

```text
完整流水线：68 groups / 92 queries / 204 variants / 276 pairings
答案可验证：72 rows
答案不可验证：204 rows
输出 validator 单元测试：5/5
扩展数据源容量扫描：5 个来源全部满足默认配额
```

标准复验命令见 `DATASET_OPERATIONS.md`。任何结构修改后至少运行完整流水线、`validate_dataset.py` 和单元测试。

## 8. 已知限制

- 中文开放查询池只有 26 条安全 BELLE seed tasks，较大规模实验应增加新的公开中文指令数据源。
- 近似 token 数不是 Qwen tokenizer 结果，只用于构建分桶。
- 冗余长度扩展依靠同义重复规则，不等于经过人工逐条语义验收。
- BELLE 数据条款为研究和非商业用途；再分发前需要重新核对所有上游许可证。
