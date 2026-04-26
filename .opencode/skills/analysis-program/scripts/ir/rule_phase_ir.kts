#!/usr/bin/env kotlin
import java.io.File
import java.time.Instant
import java.util.Properties

/**
 * Phase 3: 深度 IR 结构提取器 (高度结构化版)
 * 
 * 核心逻辑：
 * 1. 类封装：定义 IrParameter, IrFunction 等数据类，确保参数、函数、类均为对象结构。
 * 2. 精准解析：将函数参数从字符串解析为参数对象列表 (List<IrParameter>)。
 * 3. 结构化序列化：自定义递归 toJson 函数，支持深度嵌套的对象树转 JSON。
 */

// --- 1. IR 数据模型定义 ---

/**
 * 基础接口，定义如何转换为可序列化的 Map
 */
interface IrModel {
    fun toDataMap(): Map<String, Any?>
}

/**
 * 参数模型：包含参数名和类型
 */
data class IrParameter(
    val name: String,
    val type: String
) : IrModel {
    override fun toDataMap() = mapOf("name" to name, "type" to type)
}

/**
 * 元数据模型
 */
data class IrMeta(
    val source: String,
    val analyzer: String,
    val timestamp: String = Instant.now().toString()
) : IrModel {
    override fun toDataMap() = mapOf(
        "source" to source,
        "analyzer" to analyzer,
        "timestamp" to timestamp
    )
}

/**
 * 类/接口声明模型
 */
data class IrDeclaration(
    val name: String,
    val extends: List<String>
) : IrModel {
    override fun toDataMap() = mapOf("name" to name, "extends" to extends)
}

/**
 * 属性模型
 */
data class IrProperty(
    val name: String,
    val type: String,
    val modifier: String
) : IrModel {
    override fun toDataMap() = mapOf("name" to name, "type" to type, "modifier" to modifier)
}

/**
 * 函数模型：参数已改为 List<IrParameter>
 */
data class IrFunction(
    val name: String,
    val params: List<IrParameter>,
    val returnType: String,
    val modifier: String,
    val invocations: List<String>
) : IrModel {
    override fun toDataMap() = mapOf(
        "name" to name,
        "params" to params.map { it.toDataMap() },
        "returnType" to returnType,
        "modifier" to modifier,
        "invocations" to invocations
    )
}

/**
 * 类内部结构模型
 */
data class IrStructure(
    val declarations: List<IrDeclaration>,
    val properties: List<IrProperty>,
    val functions: List<IrFunction>
) : IrModel {
    override fun toDataMap() = mapOf(
        "declarations" to declarations.map { it.toDataMap() },
        "properties" to properties.map { it.toDataMap() },
        "functions" to functions.map { it.toDataMap() }
    )
}

/**
 * 统一的 JSON 序列化工具 (递归处理)
 */
fun Any?.toJson(): String = when (this) {
    null -> "null"
    is String -> "\"${this.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n").replace("\r", "")}\""
    is Number, is Boolean -> this.toString()
    is List<*> -> this.joinToString(", ", "[", "]") { it.toJson() }
    is Map<*, *> -> this.entries.joinToString(", ", "{", "}") {
        "\"${it.key}\": ${it.value.toJson()}"
    }

    is IrModel -> this.toDataMap().toJson()
    else -> "\"$this\""
}

// --- 2. 分析环境与工具配置 ---

val projectRoot = System.getProperty("user.dir") ?: "."
val props = Properties().apply {
    val configFile = File(projectRoot, ".opencode/.skills/analysis-program/scripts/config.properties")
    if (configFile.exists()) configFile.reader(Charsets.UTF_8).use { load(it) }
}

val analysisRootName = props.getProperty("struct.root", "哆啦A梦分析器的分析结果")
val irOutputDir = File(File(projectRoot, analysisRootName), "ir")
val detektJar = File(projectRoot, ".claude/.skills/analysis-program/scripts/ir/detekt-cli.jar")

fun runCommand(vararg command: String): String = try {
    ProcessBuilder(*command).redirectErrorStream(true).start().inputStream.bufferedReader().readText()
} catch (e: Exception) {
    ""
}

/**
 * 解析原始参数字符串为 IrParameter 列表
 */
fun parseParameters(rawParams: String): List<IrParameter> {
    if (rawParams.isBlank()) return emptyList()
    return rawParams.split(",").mapNotNull { part ->
        val segments = part.split(":").map { it.trim() }
        if (segments.size >= 2) {
            // 处理包含默认值的情况，如 "id: Int = 0"
            val paramType = segments[1].split("=")[0].trim()
            IrParameter(segments[0], paramType)
        } else if (segments.isNotEmpty() && segments[0].isNotBlank()) {
            IrParameter(segments[0], "Unknown")
        } else null
    }
}

// --- 3. 核心提取逻辑 ---

fun analyzeSourceCode(file: File, relPath: String, type: String): String {
    val content = file.readText()

    // 1. 获取 Findings (静态检查)
    val detektOutput = if (type == "kt") {
        runCommand("java", "-jar", detektJar.absolutePath, "--input", file.absolutePath, "--build-upon-default-config")
    } else ""
    val findings = detektOutput.lines().filter { it.isNotBlank() && it.contains(":") }.map { it.trim() }

    // 2. 提取基础信息
    val pkg = Regex("""package\s+([\w.]+)""").find(content)?.groupValues?.get(1) ?: "default"
    val imports = Regex("""import\s+([\w.*]+)""").findAll(content).map { it.groupValues[1] }.toList()

    val declarations = Regex("""(?m)^.*(?:class|interface|object|data\s+class|sealed\s+class)\s+(\w+)(?:\s*:\s*([\w.<>(), ]+))?""")
        .findAll(content).map { match ->
            val supers = match.groupValues.getOrNull(2)?.split(",")?.map { it.trim().split("(")[0] }?.filter { it.isNotEmpty() && it != "{" } ?: emptyList()
            IrDeclaration(match.groupValues[1], supers)
        }.toList()

    // 属性提取 (使用 Map 去重)
    val propertyMap = mutableMapOf<String, IrProperty>()
    Regex("""(?m)^\s*(private|internal|protected|public|override)?\s*(?:val|var)\s+(\w+)\s*:\s*([\w.<>?]+)""")
        .findAll(content).forEach { match ->
            val name = match.groupValues[2]
            propertyMap[name] = IrProperty(name, match.groupValues[3], match.groupValues[1].ifEmpty { "public" })
        }

    // 函数与调用点提取
    val functions =
        Regex("""(?m)^\s*(private|internal|protected|public|override)?\s*fun\s+(\w+)\s*\((.*?)\)\s*(?::\s*([\w.<>?]+))?\s*\{?([\s\S]*?)(?=^\s*fun|^\s*class|^\s*\}|\z)""")
            .findAll(content).map { match ->
                val rawParams = match.groupValues[3]
                val body = match.groupValues[5]

                // 提取调用点 (Invocations)
                val invocs = Regex("""(\w+)\(""").findAll(body)
                    .map { it.groupValues[1] }
                    .filter { it !in listOf("if", "for", "while", "when", "return", "let", "apply", "also", "run", "with") }
                    .distinct().toList()

                IrFunction(
                    name = match.groupValues[2],
                    params = parseParameters(rawParams),
                    returnType = match.groupValues[4].ifEmpty { "Unit" },
                    modifier = match.groupValues[1].ifEmpty { "public" },
                    invocations = invocs
                )
            }.toList()

    // 构造最终的结构化 Map 并序列化
    val result = mapOf(
        "meta" to IrMeta(relPath, if (type == "kt") "Detekt" else "Checkstyle").toDataMap(),
        "content" to mapOf(
            "package" to pkg,
            "imports" to imports,
            "structure" to IrStructure(declarations, propertyMap.values.toList(), functions).toDataMap()
        ),
        "analysis" to mapOf(
            "metrics" to mapOf("line_count" to content.lines().size, "issue_count" to findings.size),
            "findings" to findings
        )
    )

    return result.toJson()
}

fun analyzeXml(file: File, relPath: String): String {
    val content = file.readText()
    val rootTag = Regex("""<([\w.:]+)""").find(content)?.groupValues?.get(1) ?: "unknown"
    val defIds = Regex("""@\+id/(\w+)""").findAll(content).map { it.groupValues[1] }.distinct().toList()
    val usedIds = Regex("""@[^+][^/]+/(\w+)""").findAll(content).filter { !it.value.startsWith("@+") }.map { it.groupValues[1] }.distinct().toList()
    val resRefs = Regex("""[@\?][\w./:]+""").findAll(content).map { it.value }.distinct().toList()

    val result = mapOf(
        "meta" to IrMeta(relPath, "Mac-xmllint").toDataMap(),
        "content" to mapOf(
            "root_element" to rootTag,
            "defined_ids" to defIds,
            "used_ids" to usedIds,
            "referenced_resources" to resRefs
        )
    )
    return result.toJson()
}

// --- 4. 运行主逻辑 ---

fun main() {
    println("🚀 Phase 3: 启动深度结构化 IR 扫描 (参数对象化 + 调用链提取)...")
    if (!detektJar.exists()) {
        println("🚨 缺失工具包: ${detektJar.absolutePath}")
        return
    }
    if (!irOutputDir.exists()) irOutputDir.mkdirs()

    var count = 0
    File(projectRoot).walkTopDown()
        .onEnter { it.name !in setOf("build", ".gradle", ".git", ".idea", "node_modules", analysisRootName) }
        .forEach { file ->
            if (file.isFile) {
                val ext = file.extension.lowercase()
                if (ext == "kt" || ext == "java" || ext == "xml") {
                    val relPath = file.relativeTo(File(projectRoot)).path
                    val json = when (ext) {
                        "kt" -> analyzeSourceCode(file, relPath, "kt")
                        "java" -> analyzeSourceCode(file, relPath, "java")
                        "xml" -> analyzeXml(file, relPath)
                        else -> null
                    }
                    if (json != null) {
                        File(irOutputDir, "$relPath.ir.json").apply { parentFile.mkdirs(); writeText(json) }
                        count++
                    }
                }
            }
        }
    println("\n✨ 完成！已生成 $count 个高度结构化的 IR 碎片。")
}

main()
