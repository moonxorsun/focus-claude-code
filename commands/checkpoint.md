---
description: Save progress mid-session without ending the focus session. Archives findings, truncates logs, but keeps focus_context.md active.
---

**IMPORTANT: Execute the command below EXACTLY as written. Do NOT modify the path or use alternative commands.**

Run the checkpoint script to save progress:

```bash
python "{{FOCUS_PLUGIN_ROOT}}/scripts/checkpoint_session.py"
```

After the script runs, follow the SKILL.md instructions at `skills/checkpoint/SKILL.md` to:
1. Archive valuable findings/issues to documentation
2. Update focus_context.md (remove archived items)
3. Optionally commit the checkpoint
