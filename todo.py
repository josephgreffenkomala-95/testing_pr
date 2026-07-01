from typing import List, Optional

TodoList = List[dict]


def create_todo_list() -> TodoList:
    """Create and return a new empty to-do list."""
    return []


def add_item(todo_list: TodoList, item: str) -> TodoList:
    """Add a new task to the to-do list and return the list."""
    todo_list.append({"task": item, "done": False})
    return todo_list


def mark_done(todo_list: TodoList, index: int) -> bool:
    """Mark the item at the given index as done.

    Returns True if the item was found and marked, False otherwise.
    """
    if 0 <= index < len(todo_list):
        todo_list[index]["done"] = True
        return True
    return False


def list_items(todo_list: TodoList) -> None:
    """Print all items in the to-do list to stdout."""
    if not todo_list:
        print("No items in the to-do list.")
        return
    for i, item in enumerate(todo_list):
        status = "x" if item["done"] else " "
        print(f"  [{status}] {i}: {item['task']}")


def remove_item(todo_list: TodoList, index: int) -> bool:
    """Remove the item at the given index.

    Returns True if the item was removed, False otherwise.
    """
    if 0 <= index < len(todo_list):
        todo_list.pop(index)
        return True
    return False


if __name__ == "__main__":
    todos = create_todo_list()

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
            if task:
                add_item(todos, task)
                print(f"Added: {task}")
        elif choice == "2":
            list_items(todos)
        elif choice == "3":
            if not todos:
                print("No items in the to-do list.")
                continue
            list_items(todos)
            idx = input("Enter item number to mark done: ").strip()
            if idx.isdigit():
                if mark_done(todos, int(idx)):
                    print("Item marked as done.")
                else:
                    print("Invalid item number.")
            else:
                print("Invalid input.")
        elif choice == "4":
            if not todos:
                print("No items in the to-do list.")
                continue
            list_items(todos)
            idx = input("Enter item number to remove: ").strip()
            if idx.isdigit():
                if remove_item(todos, int(idx)):
                    print("Item removed.")
                else:
                    print("Invalid item number.")
            else:
                print("Invalid input.")
        elif choice == "5":
            print("Goodbye!")
            break
        else:
            print("Invalid option.")