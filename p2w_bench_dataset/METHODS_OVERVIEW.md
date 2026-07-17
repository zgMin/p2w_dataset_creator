# Prompt-to-Weight 方法简表

本文档只记录后续实验可选择的方法，不在数据集构建阶段运行实验。

## 对照方法

### Full Prompt

直接输入 `C + x`，不修改模型权重。其 greedy 输出作为非唯一答案任务的主要一致性参考。

### Query Only

只输入 `x`，不提供 `C`，也不修改权重。用于观察移除 prompt 后的原始能力差距。

## 一次性权重方法

### Static Delta `Delta W(C)`

将同一上下文在若干 calibration queries 上产生的内部目标联合求解为一组闭式权重增量，再在其他查询上复用。用于测试跨查询的上下文参数化能力。

### Query-dependent Delta `Delta W(C, x)`

针对当前上下文和查询计算一次闭式权重增量。它能利用当前 query，但不能直接说明权重是否支持未见查询。

### QAvg

对若干 query/token dependent patch 做参数平均，得到一个可融合增量。该方法简单，但不同轨迹的更新可能相互抵消。

### QTraj

沿 full-prompt 的 teacher-forced 生成轨迹收集多个前缀约束，并通过一次联合岭回归求解同一组 `Delta W`。生成期间不重新计算参数。

### QTraj + Teacher-token

先用 QTraj 对齐内部状态，再使用闭式 `lm_head` 更新增强 full-prompt teacher token 的输出决策。目标形式包括 `topk_delta`、`margin` 和 `two_delta`。

## 动态分析方法

### Dynamic Per-token

每生成一个 token，按照当前前缀重新计算临时 `Delta W_t(C, x, y_<t)`。通常更接近论文中的 token-dependent patch，但不是一次融合权重。

### Dynamic Average

收集动态生成过程中的多个临时增量后求平均，再作为一次性权重使用。它用于分析动态更新能否压缩成静态参数，不应默认视为可靠方法。

## 融合检查

对声称可一次融合的方法，应同时保存 factorized patch 和物理融合模型，并验证融合前后的 logits 在数值误差范围内一致。运行 weight-only 条件时，只输入 query，不得保留 prompt、anchor、stop token 提示或其他运行时约束。
