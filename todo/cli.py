import argparse
import curses
import sys

from .models import _VALID_PRIORITIES, undo
from .core import (
    add_item,
    edit_item,
    mark_done,
    mark_undone,
    remove_item,
    clear_done,
    search_items,
    set_priority,
    set_due,
    set_tags,
    list_items,
    stats,
)
from .io import save_todo_list, load_todo_list, export_todo_list
from .tui import run_tui


def main():
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

    sub.add_parser("tui", help="Open an interactive terminal UI")

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
    elif args.command == "tui":
        try:
            if run_tui(todos):
                save_todo_list(todos)
        except curses.error as e:
            print(f"Error: {e}")
            sys.exit(1)
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
