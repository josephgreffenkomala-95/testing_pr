import copy
from datetime import datetime
from typing import List, Optional

from . import models
from .models import (
    TodoList,
    _VALID_PRIORITIES,
    _PRIORITY_ORDER,
    _ANSI_RESET,
    _ANSI_RED,
    _ANSI_YELLOW,
    _ANSI_GREEN,
    _ANSI_CYAN,
    _ANSI_BOLD,
    _ANSI_DIM,
    _ANSI_MAGENTA,
    _load_config,
    _push_undo,
)


def create_todo_list() -> TodoList:
    return []


def add_item(
    todo_list: TodoList,
    item: str,
    priority: Optional[str] = None,
    due: Optional[str] = None,
    tags: Optional[str] = None,
    max_length: int = 200,
) -> TodoList:
    config = _load_config()
    max_tasks = config.get("max_tasks", 1000)
    if len(todo_list) >= max_tasks:
        raise ValueError(f"Cannot exceed maximum of {max_tasks} tasks")
    stripped = item.strip()
    if not stripped:
        raise ValueError("Item must not be empty or whitespace-only")
    if len(stripped) > max_length:
        raise ValueError(f"Item exceeds maximum length of {max_length} characters")
    if priority is None:
        priority = config.get("default_priority", "medium")
    priority = priority.lower()
    if priority not in _VALID_PRIORITIES:
        raise ValueError(f"Priority must be one of {_VALID_PRIORITIES}")
    due_date = None
    if due is not None:
        try:
            due_date = datetime.strptime(due, "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError:
            raise ValueError("Due date must be in YYYY-MM-DD format")
    tag_list = []
    if tags is not None:
        tag_list = [t.strip().lower() for t in tags.split(",") if t.strip()]
        if len(tag_list) > 5:
            raise ValueError("Maximum 5 tags per item")
    item_id = models._next_id
    models._next_id += 1
    todo_list.append(
        {
            "id": item_id,
            "task": stripped,
            "done": False,
            "priority": priority,
            "due": due_date,
            "tags": tag_list,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
    )
    return todo_list


def edit_item(todo_list: TodoList, item_id: int, new_task: str, max_length: int = 200) -> bool:
    stripped = new_task.strip()
    if not stripped:
        raise ValueError("Item must not be empty or whitespace-only")
    if len(stripped) > max_length:
        raise ValueError(f"Item exceeds maximum length of {max_length} characters")
    for item in todo_list:
        if item["id"] == item_id:
            _push_undo(todo_list)
            item["task"] = stripped
            return True
    return False


def set_priority(todo_list: TodoList, item_id: int, priority: str) -> bool:
    priority = priority.lower()
    if priority not in _VALID_PRIORITIES:
        raise ValueError(f"Priority must be one of {_VALID_PRIORITIES}")
    for item in todo_list:
        if item["id"] == item_id:
            _push_undo(todo_list)
            item["priority"] = priority
            return True
    return False


def set_due(todo_list: TodoList, item_id: int, due: Optional[str]) -> bool:
    due_date = None
    if due is not None:
        try:
            due_date = datetime.strptime(due, "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError:
            raise ValueError("Due date must be in YYYY-MM-DD format")
    for item in todo_list:
        if item["id"] == item_id:
            _push_undo(todo_list)
            item["due"] = due_date
            return True
    return False


def set_tags(todo_list: TodoList, item_id: int, tags: str) -> bool:
    tag_list = [t.strip().lower() for t in tags.split(",") if t.strip()]
    if len(tag_list) > 5:
        raise ValueError("Maximum 5 tags per item")
    for item in todo_list:
        if item["id"] == item_id:
            _push_undo(todo_list)
            item["tags"] = tag_list
            return True
    return False


def mark_done(todo_list: TodoList, item_id: int) -> bool:
    for item in todo_list:
        if item["id"] == item_id:
            _push_undo(todo_list)
            item["done"] = True
            return True
    return False


def mark_undone(todo_list: TodoList, item_id: int) -> bool:
    for item in todo_list:
        if item["id"] == item_id:
            _push_undo(todo_list)
            item["done"] = False
            return True
    return False


def remove_item(todo_list: TodoList, item_id: int) -> bool:
    for i, item in enumerate(todo_list):
        if item["id"] == item_id:
            _push_undo(todo_list)
            todo_list.pop(i)
            return True
    return False


def clear_done(todo_list: TodoList) -> int:
    count = sum(1 for item in todo_list if item["done"])
    if count > 0:
        _push_undo(todo_list)
    todo_list[:] = [item for item in todo_list if not item["done"]]
    return count


def search_items(todo_list: TodoList, query: str, search_tags: bool = False) -> List[dict]:
    query_lower = query.lower()
    results = []
    for item in todo_list:
        if query_lower in item["task"].lower():
            results.append(item)
            continue
        if search_tags and "tags" in item:
            for tag in item["tags"]:
                if query_lower in tag:
                    results.append(item)
                    break
    return copy.deepcopy(results)


def list_items(
    todo_list: TodoList,
    filter_by: str = "all",
    sort_by: str = "id",
    tag_filter: Optional[str] = None,
    color: bool = True,
) -> None:
    if not todo_list:
        print("No items in the to-do list.")
        return

    filtered = todo_list
    if filter_by == "done":
        filtered = [i for i in todo_list if i["done"]]
    elif filter_by == "pending":
        filtered = [i for i in todo_list if not i["done"]]
    elif filter_by == "overdue":
        today = datetime.now().strftime("%Y-%m-%d")
        filtered = [
            i
            for i in todo_list
            if not i["done"] and i.get("due") and i["due"] < today
        ]

    if tag_filter is not None:
        tag_lower = tag_filter.lower()
        filtered = [i for i in filtered if tag_lower in [t.lower() for t in i.get("tags", [])]]

    if sort_by == "priority":
        filtered = sorted(filtered, key=lambda i: _PRIORITY_ORDER.get(i.get("priority", "medium"), 1))
    elif sort_by == "due":
        filtered = sorted(
            filtered,
            key=lambda i: i.get("due") or "9999-99-99",
        )
    elif sort_by == "status":
        filtered = sorted(filtered, key=lambda i: (i["done"], i["id"]))
    elif sort_by == "created":
        filtered = sorted(filtered, key=lambda i: i.get("created_at", ""), reverse=True)

    if not filtered:
        print("No matching items found.")
        return

    for item in filtered:
        status = "x" if item["done"] else " "
        priority = item.get("priority", "medium")
        due = item.get("due", "")
        created = item.get("created_at", "")
        tags = item.get("tags", [])

        priority_badge = f"[{priority[0].upper()}]" if priority else ""
        due_str = f" (due: {due})" if due else ""
        tag_str = f" {{{','.join(tags)}}}" if tags else ""

        line = f"  [{status}] {item['id']}: {item['task']} {priority_badge}{due_str}{tag_str}"
        if created:
            line += f"  {created}"

        if color:
            if item["done"]:
                print(f"{_ANSI_DIM}{line}{_ANSI_RESET}")
            elif priority == "high":
                print(f"{_ANSI_RED}{line}{_ANSI_RESET}")
            elif priority == "low":
                print(f"{_ANSI_CYAN}{line}{_ANSI_RESET}")
            elif tag_filter and tag_lower in [t.lower() for t in tags]:
                print(f"{_ANSI_MAGENTA}{line}{_ANSI_RESET}")
            else:
                print(line)
        else:
            print(line)


def stats(todo_list: TodoList) -> None:
    total = len(todo_list)
    done = sum(1 for i in todo_list if i["done"])
    pending = total - done
    overdue = 0
    today = datetime.now().strftime("%Y-%m-%d")
    for i in todo_list:
        if not i["done"] and i.get("due") and i["due"] < today:
            overdue += 1

    priority_counts = {"high": 0, "medium": 0, "low": 0}
    for i in todo_list:
        p = i.get("priority", "medium")
        if p in priority_counts:
            priority_counts[p] += 1

    all_tags = {}
    for i in todo_list:
        for t in i.get("tags", []):
            all_tags[t] = all_tags.get(t, 0) + 1

    print(f"{_ANSI_BOLD}To-Do Stats{_ANSI_RESET}")
    print(f"  Total:    {total}")
    print(f"  Done:     {_ANSI_GREEN}{done}{_ANSI_RESET}")
    print(f"  Pending:  {_ANSI_YELLOW}{pending}{_ANSI_RESET}")
    print(f"  Overdue:  {_ANSI_RED}{overdue}{_ANSI_RESET}")
    print(f"  High:     {_ANSI_RED}{priority_counts['high']}{_ANSI_RESET}  "
          f"Medium: {priority_counts['medium']}  "
          f"Low: {_ANSI_CYAN}{priority_counts['low']}{_ANSI_RESET}")
    if all_tags:
        print(f"  Tags:     {', '.join(f'{k}({v})' for k, v in sorted(all_tags.items()))}")
