# testing_pr

A simple Python project with greeting, farewell, and to-do list utilities.

## Usage

### To-Do List

```python
from todo import create_todo_list, add_item, mark_done, list_items, remove_item

todos = create_todo_list()
add_item(todos, "Buy groceries")
add_item(todos, "Read a book")
mark_done(todos, 0)
list_items(todos)
```

Or run interactively:

```
python todo.py
```