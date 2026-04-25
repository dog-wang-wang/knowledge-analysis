#!/usr/bin/env kotlin
import java.io.File
import java.util.Properties

// 配置的技能操作人的名字吧（我觉得不需要配置，但是我喜欢哆啦A梦，所以就加上了））
lateinit var skillHost: String
// 项目的名字
lateinit var projectName: String
// 分析结果根目录名称
lateinit var analysisRootName: String
// JSON target目录
lateinit var jsonDir: String
// HTML target目录
lateinit var htmlDir: String

safeRun {
    initProperties()
    createOutputDir(skillHost, projectName)
}

// 初始化配置
fun initProperties() {
    // todo: 可更改项
    val props = Properties().apply { load(File(".skills/analysis-program/scripts/config.properties").reader(Charsets.UTF_8)) }
    skillHost = props.getProperty("skill.host")
    projectName = props.getProperty("project.name")
    analysisRootName = props.getProperty("struct.root")
    jsonDir = props.getProperty("struct.root.ai")
    htmlDir = props.getProperty("struct.root.person")
    println("初始化配置成功: $skillHost $projectName")
}

// 创建输出目录
fun createOutputDir(host: String, project: String) {
    println("$host 开始创建 $project 项目的相关分析文档输出目录")
    // 创建输出的根目录
    val root = mkdir(analysisRootName)
    // 创建json输出目录，给 ai 看
    mkdir("json", root.absolutePath)
    // 创建html输出目录，给人看
    mkdir("html", root.absolutePath)
}


fun mkdir(target: String, parent: String = "") : File {
    val dir = if (parent.isEmpty()) target else "$parent/$target"
    return File(dir).apply {
        val tips = "已经存在了$target"
        if (!exists()) mkdir() else println(tips)
    }
}

fun <T> safeRun(block: () -> T) {
    try {
        block()
    } catch (e: Exception) {
        print(e.message)
    }
}
