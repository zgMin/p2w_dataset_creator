# Prompt-to-Weight Dataset Builders

本仓库提供面向 Prompt-to-Weight 方法的中英文评测数据构建代码。代码从公开数据源下载原始数据，完成查询筛选、指令构造、冗余长度扩展、一对多查询配对、答案可验证性拆分和结构校验。

仓库只包含可复现的构建代码、配置和文档。原始数据与生成结果由 `.gitignore` 排除，使用者在本地运行流水线生成。

## 项目组成

```text
prompt-to-weight-dataset-builders/
├── README.md
├── DATASET_OPERATIONS.md
├── DATASET_HANDOFF.md
├── .gitignore
├── p2w_bench_dataset/          # 中英文完整基准构建器
└── p2w_verifiable_expanded/    # 答案可验证扩展集构建器
```

完整基准默认包含 68 个指令组、92 个查询、204 个 prompt 变体和 276 个最终配对。描述性任务默认一条指令对应 3 个查询，可通过配置继续扩展。

## 快速开始

Python 3.9 或更新版本即可运行，不需要第三方依赖。

```bash
cd p2w_bench_dataset
python3 scripts/run_pipeline.py
```

构建答案可验证扩展集前，需要先生成上面的完整基准：

```bash
cd ../p2w_verifiable_expanded
python3 scripts/build_dataset.py --plan-only
python3 scripts/build_dataset.py
```

## 文档

- `DATASET_OPERATIONS.md`：构建、扩样、容量检查和测试命令。
- `DATASET_HANDOFF.md`：数据关系、代码职责、兼容性和维护说明。
- `p2w_bench_dataset/DATA_SCHEMA.md`：完整基准字段字典。
- `p2w_bench_dataset/DATA_SOURCES.md`：完整基准数据来源和许可证边界。
- `p2w_verifiable_expanded/DATA_SCHEMA.md`：扩展集字段字典。
- `p2w_verifiable_expanded/DATA_SOURCES.md`：扩展集数据来源。

## 上传 GitHub

在仓库根目录执行：

```bash
git init
git add .
git status
git commit -m "Initial dataset builder release"
git branch -M main
git remote add origin <your-repository-url>
git push -u origin main
```

提交前的 `git status` 不应包含 `data/raw`、`data/interim`、`data/final`、`outputs` 或 `work` 中的生成文件。

## 数据许可

构建器涉及 SQuAD、Dolly、CMRC2018、DRCD、BELLE、MRQA Natural Questions、TriviaQA 和 RelationExtraction。各来源条款不同，其中 BELLE 数据要求研究和非商业使用。使用、发布或再分发生成数据前，应以各上游最新许可证和数据条款为准。

