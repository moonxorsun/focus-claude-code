# Focus Plugin Troubleshooting

## Common Issues

### logs 目录未生成
- **Cause**: SKILL.md 中定义 hooks 无效，`os.getcwd()` 返回错误目录
- **Resolution**: 移动到 `hooks/hooks.json`，使用 `$CLAUDE_PROJECT_DIR` 环境变量

### hooks 未激活
- **Cause**: SKILL.md 中双引号未转义，YAML 解析时字符串被截断
- **Resolution**: `"$CLAUDE_PROJECT_DIR"` → `\"$CLAUDE_PROJECT_DIR\"`，所有 14 处已修复

### hooks 不触发
- **Cause**: SKILL.md frontmatter 中定义 hooks 无效
- **Resolution**: 移动到 `hooks/hooks.json`（官方标准结构）

### 错误日志难以定位代码位置
- **Cause**: 只记录函数名，不知道具体哪行代码抛异常
- **Resolution**: `_format_msg()` 自动获取 `file:line`，`error()` 自动附加 traceback
