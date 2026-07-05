import json
import os
from datetime import datetime
from typing import List, Optional

TodoList = List[dict]

_next_id = 0
_DEFAULT_FILE = "todos.json"
_UNDO_STACKS = {}
_UNDO_MAX = 50

_VALID_PRIORITIES = ("low", "medium", "high")
_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}

_ANSI_RESET = "\033[0m"
_ANSI_RED = "\033[91m"
_ANSI_YELLOW = "\033[93m"
_ANSI_GREEN = "\033[92m"
_ANSI_CYAN = "\033[96m"
_ANSI_BOLD = "\033[1m"
_ANSI_DIM = "\033[2m"
_ANSI_MAGENTA = "\033[95m"

_DEFAULT_CONFIG = {
    "default_priority": "medium",
    "max_tasks": 1000,
    "sort_newest_first": False,
}

_cached_config = None


def _load_config():
    global _cached_config
    if _cached_config is not None:
        return _cached_config.copy()
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".todorc")
    config = _DEFAULT_CONFIG.copy()
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            user_config = json.load(f)
        config.update(user_config)
    _cached_config = config
    return config.copy()


def _get_undo_stack(todo_list):
    list_id = id(todo_list)
    if list_id not in _UNDO_STACKS:
        _UNDO_STACKS[list_id] = []
    return _UNDO_STACKS[list_id]


def _push_undo(todo_list):
    stack = _get_undo_stack(todo_list)
    snapshot = json.loads(json.dumps(todo_list))
    stack.append(snapshot)
    if len(stack) > _UNDO_MAX:
        _UNDO_STACKS[id(todo_list)] = stack[-_UNDO_MAX:]


def undo(todo_list: TodoList) -> bool:
    global _next_id
    stack = _get_undo_stack(todo_list)
    if not stack:
        return False
    prev = stack.pop()
    todo_list.clear()
    for item in prev:
        todo_list.append(item)
    if todo_list:
        _next_id = max(item["id"] for item in todo_list) + 1
    else:
        _next_id = 0
    return True
