# Focus Plugin Conventions

## Testing
- 使用简单测试任务验证 plugin 基本功能，不涉及复杂业务逻辑

## Debugging
- 删除 `log_debug.json` 调试代码，日志系统已验证正常
- 暂不添加 debug 级别日志，info.log + error.log 已覆盖核心流程

## Configuration
- `decay_factor` / `min_session_budget` 可配置，方便用户调整 recover 预算分配策略

## Parallel Sessions
- 不支持同一目录多 session，可能损坏状态
- SessionStart 显示上次活动时间，用户自行判断
- 只提醒不阻止，无法可靠检测另一 session 是否在用
