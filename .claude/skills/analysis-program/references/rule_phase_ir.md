# Phase 3: IR 结构提取 (执行指南)

本阶段核心任务：利用专业工具（Detekt/Checkstyle）对源码进行深度静态扫描，生成标准化的 `.ir.json`。

### 1. 工具存放目录
请确保工具存放在以下路径中：
`项目根目录/.claude/skills/analysis-program/scripts/ir/`

### 2. 检查工具是否存在
请确认以下文件已就绪：
- `detekt-cli.jar` (Kotlin 分析器)
- `checkstyle.jar` (Java 分析器)

### 3. 下载缺失工具 (仅在上述文件不存在时执行)
如果在终端运行脚本提示工具缺失，请复制以下命令进行下载：

```bash
# 创建目录
mkdir -p ./.claude/skills/analysis-program/scripts/ir

# 下载 Detekt CLI (Kotlin)
curl -L https://github.com/detekt/detekt/releases/download/v1.23.1/detekt-cli-1.23.1-all.jar -o ./.claude/skills/analysis-program/scripts/ir/detekt-cli.jar

# 下载 Checkstyle (Java)
curl -L https://github.com/checkstyle/checkstyle/releases/download/checkstyle-10.12.3/checkstyle-10.12.3-all.jar -o ./.claude/skills/analysis-program/scripts/ir/checkstyle.jar
```

## 1. 执行分析
环境确认无误后，在项目根目录下执行：
```bash
kotlin ./.claude/skills/analysis-program/scripts/ir/rule_phase_ir.kts
```
