# testing_pr

A simple Python project with greeting, farewell, and to-do list utilities.

## Usage

### To-Do List

```python
from todo import create_todo_list, add_item, mark_done, list_items, remove_item

todos = create_todo_list()
add_item(todos, "Buy groceries")  # returns item with id=0
add_item(todos, "Read a book")    # returns item with id=1
mark_done(todos, 0)               # 0 is the unique ID, not a positional index
list_items(todos)
```

### CLI

```
python3 todo.py add "Buy groceries" -p high -d 2025-12-31
python3 todo.py list --no-color
python3 todo.py ls -f pending -s priority
python3 todo.py done 0
python3 todo.py undone 0
python3 todo.py edit 0 "Updated task"
python3 todo.py remove 1
python3 todo.py search groceries
python3 todo.py stats
python3 todo.py clear-done
```

### Interactive TUI

```
python3 todo.py tui
```

Use `j`/`k` or the arrow keys to move, `space` to toggle a task, `x` to remove it, `a` to add a task, click to select or toggle, right-click to remove, and `q` to quit.
