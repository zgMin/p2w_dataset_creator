# 数据来源与构造边界

本文档说明 P2W-Bench-ZHEN v0.3 中哪些内容来自公共数据、哪些内容由本项目构造，以及如何追溯每条样本。

## 来源总览

当前默认配置包含 68 个 prompt group 和 116 个 query 分配记录，其中 112 个使用公共查询，4 个为本项目构造的虚构或反事实知识样本。默认版本的实际数量如下：

| 来源 | 语言 | 使用部分 | 在本数据集中的用途 | 入选 query | 数据许可或使用条件 |
|---|---|---|---|---:|---|
| SQuAD 1.1 | 英文 | `dev-v1.1` | 英文知识 query、证据段落、gold answer | 10 | CC BY-SA 4.0 |
| Databricks Dolly 15K | 英文 | 完整公开 JSONL 中筛选 | 英文描述性和通用 query | 46 | CC BY-SA 3.0 |
| CMRC 2018 | 简体中文 | `dev`，SQuAD-style | 中文知识 query、证据段落、gold answer | 5 | CC BY-SA 4.0 |
| DRCD | 繁体中文 | `dev` | 中文知识 query、证据段落、gold answer | 5 | CC BY-SA 3.0 |
| BELLE 1.5M seed tasks | 中文 | 175 个 seed tasks | 中文描述性和通用 query 分配 | 46 | 仅研究、非商业使用，依其数据目录说明 |
| 本项目合成 | 中英文 | `config/synthetic_knowledge.json` | 虚构知识与反事实知识 | 4 | 本项目构造 |

这里的“入选 query”指指令组内的 query 分配记录；每个 query 会再配三个 prompt 长度版本。中文通用部分从 26 条安全 BELLE query 中分配，允许不同指令复用同一上游 query，因此上游唯一 query 数可能小于分配记录数。

## 各来源的具体处理

### SQuAD 1.1

- 上游主页：<https://rajpurkar.github.io/SQuAD-explorer/>
- 实际下载文件：`dev-v1.1.json`
- 本地文件：`data/raw/squad_dev_v1.1.json`
- 使用字段：article title、paragraph context、question、answers、question id。
- 构建方式：保留原始英文 question 和 gold answer；从 answer 所在段落截取短证据片段，作为知识 prompt 的事实部分。
- 未使用上游模型输出。

### Databricks Dolly 15K

- 上游仓库：<https://github.com/databrickslabs/dolly>
- 数据说明：<https://github.com/databrickslabs/dolly/blob/2305eb7f2f4b3beb2379f34c6addf335b46c4b43/data/README.md>
- 实际下载使用固定 commit `2305eb7f2f4b3beb2379f34c6addf335b46c4b43`，因为仓库当前主分支已将数据迁移至 Hugging Face。
- 本地文件：`data/raw/databricks_dolly_15k.jsonl`
- 使用字段：instruction、context、category。
- 构建方式：instruction 作为 query；若原记录带 context，则 context 保留在 query 一侧，并标为 `Task context`。项目构造的风格、格式或输出控制 prompt 不来自 Dolly。
- Dolly response 不作为 full-prompt 参考输出，也不会写入最终数据集。

### CMRC 2018

- 上游主页：<https://ymcui.com/cmrc2018/>
- 上游仓库：<https://github.com/ymcui/cmrc2018>
- 实际下载文件：`squad-style-data/cmrc2018_dev.json`
- 本地文件：`data/raw/cmrc2018_dev.json`
- 使用字段：title、context、question、answers、question id。
- 构建方式与 SQuAD 相同，提供简体中文知识 query、证据和 gold answer。

### DRCD

- 上游仓库：<https://github.com/DRCKnowledgeTeam/DRCD>
- 实际下载文件：`DRCD_dev.json`
- 本地文件：`data/raw/drcd_dev.json`
- 使用字段：title、context、question、answers、question id。
- DRCD 为繁体中文阅读理解数据。本版本保留原始繁体 query 和证据，不做简繁转换。
- 上游声明该数据整理、改编自维基百科，并按 CC BY-SA 3.0 发布。

### BELLE seed tasks

- 上游仓库：<https://github.com/LianjiaTech/BELLE>
- 数据目录说明：<https://github.com/LianjiaTech/BELLE/blob/main/data/1.5M/README.md>
- 实际下载文件：`data/1.5M/zh_seed_tasks.json`；文件内容采用 JSON Lines 结构。
- 本地文件：`data/raw/belle_zh_seed_tasks.jsonl`
- 使用字段：id、name、instruction、首个 instance input。
- 构建方式：instruction 与 instance input 组合成中文 query；上游 output 不写入最终数据集。
- 许可证注意：BELLE 仓库代码标注 Apache-2.0，但 `data/1.5M/README.md` 对数据和衍生物另行要求仅用于研究、不得商用。使用和再分发本数据集时应遵守数据专属条件。

### 本项目合成知识

- 文件：`config/synthetic_knowledge.json`
- 数量：中文 2 条、英文 2 条。
- 类型：虚构实体多跳关系、与现实常识冲突的测试设定。
- 目的：降低模型依赖预训练记忆即可答对的可能性。
- context、query 和 gold answer 都由本项目构造，不来自公共数据。

## Prompt 的来源

公共数据主要提供 query。Prompt 按任务族分为两种情况：

1. 知识问答 prompt：事实内容来自 SQuAD、CMRC、DRCD 的证据段落，或来自本项目合成知识；“仅依据资料回答”等外层指令由本项目构造。
2. 描述、风格、格式和输出控制 prompt：全部由本项目在 `config/prompt_templates.json` 中构造，不复制 Dolly 或 BELLE 的 prompt。

三档长度 prompt 均由确定性规则生成：

- `short`
- `medium_redundant`
- `long_redundant`

描述性 prompt 的三档文本在 `prompt_templates.json` 中人工编写：short 保留核心指令，medium 使用自然的助手角色和任务解释展开，long 进一步解释同一要求的含义和目标。它们不复制原句、不调用 LLM、不引入新的行为约束，也不使用公共数据中的 response。知识等其他任务仍可通过事实或要求的同义冗余扩写。

## 样本追溯

每条 query 保存：

- `source`：来源简称。
- `source_id`：上游 question id、seed task id 或固定 Dolly 行号。
- `source_category`：上游任务类别。
- `is_public_query`：是否来自公共来源。

下载时生成 `data/raw/download_manifest.json`，记录实际 URL、文件大小和 SHA-256。最终目录中的 `sources.json` 是该清单的副本，`build_manifest.json` 则记录最终 JSONL 文件的 SHA-256。

## 许可提醒

本文件记录的是上游项目在当前构建时公开展示的许可信息，不构成法律意见。尤其是 BELLE 数据具有非商业限制，因此当前聚合数据集不应被整体视为可自由商用。发布、共享或商用前应重新核对所有上游条款并保留必要署名。
