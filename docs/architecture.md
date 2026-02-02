# Focus Plugin Architecture

## Core Findings

### Information Persistence Reminder
- `action_count.json` 累加到 5 后重置，证明触发成功

### Transcript Structure
- `tool_use` 在 `assistant.message.content[]`
- `tool_result` 在 `user.message.content[]`

### is_error Field Reliability
- 只有用户拒绝操作时 Claude Code 才设置 `is_error=True`，避免误检

### Category System
- 分类系统扩展为 10 个：bugs/resolved_bugs 区分，新增 external_knowledge/techniques/decisions/config

### Code Reuse
- 三个脚本 30-40% 代码重复，提取公共模块 `focus_core.py`

### Recover Budget Allocation
- 指数衰减分配：最近 session 50%，依次递减，未用预算累积

### SessionStart Hook
- 移入 `hooks/hooks.json`，插件安装后自动生效

### Environment Variables
- 使用 `$CLAUDE_PLUGIN_ROOT` 读取 config.json
- 官方标准环境变量，与 hooks.json 保持一致，回退到 `__file__` 支持手动调试

### Output Messages
- 统一使用 `output_message(tag, msg)` 处理所有 AI 注入消息

### API Response Format
- API 响应改为 YES/NO，字符串搜索更健壮

### Logging
- 日志添加文件行号+traceback
- 使用 `inspect.currentframe()` 获取调用位置

### Token Limits
- `max_tokens` 改为 50，YES/NO 响应只需 1-2 tokens

### Plugin Root Discovery
- 使用 `focus_plugin_root.txt` 文件，环境变量只在 hooks 上下文有效
