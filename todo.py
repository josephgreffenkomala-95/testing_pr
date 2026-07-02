import copy
import json
import os
import csv
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
    global _next_id
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
    todo_list.append(
        {
            "id": _next_id,
            "task": stripped,
            "done": False,
            "priority": priority,
            "due": due_date,
            "tags": tag_list,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
    )
    _next_id += 1
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


def save_todo_list(todo_list: TodoList, filepath: str = _DEFAULT_FILE) -> None:
    with open(filepath, "w") as f:
        json.dump(todo_list, f, indent=2)


def load_todo_list(filepath: str = _DEFAULT_FILE) -> TodoList:
    global _next_id
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
        _next_id = max(item["id"] for item in validated) + 1
    return validated


def main():
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="todo", description="Feature-rich to-do list CLI"
    )
    sub = parser.add_subparsers(dest="command")

    add_p = sub.add_parser("add", help="Add a new task")
    add_p.add_argument("task", help="Task description")
    add_p.add_argument("-p", "--priority", choices=_VALID_PRIORITIES, default="medium", help="Task priority (default: medium)")
    add_p.add_argument("-d", "--due", help="Due date in YYYY-MM-DD format")
    add_p.add_argument("-t", "--tags", help="Comma-separated tags (max 5)")

    list_p = sub.add_parser("list", help="List all tasks")
    list_p.add_argument("--no-color", action="store_true", help="Disable colored output")

    ls_p = sub.add_parser("ls", help="List tasks with filtering and sorting")
    ls_p.add_argument("-f", "--filter", choices=["all", "done", "pending", "overdue"], default="all", help="Filter tasks")
    ls_p.add_argument("-s", "--sort", choices=["id", "priority", "due", "status", "created"], default="id", help="Sort tasks")
    ls_p.add_argument("-t", "--tag", help="Filter by tag")
    ls_p.add_argument("--no-color", action="store_true", help="Disable colored output")

    done_p = sub.add_parser("done", help="Mark a task as done")
    done_p.add_argument("id", type=int, help="Task ID to mark done")

    undone_p = sub.add_parser("undone", help="Mark a task as pending again")
    undone_p.add_argument("id", type=int, help="Task ID to mark as pending")

    rm_p = sub.add_parser("remove", help="Remove a task")
    rm_p.add_argument("id", type=int, help="Task ID to remove")

    sub.add_parser("clear-done", help="Remove all completed tasks")

    edit_p = sub.add_parser("edit", help="Edit a task description")
    edit_p.add_argument("id", type=int, help="Task ID to edit")
    edit_p.add_argument("task", help="New task description")

    priority_p = sub.add_parser("priority", help="Set task priority")
    priority_p.add_argument("id", type=int, help="Task ID")
    priority_p.add_argument("priority", choices=_VALID_PRIORITIES, help="New priority")

    due_p = sub.add_parser("due", help="Set or remove due date")
    due_p.add_argument("id", type=int, help="Task ID")
    due_p.add_argument("date", nargs="?", default=None, help="Due date (YYYY-MM-DD) or omit to clear")

    tag_p = sub.add_parser("tag", help="Set tags on a task")
    tag_p.add_argument("id", type=int, help="Task ID")
    tag_p.add_argument("tags", help="Comma-separated tags (max 5)")

    search_p = sub.add_parser("search", help="Search tasks by keyword")
    search_p.add_argument("query", help="Search keyword")
    search_p.add_argument("--tags", action="store_true", help="Also search in tags")

    sub.add_parser("stats", help="Show to-do list statistics")

    export_p = sub.add_parser("export", help="Export todo list to file")
    export_p.add_argument("filepath", help="Output file path")
    export_p.add_argument("-f", "--format", choices=["csv", "txt", "json"], default="csv", help="Export format")

    sub.add_parser("undo", help="Undo last change")

    args = parser.parse_args()
    todos = load_todo_list()

    if args.command == "add":
        try:
            add_item(todos, args.task, priority=args.priority, due=args.due, tags=args.tags)
            save_todo_list(todos)
            due_str = f" (due: {args.due})" if args.due else ""
            tag_str = f" [{args.tags}]" if args.tags else ""
            print(f"Added: {args.task.strip()} [{args.priority}]{due_str}{tag_str}")
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
    elif args.command in ("list", "ls"):
        color = True
        filter_by = "all"
        sort_by = "id"
        tag_filter = None
        if args.command == "ls":
            filter_by = args.filter
            sort_by = args.sort
            color = not args.no_color
            tag_filter = args.tag
        elif args.command == "list":
            color = not args.no_color
        list_items(todos, filter_by=filter_by, sort_by=sort_by, tag_filter=tag_filter, color=color)
    elif args.command == "done":
        if mark_done(todos, args.id):
            save_todo_list(todos)
            print(f"Marked {args.id} as done.")
        else:
            print(f"Error: No item with ID {args.id}")
            sys.exit(1)
    elif args.command == "undone":
        if mark_undone(todos, args.id):
            save_todo_list(todos)
            print(f"Marked {args.id} as pending.")
        else:
            print(f"Error: No item with ID {args.id}")
            sys.exit(1)
    elif args.command == "remove":
        if remove_item(todos, args.id):
            save_todo_list(todos)
            print(f"Removed item {args.id}.")
        else:
            print(f"Error: No item with ID {args.id}")
            sys.exit(1)
    elif args.command == "edit":
        try:
            if edit_item(todos, args.id, args.task):
                save_todo_list(todos)
                print(f"Updated item {args.id}: {args.task.strip()}")
            else:
                print(f"Error: No item with ID {args.id}")
                sys.exit(1)
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
    elif args.command == "priority":
        try:
            if set_priority(todos, args.id, args.priority):
                save_todo_list(todos)
                print(f"Set priority of {args.id} to {args.priority}.")
            else:
                print(f"Error: No item with ID {args.id}")
                sys.exit(1)
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
    elif args.command == "due":
        try:
            if set_due(todos, args.id, args.date):
                save_todo_list(todos)
                print(f"Set due date of {args.id} to {args.date}.")
            else:
                print(f"Error: No item with ID {args.id}")
                sys.exit(1)
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
    elif args.command == "tag":
        try:
            if set_tags(todos, args.id, args.tags):
                save_todo_list(todos)
                print(f"Set tags of {args.id} to: {args.tags}.")
            else:
                print(f"Error: No item with ID {args.id}")
                sys.exit(1)
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
    elif args.command == "clear-done":
        count = clear_done(todos)
        save_todo_list(todos)
        print(f"Cleared {count} completed task(s).")
    elif args.command == "search":
        results = search_items(todos, args.query, search_tags=args.tags)
        if results:
            print(f"Found {len(results)} result(s):")
            list_items(results, color=True)
        else:
            print(f"No results for '{args.query}'.")
    elif args.command == "stats":
        stats(todos)
    elif args.command == "export":
        try:
            export_todo_list(todos, args.filepath, fmt=args.format)
            print(f"Exported {len(todos)} item(s) to {args.filepath} ({args.format}).")
        except (ValueError, OSError) as e:
            print(f"Error: {e}")
            sys.exit(1)
    elif args.command == "undo":
        if undo(todos):
            save_todo_list(todos)
            print("Undone last action.")
        else:
            print("Nothing to undo.")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
