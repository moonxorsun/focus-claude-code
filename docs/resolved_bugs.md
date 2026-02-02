# Focus Plugin Resolved Bugs

## Windows Encoding
### Stop hook UnicodeEncodeError
- **Cause**: Windows GBK 编码无法处理 emoji（⚠️✅🚨）
- **Resolution**: 替换为 ASCII：`[!]` `[OK]` `[!!!]`

## File Operations
### JSON 文件损坏
- **Cause**: 非原子写入，进程中断导致文件截断/清空
- **Resolution**: 添加 `atomic_write_json()` 使用 temp+rename 模式

## API Integration
### check_user_confirmation 错误缺少上下文
- **Cause**: 异常只记录 error，无法定位 API 返回内容
- **Resolution**: 添加 `result_text` 初始化，error 日志包含 API 返回值

### check_user_confirmation JSON 解析失败
- **Cause**: API 响应被截断或 Markdown 包装，`rfind("}")` 返回 -1 导致空字符串
- **Resolution**: 改用 YES/NO 响应 + 字符串搜索，彻底避免 JSON 解析问题

## Logging
### recover/extract 脚本无日志输出
- **Cause**: `main()` 中未重载 CONFIG，使用插件默认配置而非项目配置
- **Resolution**: 添加 `global CONFIG` + `CONFIG = load_config(project_path)`

## Session Recovery
### recover/done 只读取当前会话
- **Cause**: `find_transcript_path()` 只返回最新的一个会话文件
- **Resolution**: 从 operations.jsonl 提取所有 session_id，遍历所有相关会话

### commands/recover.md 没调用脚本
- **Cause**: skill 文件只有一句话 "Invoke the skill"，没有执行指令
- **Resolution**: 添加 `python "$CLAUDE_PLUGIN_ROOT/scripts/..."` 脚本调用

### load_operations 参数错误
- **Cause**: 传入 project_path（目录）而非 OPERATIONS_FILE（文件路径）
- **Resolution**: 修改为 `load_operations(OPERATIONS_FILE, logger)`

### read_stdin_data JSON 解析失败
- **Cause**: Claude Code 传入的大型 JSON 被截断或包含非法字符
- **Resolution**: 添加 `extract_key_fields()` 正则回退，降级为 debug 日志

### checkpoint stdout 关闭错误
- **Cause**: `io.TextIOWrapper` 包装 stdout 导致 I/O closed
- **Resolution**: 改用 `os.environ.setdefault('PYTHONIOENCODING', 'utf-8')`

### checkpoint logger 未初始化
- **Cause**: `generate_summary()` 使用模块级 logger，未被调用方初始化
- **Resolution**: 添加 `extract_session_info.logger = logger` 共享 logger

### recover 包含噪音内容
- **Cause**: `<command-name>` 等 XML 标签和 tool_result 未过滤
- **Resolution**: 新增 `_is_noise_content()` 过滤噪音，保留自然对话

### recover 恢复当前 session
- **Cause**: 当前 session 已在 AI 上下文中，恢复是冗余的
- **Resolution**: 跳过当前 session（从 operations 获取 session_id 过滤）

### recover 旧日志残留
- **Cause**: 新 recover 只生成 6 个文件，旧的 10-19 残留
- **Resolution**: 写入前清理 `dual_session_*.log`

### recover 预算显示错误
- **Cause**: `total remaining` 按显示顺序计算，数值含义混乱
- **Resolution**: 保存处理时的 `remaining_budget`，显示正确的剩余预算

### $CLAUDE_PLUGIN_ROOT undefined
- **Cause**: commands/skills 中环境变量未定义，AI 执行 bash 报错
- **Resolution**: SessionStart 时写入 `focus_plugin_root.txt`，commands 用 `$(cat ...)` 读取
