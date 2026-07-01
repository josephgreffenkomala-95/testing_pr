def create_todo_list():
    return []


def add_item(todo_list, item):
    todo_list.append({"task": item, "done": False})
    return todo_list


def mark_done(todo_list, index):
    if 0 <= index < len(todo_list):
        todo_list[index]["done"] = True
    return todo_list


def list_items(todo_list):
    if not todo_list:
        print("No items in the to-do list.")
        return
    for i, item in enumerate(todo_list):
        status = "x" if item["done"] else " "
        print(f"  [{status}] {i}: {item['task']}")


def remove_item(todo_list, index):
    if 0 <= index < len(todo_list):
        todo_list.pop(index)
    return todo_list


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
            list_items(todos)
            idx = input("Enter item number to mark done: ").strip()
            if idx.isdigit():
                mark_done(todos, int(idx))
                print("Item marked as done.")
        elif choice == "4":
            list_items(todos)
            idx = input("Enter item number to remove: ").strip()
            if idx.isdigit():
                remove_item(todos, int(idx))
                print("Item removed.")
        elif choice == "5":
            print("Goodbye!")
            break
        else:
            print("Invalid option.")