#!/usr/bin/env python
"""
Root-level entry point for the TaskList bot.

Allows the bot to be launched as:

    python bot.py

from the project root, which matches the systemd ExecStart line:

    ExecStart=/home/ubuntu/TaskList-Discord-Bot/venv/bin/python bot.py

when WorkingDirectory is set to the project root (/home/ubuntu/TaskList-Discord-Bot).

Adds src/ to sys.path so all internal imports (config, database, …) resolve
correctly, then runs src/bot.py as __main__.
"""
from __future__ import annotations

import os
import sys
import runpy

_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

runpy.run_path(os.path.join(_src, "bot.py"), run_name="__main__")
