import csv
import json
import os

from . import models
from .models import TodoList, _DEFAULT_FILE


def save_todo_list(todo_list: TodoList, filepath: str = _DEFAULT_FILE) -> None:
    with open(filepath, "w") as f:
        json.dump(todo_list, f, indent=2)


def load_todo_list(filepath: str = _DEFAULT_FILE) -> TodoList:
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r") as f:
        data = json.load(f)
    _REQUIRED_KEYS = {"id", "task", "done"}
    validated = []
    for item in data:
        if not isinstance(item, dict) or not _REQUIRED_KEYS.issubset(item):
            continue
        item.setdefault("priority", "medium")
        item.setdefault("due", None)
        item.setdefault("created_at", "")
        item.setdefault("tags", [])
        validated.append(item)
    if validated:
        models._next_id = max(item["id"] for item in validated) + 1
    return validated


def export_todo_list(todo_list: TodoList, filepath: str, fmt: str = "csv") -> None:
    abs_path = os.path.abspath(filepath)
    if not abs_path.startswith(os.getcwd()):
        raise ValueError("Export path must be within the current working directory")
    if fmt == "csv":
        with open(filepath, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "task", "done", "priority", "due", "tags", "created_at"])
            for item in todo_list:
                writer.writerow([
                    item["id"],
                    item["task"],
                    item["done"],
                    item.get("priority", "medium"),
                    item.get("due", ""),
                    ",".join(item.get("tags", [])),
                    item.get("created_at", ""),
                ])
    elif fmt == "txt":
        with open(filepath, "w") as f:
            for item in todo_list:
                status = "DONE" if item["done"] else "TODO"
                tags = ",".join(item.get("tags", []))
                f.write(f"[{status}] {item['id']}: {item['task']} | priority={item.get('priority', 'medium')} | due={item.get('due', 'none')} | tags={tags}\n")
    elif fmt == "json":
        with open(filepath, "w") as f:
            json.dump(todo_list, f, indent=2)
    else:
        raise ValueError(f"Unknown export format: {fmt}. Supported: csv, txt, json")
