# Focus Plugin AI Norms

## Recover Flow Standardization

### Problem: recover 后 AI 行为不可控
- SKILL.md 只是指导性文档，AI 自由发挥

### Solution
- 脚本输出添加 `[REQUIRED]` 指令块，强制调用 AskUserQuestion
- 选项固定为 Continue/Complete/Restart/Cancel

## Two-Step Ask Flow (Scenario 2)

### When: 无 focus_context.md
1. 先问 Recover history/Start new/Cancel
2. 选择恢复后再问选哪个 Session
