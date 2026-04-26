#!/usr/bin/env kotlin
import java.io.File
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths
import java.util.Properties
import kotlin.io.path.fileSize
import kotlin.io.path.isDirectory
import kotlin.io.path.isRegularFile
import kotlin.io.path.listDirectoryEntries
import kotlin.io.path.name

// 配置的技能操作人的名字吧（我觉得不需要配置，但是我喜欢哆啦A梦，所以就加上了））
lateinit var skillHost: String
// 项目的名字
lateinit var projectName: String
// 分析结果根目录名称
lateinit var analysisRootName: String
// JSON target目录
lateinit var jsonDir: String
// JSON 文件名
lateinit var jsonFileName: String
// HTML target目录
lateinit var htmlDir: String
lateinit var htmlFileName: String
// 忽略目录（大仓库关键）
val ignoreDirs = setOf(
    ".git", "node_modules", ".idea",
    "build", "dist", ".gradle", "out"
)
safeRun {
    initProperties()
    scan()
}

// 初始化配置
fun initProperties() {
    // todo: 可更改项
    val props = Properties().apply { load(File(".opencode/skills/analysis-program/scripts/config.properties").reader(Charsets.UTF_8)) }
    skillHost = props.getProperty("skill.host")
    projectName = props.getProperty("project.name")
    analysisRootName = props.getProperty("struct.root")
    jsonDir = props.getProperty("struct.root.ai")
    jsonFileName = props.getProperty("struct.root.ai.scan")
    htmlDir = props.getProperty("struct.root.person")
    htmlFileName = props.getProperty("struct.root.person.scan")
}

fun scan() {
    val rootPath = Paths.get(".").toAbsolutePath().normalize()
    generateJsonFile(rootPath)
    generateHtmlFile(rootPath)
}

// 生成 json 结构的目录信息
fun generateJsonFile(rootPath: Path) {
    println("开始生成扫描文件的 Json 展示数据")
    val files = mutableListOf<FileInfo>()
    Files.walk(rootPath).use { stream ->
        stream.forEach { path ->
            if (!Files.isRegularFile(path)) return@forEach
            // 跳过隐藏/忽略目录
            if (path.any { it.toString() in ignoreDirs }) return@forEach
            val fileName = path.fileName.toString()
            val ext = fileName.substringAfterLast('.', "").ifEmpty { "(no_ext)" }
            val absolutePath = path.toAbsolutePath().toString()
            val relativePath = rootPath.relativize(path).toString()
            val fileInfo = FileInfo(absolutePath, relativePath, fileName, ext)
            files.add(fileInfo)
        }
    }
    val result = Result(rootPath.toString(), files)
    writeOutputFile(jsonDir, jsonFileName, FileType.JSON.type, toJson(result))
    print("✅JSON报告已生成")
}

// 生成 html 结构的目录信息
fun generateHtmlFile(rootPath: Path) {
    println("开始生成扫描文件的HTML展示数据")
    val stats = Stats()
    // 递归扫描并生成树状结构
    val dataTree = scan(rootPath, rootPath, stats)
    val totalSize = stats.extSizes.values.sum().coerceAtLeast(1L)
    val sortedExts = stats.extSizes.toList().sortedByDescending { it.second }.take(8)
    // 文件类型颜色映射
    val colors = mapOf(
        ".kt" to "#A97BFF", ".java" to "#b07219", ".xml" to "#0060ac", 
        ".js" to "#f7df1e", ".ts" to "#3178c6", ".py" to "#3776ab",
        ".json" to "#6b7280", ".md" to "#083fa1", ".html" to "#e34c26", ".css" to "#264de4"
    )

    // 侧边栏进度条
    val langBars = sortedExts.joinToString("") { (ext, size) ->
        val pct = (size.toDouble() / totalSize) * 100
        val color = colors[ext.lowercase()] ?: "#6b7280"
        """<div class="bar-row"><span class="bar-label">$ext</span>
           <div class="bar" style="width:$pct%;background:$color"></div>
           <span class="bar-pct">${"%.1f".format(pct)}%</span></div>"""
    }
    // 路径映射供 JS 使用
    val filePathsJson = stats.filePathsByExt.map { (ext, paths) ->
        "\"$ext\": ${paths.sorted().map { "\"$it\"" }}"
    }.joinToString(",", "{", "}")
    val htmlContent = """
<!DOCTYPE html>
<html><head>
  <meta charset="utf-8"><title>$projectName 代码地图</title>
  <style>
    body { font: 14px/1.5 system-ui, sans-serif; margin: 0; background: #1a1a2e; color: #eee; }
    .container { display: flex; height: 100vh; }
    .sidebar { width: 300px; background: #252542; padding: 20px; border-right: 1px solid #3d3d5c; overflow-y: auto; flex-shrink: 0; }
    .main { flex: 1; padding: 20px; overflow-y: auto; background: #0f0f1a; scroll-behavior: smooth; }
    h1 { margin: 0 0 15px 0; font-size: 20px; color: #fff; }
    h2 { margin: 25px 0 10px 0; font-size: 14px; color: #888; text-transform: uppercase; letter-spacing: 1px; }
    .stat { display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #3d3d5c; }
    .stat-value { font-weight: bold; color: #4db8ff; }
    .bar-row { display: flex; align-items: center; margin: 8px 0; }
    .bar-label { width: 65px; font-size: 12px; color: #aaa; overflow: hidden; text-overflow: ellipsis; }
    .bar { height: 12px; border-radius: 6px; }
    .bar-pct { margin-left: 10px; font-size: 11px; color: #777; width: 40px; text-align: right; }
    .tree { list-style: none; padding-left: 20px; margin-top: 5px; }
    details { cursor: pointer; margin-bottom: 2px; }
    summary { padding: 6px 10px; border-radius: 4px; outline: none; transition: background 0.2s; }
    summary:hover { background: #2d2d44; }
    .folder { color: #ffd700; font-weight: 500; }
    .file { display: flex; align-items: center; padding: 5px 10px; border-radius: 4px; transition: background 0.2s; }
    .file:hover { background: #2d2d44; }
    .size { color: #888; margin-left: auto; font-size: 11px; }
    .dot { width: 8px; height: 8px; border-radius: 50%; margin-right: 10px; display: inline-block; }
    .controls-panel { background: #1e1e35; padding: 15px; border-radius: 8px; border: 1px solid #3d3d5c; margin-bottom: 20px; display: flex; gap: 40px; align-items: center; }
    .switch-item { display: flex; align-items: center; gap: 12px; }
    .switch { position: relative; display: inline-block; width: 44px; height: 22px; }
    .switch input { opacity: 0; width: 0; height: 0; }
    .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #3d3d5c; transition: .4s; border-radius: 22px; }
    .slider:before { position: absolute; content: ""; height: 16px; width: 16px; left: 3px; bottom: 3px; background-color: white; transition: .4s; border-radius: 50%; }
    input:checked + .slider { background-color: #4db8ff; }
    input:checked + .slider:before { transform: translateX(22px); }
    .switch-label { font-size: 13px; font-weight: bold; color: #ccc; }
    .section-container { display: none; }
    .section-container.active { display: block; }
    .type-group { margin-bottom: 15px; background: #1e1e35; border-radius: 8px; overflow: hidden; border: 1px solid #3d3d5c; }
    .type-header { background: #2a2a4a; padding: 10px 15px; border-bottom: 1px solid #3d3d5c; display: block; }
    .path-list { list-style: none; padding: 10px 15px; margin: 0; max-height: 450px; overflow-y: auto; font-family: monospace; font-size: 12px; }
    .pkg-tree { padding-left: 15px; color: #aaa; border-left: 1px solid #3d3d5c; }
  </style>
</head><body>
  <div class="container">
    <div class="sidebar">
      <h1>📊 项目统计</h1>
      <div class="stat"><span>文件总数</span><span class="stat-value">${stats.files}</span></div>
      <div class="stat"><span>目录数量</span><span class="stat-value">${stats.dirs}</span></div>
      <div class="stat"><span>总大小</span><span class="stat-value">${formatSize(dataTree.size)}</span></div>
      <h2>类型分布 (Top 8)</h2>
      $langBars
    </div>
    <div class="main">
      <h1>🔍 视图控制</h1>
      <div class="controls-panel">
          <div class="switch-item">
              <span class="switch-label" id="viewLabel">视图: 分类浏览器</span>
              <label class="switch"><input type="checkbox" id="viewMode" onchange="applyFilters()"><span class="slider"></span></label>
          </div>
          <div class="switch-item" id="collapseSwitch">
              <span class="switch-label">全部折叠</span>
              <label class="switch"><input type="checkbox" id="toggleCollapse" onchange="applyFilters()" checked><span class="slider"></span></label>
          </div>
          <div class="switch-item" id="groupSwitch">
              <span class="switch-label">按包分类 (目录分组)</span>
              <label class="switch"><input type="checkbox" id="toggleGroup" onchange="applyFilters()"><span class="slider"></span></label>
          </div>
      </div>
      <div id="browserSection" class="section-container active">
        <h2>📂 分类浏览器</h2>
        <div id="typeDetailsContent"></div>
      </div>
      <div id="structureSection" class="section-container">
        <h2>🌳 项目结构树</h2>
        <ul class="tree" id="rootTree"></ul>
      </div>
    </div>
  </div>
  <script>
    const data = ${dataTree.toJson()};
    const colors = ${colors.entries.joinToString(",", "{", "}") { "\"${it.key}\":\"${it.value}\"" }};
    const filePathsByExt = $filePathsJson;

    function applyFilters() {
        const isStructureView = document.getElementById('viewMode').checked;
        const browserSection = document.getElementById('browserSection');
        const structureSection = document.getElementById('structureSection');
        const viewLabel = document.getElementById('viewLabel');
        
        if (isStructureView) {
            browserSection.classList.remove('active');
            structureSection.classList.add('active');
            document.getElementById('collapseSwitch').style.display = 'none';
            document.getElementById('groupSwitch').style.display = 'none';
            viewLabel.innerText = '视图: 项目结构';
        } else {
            browserSection.classList.add('active');
            structureSection.classList.remove('active');
            document.getElementById('collapseSwitch').style.display = 'flex';
            document.getElementById('groupSwitch').style.display = 'flex';
            viewLabel.innerText = '视图: 分类浏览器';
            renderBrowser();
        }
    }

    function renderBrowser() {
        const container = document.getElementById('typeDetailsContent');
        container.innerHTML = '';
        const isCollapsed = document.getElementById('toggleCollapse').checked;
        const isGrouped = document.getElementById('toggleGroup').checked;
        
        Object.keys(filePathsByExt).sort((a,b) => filePathsByExt[b].length - filePathsByExt[a].length).forEach(ext => {
            const paths = filePathsByExt[ext];
            const det = document.createElement('details');
            det.className = 'type-group';
            det.open = !isCollapsed;
            det.innerHTML = `<summary class="type-header"><span class="dot" style="background:${'$'}{colors[ext]||'#6b7280'}"></span>类型: ${'$'}{ext} (${'$'}{paths.length} 个文件)</summary>`;
            const content = document.createElement('div');
            if (isGrouped) {
                content.innerHTML = '<div class="path-list">' + renderTree(buildPathTree(paths)) + '</div>';
            } else {
                content.innerHTML = '<ul class="path-list">' + paths.map(p => `<li>${'$'}{p}</li>`).join('') + '</ul>';
            }
            det.appendChild(content);
            container.appendChild(det);
        });
    }

    function buildPathTree(paths) {
        const root = {};
        paths.forEach(p => {
            let curr = root;
            p.split('/').forEach((part, i, arr) => {
                if (!curr[part]) curr[part] = i === arr.length - 1 ? null : {};
                curr = curr[part];
            });
        });
        return root;
    }

    function renderTree(node) {
        let h = '<ul class="tree pkg-tree">';
        Object.keys(node).sort().forEach(k => {
            if (node[k] === null) h += `<li class="file">${'$'}{k}</li>`;
            else h += `<li><details><summary><span class="folder">📁 ${'$'}{k}</span></summary>${'$'}{renderTree(node[k])}</details></li>`;
        });
        return h + '</ul>';
    }

    function renderMainTree(node, parent, isRoot = false) {
      if (node.children) {
        const det = document.createElement('details');
        det.open = isRoot;
        det.innerHTML = `<summary><span class="folder">📁 ${'$'}{node.name}</span><span class="size">${'$'}{fmt(node.size)}</span></summary>`;
        const ul = document.createElement('ul'); ul.className = 'tree';
        node.children.sort((a,b) => (b.children?1:0)-(a.children?1:0) || a.name.localeCompare(b.name)).forEach(c => renderMainTree(c, ul));
        det.appendChild(ul);
        const li = document.createElement('li'); li.appendChild(det); parent.appendChild(li);
      } else {
        const li = document.createElement('li'); li.className = 'file';
        li.innerHTML = `<span class="dot" style="background:${'$'}{colors[node.ext]||'#6b7280'}"></span>${'$'}{node.name}<span class="size">${'$'}{fmt(node.size)}</span>`;
        parent.appendChild(li);
      }
    }
    function fmt(b) { return b < 1024 ? b+' B' : b < 1048576 ? (b/1024).toFixed(1)+' KB' : (b/1048576).toFixed(1)+' MB'; }

    // 初始化
    data.children.forEach(c => renderMainTree(c, document.getElementById('rootTree'), true));
    renderBrowser();
  </script>
</body></html>
    """.trimIndent()
    writeOutputFile(htmlDir, htmlFileName, FileType.HTML.type, htmlContent)
    println("✅HTML报告已生成")
}


fun esc(s: String) = s
    .replace("\\", "\\\\")
    .replace("\"", "\\\"")

/**
 * 文件结果转换为对象
 * @param result 文件结果
 */
fun toJson(result: Result): String {
    val sb = StringBuilder()

    sb.append("{")
    sb.append("\"root\":\"${esc(result.root)}\",")
    sb.append("\"files\":[")

    result.files.forEachIndexed { i, f ->
        sb.append("{")
        sb.append("\"absolutePath\":\"${esc(f.absolutePath)}\",")
        sb.append("\"relativePath\":\"${esc(f.relativePath)}\",")
        sb.append("\"fileName\":\"${esc(f.fileName)}\",")
        sb.append("\"extension\":\"${esc(f.extension)}\"")
        sb.append("}")
        if (i != result.files.lastIndex) sb.append(",")
    }

    sb.append("]}")
    return sb.toString()
}

/**
 * 递归扫描目录
 */
fun scan(path: Path, rootPath: Path, stats: Stats): Node {
    val children = mutableListOf<Node>()
    var totalSize = 0L
    path.listDirectoryEntries().sortedBy { it.name }.forEach { item ->
        val name = item.name
        // 过滤忽略名单和隐藏文件
        if (name in ignoreDirs || name.startsWith(".")) return@forEach
        if (item.isRegularFile()) {
            val size = item.fileSize()
            val ext = if (name.contains(".")) ".${name.substringAfterLast(".")}" else "(无扩展名)"
            val extLower = ext.lowercase()
            children.add(Node(name, size, extLower))
            totalSize += size
            // 更新统计数据
            stats.apply {
                files++
                extensions[ext] = stats.extensions.getOrDefault(ext, 0) + 1
                extSizes[ext] = stats.extSizes.getOrDefault(ext, 0L) + size
            }
            // 记录相对路径（统一使用正斜杠）
            val relativePath = rootPath.relativize(item).toString().replace("\\", "/")
            stats.filePathsByExt.getOrPut(extLower) { mutableListOf() }.add(relativePath)

        } else if (item.isDirectory()) {
            stats.dirs++
            val childNode = scan(item, rootPath, stats)
            if (!childNode.children.isNullOrEmpty() || childNode.size > 0) {
                children.add(childNode)
                totalSize += childNode.size
            }
        }
    }

    return Node(path.fileName?.toString() ?: "root", totalSize, children = children)
}

/**
 * 简单的 JSON 序列化（避免外部库依赖）
 */
fun Node.toJson(): String {
    val sb = StringBuilder()
    sb.append("""{"name":"$name","size":$size""")
    if (ext != null) sb.append(""","ext":"$ext"""")
    if (children != null) {
        sb.append(""","children":[""")
        sb.append(children.joinToString(",") { it.toJson() })
        sb.append("]")
    }
    sb.append("}")
    return sb.toString()
}

/**
 * 格式化文件大小
 */
fun formatSize(bytes: Long): String = when {
    bytes < 1024 -> "$bytes B"
    bytes < 1048576 -> "%.1f KB".format(bytes / 1024.0)
    else -> "%.1f MB".format(bytes / 1048576.0)
}

fun writeOutputFile(targetDir: String, name: String, type: String, content: String) {
    val file = createOutputFile(targetDir, name, type)
    file.parentFile.mkdirs()
    file.writeText(content)
}
// 创建文件输出目录
fun createOutputFile(targetDir: String, name: String, type: String) = File("$analysisRootName/$targetDir/$name.$type")

fun <T> safeRun(block: () -> T) {
    try {
        block()
    } catch (e: Exception) {
        print(e.message)
    }
}

sealed class FileType(val type: String) {
    object JSON : FileType("json")
    object HTML : FileType("html")
}

data class FileInfo(
    val absolutePath: String,
    val relativePath: String,
    val fileName: String,
    val extension: String
)

data class Result(
    val root: String,
    val files: List<FileInfo>
)

/**
 * 统计信息数据类
 */
data class Stats(
    var files: Int = 0, // 文件总数
    var dirs: Int = 0,  // 目录总数
    val extensions: MutableMap<String, Int> = mutableMapOf(), // 扩展名计数
    val extSizes: MutableMap<String, Long> = mutableMapOf(),   // 扩展名占用空间
    // 存储每个扩展名对应的所有文件路径列表
    val filePathsByExt: MutableMap<String, MutableList<String>> = mutableMapOf()
)

/**
 * 目录树节点数据类
 */
data class Node(
    val name: String,
    val size: Long,
    val ext: String? = null,
    val children: List<Node>? = null
)
