---
description: Recover context from previous sessions. Use when Claude's session restore fails or when resuming work after interruption.
---

**IMPORTANT: Execute the command below EXACTLY as written. Do NOT modify the path or use alternative commands.**

Run the recovery script to restore context:

```bash
python "{{FOCUS_PLUGIN_ROOT}}/scripts/recover_context.py"
```

After the script runs, follow its [REQUIRED] instructions exactly - use AskUserQuestion with the options specified in the output.
