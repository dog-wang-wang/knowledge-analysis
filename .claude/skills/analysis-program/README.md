# 更换为其他agent 的 skill 时的注意事项
1. scripts脚本中的config.properties 路径要更改为适合的路径（比如 android 本身的 skill 直接就是.skills 开头而不是.claude开头）
   - create_main的 `initProperties` 方法中的路径
   - scan_main的 `initProperties` 方法中的路径
2.