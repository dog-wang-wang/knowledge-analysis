---
name: analysis-program
description: 项目分析与理解
---
# 1. Skill目标
本 Skill 用于将大型多语言代码库转换为结构化知识图谱，包括：
- 统一中间表示（IR）
- 全局依赖图（Graph）
- 调用链（Call Chain）
- 功能模块（Module）

最终目标：
> 将“代码仓库”转换为“可计算的结构化图系统”
# 2. 核心原则
## 2.1 结构唯一性原则
所有语言必须统一转换为 IR，不允许语言差异污染结构。
## 2.2 禁止幻觉原则
禁止：
- 编造类
- 编造方法
- 编造调用关系

未知内容必须标记：
```json id="unknown"
{
  "unknown": true
}
```
## 2.3 显式关系原则
所有依赖必须显式表达，不允许隐式推断。
## 2.4 输出语言
输出的语言是中文，不说英文
# 3. 执行Workflow
## 3.1 Phase 1 → 创建分析文档输出目录
执行时参考[rule_phase_create_output.md](references/rule_phase_create_output.md)
## 3.2 Phase 2 → 文件扫描 
执行时参考[rule_phase_scan.md](references/rule_phase_scan.md)
## 3.3 Phase 3 -> 文件分析
执行时参考[rule_phase_analysis](references/rule_phase_analysis_file.md)
## 3.3 Phase 3 → 项目功能分析
扫描所有代码，分析项目的功能模块到一个文档中并保存至项目的根目录下
## 3.4 Phase 4 → 项目原理 + 技术介绍
分析项目的实现原理以及所使用的技术，并提供入手点，将该文档输出至项目根目录