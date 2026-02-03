# Focus Plugin Tuning Guide

This document covers performance, token consumption, API costs, and configuration tuning.

---

## Context Injection Overview

Focus plugin injects context into AI through hooks. Each injection consumes tokens in the context window.

### Injection Points

| Hook | Trigger | Injection Content | Token Cost |
|------|---------|-------------------|------------|
| **Recite** | Every N searches (default: 3) | Task/Plan/Current Phase summary | ~100-300 |
| **Info Persistence** | Weight sum >= threshold (default: 5) | Short reminder + category suggestions | ~100 |
| **Full Info Reminder** | Every 30 minutes | Complete reminder with examples | ~200 |
| **Remind Update** | After Write/Edit/Bash | Short reminder + phase progress | ~20 |
| **Confirm Before Modify** | Before Write/Edit | Confirmation prompt | ~20 |
| **Session Start** | Session start | Unfinished session warning | ~50 |

### External API Costs (Haiku)

| Feature | Config | When Called | Haiku Tokens |
|---------|--------|-------------|--------------|
| Confirm Before Modify | `start.confirm_before_modify.use_haiku=true` | Each Write/Edit | ~50-100 |
| Omission Detection | `checkpoint.use_haiku=true` | /focus:checkpoint | ~500 |

**Note:** Haiku API calls require `ANTHROPIC_API_KEY` and `pip install anthropic`.

---

## Configuration Reference

### Frequency Control

| Config | Default | Effect | Trade-off |
|--------|---------|--------|-----------|
| `start.recite_threshold` | 3 | Recite every N searches | Higher = less context, more goal drift risk |
| `start.threshold` | 5 | Info Persistence trigger threshold | Higher = fewer reminders, more info loss risk |
| `start.full_reminder_interval_minutes` | 30 | Full reminder interval | Higher = fewer complete reminders |
| `start.max_strikes` | 3 | Max consecutive failures before forced stop | Higher = more tolerance for errors |

### Counter Behavior

| Counter | Storage | Trigger | Reset |
|---------|---------|---------|-------|
| Recite count | `action_count.json` | Every search tool | After reaching threshold |
| Info Persistence weight | `action_count.json` | Weighted by tool type | After reaching threshold |
| Full reminder timestamp | `action_count.json` | Time-based (30 min) | After showing full reminder |
| Strike count (per operation) | `failure_counts.json` | Same operation fails | After operation succeeds |

### Weight Configuration

Controls how quickly Info Persistence triggers:

```json
{
    "start": {
        "weights": {
            "Read": 1,
            "Glob": 1,
            "Grep": 1,
            "WebSearch": 2,
            "WebFetch": 2,
            "UserPrompt": 2
        }
    }
}
```

**Example:** With default weights:
- 5x Read = threshold (5)
- 2x WebSearch + 1x Read = threshold (5)
- 2x UserPrompt + 1x Glob = threshold (5)

### API Cost Control

| Config | Default | Description |
|--------|---------|-------------|
| `start.confirm_before_modify.enabled` | true | Enable/disable confirmation |
| `start.confirm_before_modify.use_haiku` | false | Use Haiku API for confirmation |
| `checkpoint.use_haiku` | false | Use Haiku API for omission detection |
| `checkpoint.haiku_max_tokens` | 500 | Max tokens for Haiku response |

### Recovery Budget

| Config | Default | Description |
|--------|---------|-------------|
| `recover.max_sessions` | 5 | Max sessions to recover |
| `recover.char_budget` | 50000 | Total character budget |
| `recover.decay_factor` | 0.5 | Exponential decay (newest gets 50%) |
| `recover.min_session_budget` | 1000 | Minimum chars per session |

---

## Tuning Strategies

### Minimal Token Consumption

For projects where context window is precious:

```json
{
    "start": {
        "recite_threshold": 5,
        "threshold": 8,
        "full_reminder_interval_minutes": 60,
        "confirm_before_modify": {
            "enabled": true,
            "use_haiku": false
        }
    }
}
```

### Maximum Guidance

For complex tasks requiring frequent reminders:

```json
{
    "start": {
        "recite_threshold": 2,
        "threshold": 3,
        "full_reminder_interval_minutes": 15
    }
}
```

### No External API

Avoid all Haiku API costs:

```json
{
    "start": {
        "confirm_before_modify": {
            "use_haiku": false
        }
    },
    "checkpoint": {
        "use_haiku": false
    }
}
```

### High-Value Recovery

For sessions with extensive history:

```json
{
    "recover": {
        "max_sessions": 10,
        "char_budget": 80000,
        "decay_factor": 0.6
    }
}
```

---

## Cost Summary

| Operation | Context Tokens | Haiku API | Config to Reduce |
|-----------|----------------|-----------|------------------|
| Normal session (per hour) | ~500-1000 | 0 | Increase thresholds |
| Write/Edit (with Haiku) | ~20 | ~50-100 | `use_haiku: false` |
| /focus:checkpoint | ~100 | 0-500 | `checkpoint.use_haiku: false` |
| /focus:recover | ~500-2000 | 0 | Reduce `char_budget` |
| /focus:done | ~200 | 0 | - |

---

## See Also

- [design.md](design.md) - Architecture and information flow
- [development.md](development.md) - Configuration system details
- [features.md](features.md) - Feature specifications
