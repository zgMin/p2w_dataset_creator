# 扩展版答案可验证数据集

本目录构建单跳、短答案、可自动验证的 prompt-to-weight 测试集。默认保留原数据集的 24 条 short 样本，并加入 72 条公开样本；数量均可通过配置扩展，不生成 prompt 长度变体。

## 构成

| 语言 | 来源 | 数量 | 上下文类型 |
|---|---|---:|---|
| 英文 | 原 short 集（SQuAD/合成） | 12 | 百科段落或受控事实 |
| 英文 | Natural Questions (MRQA) | 12 | Wikipedia 答案段落 |
| 英文 | TriviaQA (MRQA) | 12 | Web 答案段落 |
| 英文 | RelationExtraction (MRQA) | 12 | Wikipedia 关系事实段落 |
| 中文 | 原 short 集（CMRC/DRCD/合成） | 12 | 百科段落或受控事实 |
| 中文 | CMRC2018 | 18 | 中文百科段落 |
| 中文 | DRCD | 18 | 中文百科段落 |

总计 96 条，中英文各 48 条。MRQA 子集自带段落内 detected answer span；构建器围绕该 span 截取单段上下文，并排除显式多答案问法。因此这里测的是上下文知识参数化，不测多跳推理。

## 构建

```bash
python scripts/build_dataset.py
```

只检查各来源可用容量而不生成最终数据：

```bash
python scripts/build_dataset.py --plan-only
```

脚本会下载缺失原始文件，固定使用 `seed=20260715` 筛选，输出：

- `data/final/answer_verifiable_expanded.jsonl`：最终评测集。
- `data/final/stats.json`：语言与来源统计。
- `data/final/source_manifest.json`：下载 URL、许可证说明和 SHA-256。
- `data/final/capacity_report.json`：每个来源的有效行数、唯一查询数、上下文组数、请求数和实际选择数。

原 24 条样本默认来自相邻目录 `p2w_bench_dataset/data/final/answer_verifiable.jsonl`。可用 `--base-dataset` 指定同结构文件。

扩样时修改 `config.json` 的 `base_rows.limit` 和 `additional_counts`，然后先运行 `--plan-only`。数据源由各自的 `parser` 字段驱动，不需要再修改主循环。完整操作见 [DATASET_OPERATIONS.md](../DATASET_OPERATIONS.md)，维护说明见 [DATASET_HANDOFF.md](../DATASET_HANDOFF.md)。

## 评测协议

格式指令不是知识上下文的一部分，而是四种方法共享的输出协议：

```text
Return exactly one XML element: <answer>answer text</answer>.
```

中文使用等价中文指令。这样可以稳定抽取答案，又不会把标签遵循能力混入知识参数化正确率。Full prompt 输入为 `knowledge_prompt + query_with_protocol`；Base 输入为 `query_with_protocol`；两种 QTraj 方法拟合 `knowledge_prompt` 对同一个 `query_with_protocol` 的影响。

## 远程评测

- 服务器：`A6000`
- Conda 环境：`thoughtpatch-qwen25`
- 工作目录：`/root/zgm/thoughtpatch_qwen25`
- 模型：`/root/zgm/e2pse/models/Qwen2.5-3B-Instruct`

单卡命令如下；多卡时设置 `--num-shards 4`，分别运行 `--shard-index 0..3`：

```bash
cd /root/zgm/thoughtpatch_qwen25
/root/anaconda3/envs/thoughtpatch-qwen25/bin/python \
  src/eval_verifiable_expanded.py \
  --dataset data/verifiable_expanded/answer_verifiable_expanded.jsonl \
  --out outputs/verifiable_expanded_all/shard0.json \
  --device cuda:0 --shard-index 0 --num-shards 4
```

汇总命令：

```bash
/root/anaconda3/envs/thoughtpatch-qwen25/bin/python \
  src/summarize_verifiable_expanded.py \
  --inputs outputs/verifiable_expanded_all/shard0.json \
           outputs/verifiable_expanded_all/shard1.json \
           outputs/verifiable_expanded_all/shard2.json \
           outputs/verifiable_expanded_all/shard3.json \
  --out-dir outputs/verifiable_expanded_all/report \
  --expected-rows 96
```
