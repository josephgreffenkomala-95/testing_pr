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
python3 -m todo add "Buy groceries" -p high -d 2025-12-31
python3 -m todo list --no-color
python3 -m todo ls -f pending -s priority
python3 -m todo done 0
python3 -m todo undone 0
python3 -m todo edit 0 "Updated task"
python3 -m todo remove 1
python3 -m todo search groceries
python3 -m todo stats
python3 -m todo clear-done
```

### Interactive TUI

```
python3 -m todo tui
```

Opens a full-screen curses-based interactive terminal UI.

#### TUI Features

- **UI Layout** — Bold title bar at the top, dimmed help line with available commands, status messages for user feedback, a scrollable task list with `A_REVERSE` selection highlighting and dimmed styling for completed items, and a live stats sidebar (left ~22 columns) showing total/done/pending/overdue counts, priority distribution, and current filter/sort mode.
- **Keyboard Navigation** — `j`/`k` or up/down arrows to move selection, `space` to toggle a task done/pending, `x` to remove the selected task, `a` to open a task-entry prompt, and `q` to quit.
- **Mouse Support** — Left-click to select or toggle a task, right-click to remove it. Mouse events are handled via `curses.KEY_MOUSE`.
- **Task Entry Prompt** — Press `a` to open an inline prompt at the bottom of the screen for adding new tasks. Press Enter to confirm or Escape to cancel.
