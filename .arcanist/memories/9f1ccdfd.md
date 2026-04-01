---
id: mem-9f1ccdfd
type: gotcha
context_hint: When implementing periodic tasks with retry logic, especially those that fan out to multiple recipients
referenced_files:
  - src/bot.py
  - src/task_manager.py
source_pr_url: https://github.com/Varun901/TaskList-Discord-Bot/pull/9
source_session_id: 49599d49-4da3-4c60-ad75-617b81ef0997
---

When using a sentinel/flag variable to prevent re-execution of a periodic task (e.g., a daily digest), always set the flag AFTER the operation succeeds, not before. If the flag is set before the async operation and the operation fails, the task won't retry. Additionally, when the task involves multiple recipients, the top-level success flag alone isn't enough — you also need per-recipient tracking (a set of successfully-delivered user IDs) so that retries skip already-delivered recipients and avoid duplicates. The per-recipient set should be cleared once per calendar day, independent of the retry cycle.
