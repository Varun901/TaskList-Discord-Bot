---
id: mem-9f1ccdfd
type: gotcha
context_hint: When implementing periodic/scheduled tasks with deduplication guards (e.g., 'only run once per day' patterns using date stamps or boolean flags)
referenced_files:
  - src/bot.py
source_pr_url: https://github.com/Varun901/TaskList-Discord-Bot/pull/9
source_session_id: 49599d49-4da3-4c60-ad75-617b81ef0997
---

When using a sentinel/flag variable to prevent re-execution of a periodic task (e.g., a daily digest), always set the flag AFTER the operation succeeds, not before. If the flag is set before the async operation and the operation throws, the flag incorrectly marks the work as done, preventing any retry for the remainder of the guard period. Wrap the operation in try/except and only update the sentinel on success. On failure, log the error and let the next loop iteration retry naturally.
