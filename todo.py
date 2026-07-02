import json
import os
from datetime import datetime
from typing import List, Optional

TodoList = List[dict]

_next_id = 0
_DEFAULT_FILE = "todos.json"

_VALID_PRIORITIES = ("low", "medium", "high")
_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}

_ANSI_RESET = "\033[0m"
_ANSI_RED = "\033[91m"
_ANSI_YELLOW = "\033[93m"
_ANSI_GREEN = "\033[92m"
_ANSI_CYAN = "\033[96m"
_ANSI_BOLD = "\033[1m"
_ANSI_DIM = "\033[2m"


def create_todo_list() -> TodoList:
    return []


def add_item(
    todo_list: TodoList,
    item: str,
    priority: str = "medium",
    due: Optional[str] = None,
    max_length: int = 200,
) -> TodoList:
    global _next_id
    stripped = item.strip()
    if not stripped:
        raise ValueError("Item must not be empty or whitespace-only")
    if len(stripped) > max_length:
        raise ValueError(f"Item exceeds maximum length of {max_length} characters")
    priority = priority.lower()
    if priority not in _VALID_PRIORITIES:
        raise ValueError(f"Priority must be one of {_VALID_PRIORITIES}")
    due_date = None
    if due is not None:
        try:
            due_date = datetime.strptime(due, "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError:
            raise ValueError("Due date must be in YYYY-MM-DD format")
    todo_list.append(
        {
            "id": _next_id,
            "task": stripped,
            "done": False,
            "priority": priority,
            "due": due_date,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
    )
    _next_id += 1
    return todo_list


def edit_item(todo_list: TodoList, item_id: int, new_task: str) -> bool:
    if not new_task.strip():
        raise ValueError("Item must not be empty or whitespace-only")
    for item in todo_list:
        if item["id"] == item_id:
            item["task"] = new_task.strip()
            return True
    return False


def mark_done(todo_list: TodoList, item_id: int) -> bool:
    for item in todo_list:
        if item["id"] == item_id:
            item["done"] = True
            return True
    return False


def mark_undone(todo_list: TodoList, item_id: int) -> bool:
    for item in todo_list:
        if item["id"] == item_id:
            item["done"] = False
            return True
    return False


def remove_item(todo_list: TodoList, item_id: int) -> bool:
    for i, item in enumerate(todo_list):
        if item["id"] == item_id:
            todo_list.pop(i)
            return True
    return False


def clear_done(todo_list: TodoList) -> int:
    done_items = [item for item in todo_list if item["done"]]
    count = len(done_items)
    for item in done_items:
        todo_list.remove(item)
    return count


def search_items(todo_list: TodoList, query: str) -> List[dict]:
    query_lower = query.lower()
    return [item for item in todo_list if query_lower in item["task"].lower()]


def list_items(
    todo_list: TodoList,
    filter_by: str = "all",
    sort_by: str = "id",
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

    if sort_by == "priority":
        filtered = sorted(filtered, key=lambda i: _PRIORITY_ORDER.get(i.get("priority", "medium"), 1))
    elif sort_by == "due":
        filtered = sorted(
            filtered,
            key=lambda i: i.get("due") or "9999-99-99",
        )
    elif sort_by == "status":
        filtered = sorted(filtered, key=lambda i: (i["done"], i["id"]))

    if not filtered:
        print("No matching items found.")
        return

    for item in filtered:
        status = "x" if item["done"] else " "
        priority = item.get("priority", "medium")
        due = item.get("due", "")
        created = item.get("created_at", "")

        priority_badge = f"[{priority[0].upper()}]" if priority else ""
        due_str = f" (due: {due})" if due else ""

        line = f"  [{status}] {item['id']}: {item['task']} {priority_badge}{due_str}"
        if created:
            line += f"  {created}"

        if color:
            if item["done"]:
                print(f"{_ANSI_DIM}{line}{_ANSI_RESET}")
            elif priority == "high":
                print(f"{_ANSI_RED}{line}{_ANSI_RESET}")
            elif priority == "low":
                print(f"{_ANSI_CYAN}{line}{_ANSI_RESET}")
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

    print(f"{_ANSI_BOLD}To-Do Stats{_ANSI_RESET}")
    print(f"  Total:    {total}")
    print(f"  Done:     {_ANSI_GREEN}{done}{_ANSI_RESET}")
    print(f"  Pending:  {_ANSI_YELLOW}{pending}{_ANSI_RESET}")
    print(f"  Overdue:  {_ANSI_RED}{overdue}{_ANSI_RESET}")
    print(f"  High:     {_ANSI_RED}{priority_counts['high']}{_ANSI_RESET}  "
          f"Medium: {priority_counts['medium']}  "
          f"Low: {_ANSI_CYAN}{priority_counts['low']}{_ANSI_RESET}")


def save_todo_list(todo_list: TodoList, filepath: str = _DEFAULT_FILE) -> None:
    with open(filepath, "w") as f:
        json.dump(todo_list, f, indent=2)


def load_todo_list(filepath: str = _DEFAULT_FILE) -> TodoList:
    global _next_id
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r") as f:
        data = json.load(f)
    if data:
        _next_id = max(item["id"] for item in data) + 1
    return data


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

    sub.add_parser("list", help="List all tasks")

    ls_p = sub.add_parser("ls", help="List tasks with filtering and sorting")
    ls_p.add_argument("-f", "--filter", choices=["all", "done", "pending", "overdue"], default="all", help="Filter tasks")
    ls_p.add_argument("-s", "--sort", choices=["id", "priority", "due", "status"], default="id", help="Sort tasks")
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

    search_p = sub.add_parser("search", help="Search tasks by keyword")
    search_p.add_argument("query", help="Search keyword")

    sub.add_parser("stats", help="Show to-do list statistics")

    args = parser.parse_args()
    todos = load_todo_list()

    if args.command == "add":
        try:
            add_item(todos, args.task, priority=args.priority, due=args.due)
            save_todo_list(todos)
            due_str = f" (due: {args.due})" if args.due else ""
            print(f"Added: {args.task.strip()} [{args.priority}]{due_str}")
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
    elif args.command in ("list", "ls"):
        color = True
        filter_by = "all"
        sort_by = "id"
        if args.command == "ls":
            filter_by = args.filter
            sort_by = args.sort
            color = not args.no_color
        list_items(todos, filter_by=filter_by, sort_by=sort_by, color=color)
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
    elif args.command == "clear-done":
        count = clear_done(todos)
        save_todo_list(todos)
        print(f"Cleared {count} completed task(s).")
    elif args.command == "search":
        results = search_items(todos, args.query)
        if results:
            print(f"Found {len(results)} result(s):")
            list_items(results, color=True)
        else:
            print(f"No results for '{args.query}'.")
    elif args.command == "stats":
        stats(todos)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()