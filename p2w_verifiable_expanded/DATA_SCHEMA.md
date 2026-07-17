# 字段说明

最终文件为 `data/final/answer_verifiable_expanded.jsonl`，每行是一个独立 JSON 对象。

| 字段 | 类型 | 含义 |
|---|---|---|
| `pair_id` | string | 当前 prompt-query 配对的唯一 ID。 |
| `query_id` | string | 查询唯一 ID；新增公开样本由 `language + source + 上游ID哈希` 组成，扩样时已有 ID 不漂移。 |
| `prompt_variant_id` | string | Prompt 版本 ID；当前固定以 `--single` 结尾。 |
| `language` | `zh` / `en` | 查询与上下文语言。 |
| `task_family` | string | 当前固定为 `knowledge`。 |
| `subtype` | string | 知识任务子类，当前为公开抽取式或原受控事实。 |
| `length_variant` | string | 当前固定为 `single`，不比较 prompt 长度。 |
| `source` | string | 数据来源，如 `natural_questions`、`cmrc2018`。 |
| `source_id` | string | 上游数据中的问题 ID。 |
| `source_title` | string | 上游标题；来源不提供标题时为空字符串。 |
| `dataset_partition` | string | `base_short` 表示保留的原 24 条；`expanded_public` 表示新增公开样本。 |
| `prompt` | string | 待转换为权重的知识上下文，不包含共享输出格式协议。 |
| `query` | string | 原始查询，不包含共享输出格式协议。 |
| `gold_answers` | array[string] | 段落内检测出的正确答案 span；多个值是可接受别名或等价 span。 |
| `is_public_query` | boolean | 查询是否来自公开数据；4 条原受控事实为 `false`。 |

`capacity_report.json` 中每个来源包含 `eligible_rows`、`unique_queries`、`unique_context_groups`、`requested` 和 `selected`。构建器优先选择不同上下文组；数量较大时允许同一上下文组出现多个不同问题，但不会重复规范化后的 query。

## 运行时字段

评测结果在上述字段之外增加：

| 字段 | 含义 |
|---|---|
| `evaluation_query` | `query` 与共享 `<answer>` 输出协议拼接后的实际 query-only 输入。 |
| `format_protocol` | 当前语言的共享输出协议。四种方法完全相同。 |
| `outputs` | Base、Full prompt、QTraj + Teacher-token、QTraj + Top-k 的 greedy 输出。 |
| `teacher_output` | QTraj 拟合时由 Full prompt 路径生成的 teacher trajectory。 |
| `timing_seconds` | QTraj、两类 teacher anchor 与样本总耗时。 |
| `constraint_counts` | 两类 teacher-token 闭式回归实际采用的 token 约束数。 |
| `metrics` | 汇总脚本追加的严格格式、标签抽取、EM、F1、包含率。 |

共享格式协议不属于待转换的知识参数。Full prompt 为 `prompt + evaluation_query`，Base 与两种参数化生成路径只输入 `evaluation_query`。因此正确率差异主要反映知识上下文是否被权重更新保留。
