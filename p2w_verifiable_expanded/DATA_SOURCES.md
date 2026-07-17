# 数据来源

## MRQA 2019：Natural Questions、TriviaQA、RelationExtraction

- 本项目使用 MRQA 2019 官方 dev 文件。
- Natural Questions：真实搜索查询与 Wikipedia 答案段落。
- TriviaQA：Trivia/quiz 问题与 Web 答案段落。
- RelationExtraction：关系查询与 Wikipedia 事实段落。
- 主页：https://mrqa.github.io/2019/shared

MRQA 将多套公开 QA 数据统一为 extractive 格式，并提供 `detected_answers` 段落内 span。本构建仅保留短答案能直接出现在单个上下文中的样本，不使用 HotpotQA。

## CMRC2018

- 简体中文机器阅读理解数据集，SQuAD 风格。
- 主页：https://github.com/ymcui/cmrc2018
- 许可证：CC BY-SA 4.0。

## DRCD

- 繁体中文阅读理解数据集，SQuAD 风格。
- 主页：https://github.com/DRCKnowledgeTeam/DRCD
- 许可证：CC BY-SA 3.0。

## 原 short 集

保留 `p2w_bench_dataset` 中每个 query 的 `short` 版本，共 24 条。其公开来源为 SQuAD、CMRC2018 与 DRCD，另有 4 条受控合成知识。保留这些条目是为了与此前实验直接对照。
