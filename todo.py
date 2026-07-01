import json
import os
from typing import List

TodoList = List[dict]

_next_id = 0
_DEFAULT_FILE = "todos.json"


def create_todo_list() -> TodoList:
    """Create and return a new empty to-do list."""
    return []


def add_item(todo_list: TodoList, item: str, max_length: int = 200) -> TodoList:
    """Add a new task to the to-do list and return the list.

    Strips leading/trailing whitespace. Raises ValueError if the resulting
    string is empty or exceeds max_length.
    """
    global _next_id
    stripped = item.strip()
    if not stripped:
        raise ValueError("Item must not be empty or whitespace-only")
    if len(stripped) > max_length:
        raise ValueError(f"Item exceeds maximum length of {max_length} characters")
    todo_list.append({"id": _next_id, "task": stripped, "done": False})
    _next_id += 1
    return todo_list


def mark_done(todo_list: TodoList, item_id: int) -> bool:
    """Mark the item with the given id as done.

    Returns True if the item was found and marked, False otherwise.
    """
    for item in todo_list:
        if item["id"] == item_id:
            item["done"] = True
            return True
    return False


def list_items(todo_list: TodoList) -> None:
    """Print all items in the to-do list to stdout."""
    if not todo_list:
        print("No items in the to-do list.")
        return
    for item in todo_list:
        status = "x" if item["done"] else " "
        print(f"  [{status}] {item['id']}: {item['task']}")


def remove_item(todo_list: TodoList, item_id: int) -> bool:
    """Remove the item with the given id.

    Returns True if the item was removed, False otherwise.
    """
    for i, item in enumerate(todo_list):
        if item["id"] == item_id:
            todo_list.pop(i)
            return True
    return False


def save_todo_list(todo_list: TodoList, filepath: str = _DEFAULT_FILE) -> None:
    """Save the to-do list to a JSON file."""
    with open(filepath, "w") as f:
        json.dump(todo_list, f, indent=2)


def load_todo_list(filepath: str = _DEFAULT_FILE) -> TodoList:
    """Load the to-do list from a JSON file.

    Returns an empty list if the file does not exist.
    """
    global _next_id
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r") as f:
        data = json.load(f)
    if data:
        _next_id = max(item["id"] for item in data) + 1
    return data


if __name__ == "__main__":
    todos = load_todo_list()

    while True:
        print("\n--- To-Do List ---")
        print("1. Add item")
        print("2. List items")
        print("3. Mark item done")
        print("4. Remove item")
        print("5. Quit")
        choice = input("Choose an option: ").strip()

        if choice == "1":
            task = input("Enter task: ").strip()
            try:
                add_item(todos, task)
                save_todo_list(todos)
                print(f"Added: {task}")
            except ValueError as e:
                print(f"Error: {e}")
        elif choice == "2":
            list_items(todos)
        elif choice == "3":
            if not todos:
                print("No items in the to-do list.")
                continue
            list_items(todos)
            raw = input("Enter item ID to mark done: ").strip()
            if raw.isdigit():
                if mark_done(todos, int(raw)):
                    save_todo_list(todos)
                    print("Item marked as done.")
                else:
                    print("Invalid item ID.")
            else:
                print("Invalid input.")
        elif choice == "4":
            if not todos:
                print("No items in the to-do list.")
                continue
            list_items(todos)
            raw = input("Enter item ID to remove: ").strip()
            if raw.isdigit():
                if remove_item(todos, int(raw)):
                    save_todo_list(todos)
                    print("Item removed.")
                else:
                    print("Invalid item ID.")
            else:
                print("Invalid input.")
        elif choice == "5":
            save_todo_list(todos)
            print("Goodbye!")
            break
        else:
            print("Invalid option.")