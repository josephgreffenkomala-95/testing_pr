from datetime import datetime

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Input, Label, ListItem, ListView, Static

from .models import _PRIORITY_ORDER
from .models import undo as _undo
from .core import (
    add_item,
    edit_item,
    mark_done,
    mark_undone,
    remove_item,
)


def _tui_color_pair(priority):
    """Legacy compatibility shim for the previous curses TUI."""
    return 0


def _tui_addstr(stdscr, y, x, text, attr=0):
    """Legacy compatibility shim for the previous curses TUI."""
    try:
        stdscr.addstr(y, x, text, attr)
    except TypeError:
        stdscr.addstr(y, x, text)


def _tui_render(*args, **kwargs):
    """Legacy compatibility shim for the previous curses TUI."""
    return None


def _tui_prompt(*args, **kwargs):
    """Legacy compatibility shim for the previous curses TUI."""
    return None


def _tui_handle_mouse(*args, **kwargs):
    """Legacy compatibility shim for the previous curses TUI."""
    return None


def _tui_help(*args, **kwargs):
    """Legacy compatibility shim for the previous curses TUI."""
    return None


def _tui_item_detail(*args, **kwargs):
    """Legacy compatibility shim for the previous curses TUI."""
    return None


def _tui_item_line(item):
    status = "x" if item["done"] else " "
    priority = item.get("priority", "medium")
    due = item.get("due", "")
    tags = item.get("tags", [])

    parts = [f"[{status}] {item['id']}: {item['task']} [{priority[0].upper()}]"]
    if due:
        parts.append(f"(due: {due})")
    if tags:
        parts.append(f"{{{','.join(tags)}}}")
    return " ".join(parts), priority


def _tui_is_overdue(item):
    if item["done"]:
        return False
    due = item.get("due")
    if not due:
        return False
    return due < datetime.now().strftime("%Y-%m-%d")


def _tui_build_display(todo_list, filter_by, sort_by, search_query):
    items = todo_list
    if filter_by == "done":
        items = [i for i in items if i["done"]]
    elif filter_by == "pending":
        items = [i for i in items if not i["done"]]
    if search_query:
        q = search_query.lower()
        items = [i for i in items if q in i["task"].lower()]
    if sort_by == "priority":
        items = sorted(items, key=lambda i: _PRIORITY_ORDER.get(i.get("priority", "medium"), 1))
    elif sort_by == "due":
        items = sorted(items, key=lambda i: i.get("due") or "9999-99-99")
    elif sort_by == "status":
        items = sorted(items, key=lambda i: (i["done"], i["id"]))
    elif sort_by == "created":
        items = sorted(items, key=lambda i: i.get("created_at", ""), reverse=True)
    return items


class HelpScreen(ModalScreen):
    def compose(self) -> ComposeResult:
        yield Static("TODO LIST - HELP", classes="help-title")
        yield Static("")
        yield Static("Navigation", classes="help-section")
        yield Static("  j / Up          Move selection up")
        yield Static("  k / Down        Move selection down")
        yield Static("")
        yield Static("Actions", classes="help-section")
        yield Static("  Space           Toggle task done/pending")
        yield Static("  x               Remove selected task (with confirmation)")
        yield Static("  a               Add a new task")
        yield Static("  e               Edit selected task text")
        yield Static("  i / Enter       Show full item details")
        yield Static("  u               Undo last action")
        yield Static("")
        yield Static("Display", classes="help-section")
        yield Static("  f               Cycle filter: all / done / pending")
        yield Static("  s               Cycle sort: id / priority / due / status / created")
        yield Static("  /               Search tasks by text")
        yield Static("  Esc (in search) Clear search query")
        yield Static("")
        yield Static("Mouse", classes="help-section")
        yield Static("  Left-click      Select or toggle task")
        yield Static("  Right-click     Remove task")
        yield Static("")
        yield Static("Other", classes="help-section")
        yield Static("  h / ?           Show this help screen")
        yield Static("  q               Quit TUI")
        yield Static("")
        yield Static("Press any key to return.", classes="help-footer")

    def on_key(self, event):
        event.stop()
        self.dismiss()


class DetailScreen(ModalScreen):
    def __init__(self, item):
        super().__init__()
        self._item = item

    def compose(self) -> ComposeResult:
        item = self._item
        yield Static(f"Item #{item['id']}", classes="detail-title")
        yield Static(f"Task:    {item['task']}")
        yield Static(f"Status:  {'Done' if item['done'] else 'Pending'}")
        yield Static(f"Priority: {item.get('priority', 'medium')}")
        yield Static(f"Due:     {item.get('due', 'None')}")
        yield Static(f"Tags:    {', '.join(item.get('tags', [])) or 'None'}")
        yield Static(f"Created: {item.get('created_at', 'Unknown')}")
        yield Static("")
        yield Static("Press any key to close.", classes="detail-footer")

    def on_key(self, event):
        event.stop()
        self.dismiss()


class InputPrompt(ModalScreen):
    BINDINGS = [
        Binding("escape", "dismiss_input", "Cancel", show=False),
    ]

    def __init__(self, prompt_text: str, initial_text: str = ""):
        super().__init__()
        self._prompt_text = prompt_text
        self._initial_text = initial_text

    def compose(self) -> ComposeResult:
        yield Label(self._prompt_text)
        yield Input(value=self._initial_text, id="prompt-input")

    def on_mount(self) -> None:
        self.query_one("#prompt-input", Input).focus()

    def action_dismiss_input(self) -> None:
        self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)


class TodoApp(App[bool]):
    CSS_PATH = "tui.tcss"
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("a", "add", "Add"),
        Binding("f", "cycle_filter", "Filter"),
        Binding("s", "cycle_sort", "Sort"),
        Binding("u", "undo", "Undo"),
        Binding("h,?", "show_help", "Help"),
    ]

    def __init__(self, todo_list):
        super().__init__()
        self.todo_list = todo_list
        self._changed = False
        self._filter_by = "all"
        self._sort_by = "id"
        self._search_query = ""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal():
            yield Static(id="sidebar")
            with Vertical(id="main-area"):
                yield Static(id="message")
                yield ListView(id="task-list")
        yield Footer()

    def on_mount(self) -> None:
        self._update_display()

    def _build_sidebar_lines(self):
        todo_list = self.todo_list
        total = len(todo_list)
        done_count = sum(1 for i in todo_list if i["done"])
        pending_count = total - done_count
        today = datetime.now().strftime("%Y-%m-%d")
        overdue_count = sum(
            1 for i in todo_list if not i["done"] and i.get("due") and i["due"] < today
        )
        high = sum(1 for i in todo_list if i.get("priority") == "high")
        medium = sum(1 for i in todo_list if i.get("priority") == "medium")
        low = sum(1 for i in todo_list if i.get("priority") == "low")

        lines = [
            " STATS",
            "",
            f" Total:   {total}",
            f" Done:    {done_count}",
            f" Pending: {pending_count}",
            f" Overdue: {overdue_count}",
            "",
            " Priority:",
            f"  High:   {high}",
            f"  Medium: {medium}",
            f"  Low:    {low}",
            "",
            " Mode:",
            f"  Filter: {self._filter_by}",
            f"  Sort:   {self._sort_by}",
        ]
        if self._search_query:
            lines.append(f"  Search: {self._search_query[:15]}")
        return "\n".join(lines)

    def _get_selected_item(self):
        list_view = self.query_one("#task-list", ListView)
        if list_view.index is None or not list_view.children:
            return None
        highlighted = list_view.children[list_view.index]
        item_id = highlighted._item_id
        for item in self.todo_list:
            if item["id"] == item_id:
                return item
        return None

    def _update_display(self, message=""):
        display_list = _tui_build_display(
            self.todo_list, self._filter_by, self._sort_by, self._search_query,
        )

        list_view = self.query_one("#task-list", ListView)
        list_view.clear()

        for item in display_list:
            line_text, priority = _tui_item_line(item)
            label = Label(line_text)

            classes = []
            if item["done"]:
                classes.append("done")
            if _tui_is_overdue(item):
                classes.append("overdue")
            if priority == "high":
                classes.append("prio-high")
            elif priority == "medium":
                classes.append("prio-medium")
            elif priority == "low":
                classes.append("prio-low")
            if classes:
                label.classes = " ".join(classes)

            li = ListItem(label)
            li._item_id = item["id"]
            list_view.append(li)

        if display_list and list_view.index is None:
            list_view.index = 0

        msg = self.query_one("#message", Static)
        if message:
            msg.update(message)
        elif display_list:
            done_count = sum(1 for item in display_list if item["done"])
            total = len(display_list)
            pct = int(done_count / total * 100) if total else 0
            msg.update(f"Progress: {done_count}/{total} done ({pct}%)")
        else:
            msg.update("No items yet. Press a to add one.")

        sidebar = self.query_one("#sidebar", Static)
        sidebar.update(self._build_sidebar_lines())

    def action_quit(self) -> None:
        self.exit(self._changed)

    def _cursor_down(self):
        list_view = self.query_one("#task-list", ListView)
        if list_view.index is None and list_view.children:
            list_view.index = 0
        elif list_view.children and list_view.index < len(list_view.children) - 1:
            list_view.index += 1

    def _cursor_up(self):
        list_view = self.query_one("#task-list", ListView)
        if list_view.index is None and list_view.children:
            list_view.index = 0
        elif list_view.children and list_view.index > 0:
            list_view.index -= 1

    def key_j(self, event):
        self._cursor_down()

    def key_k(self, event):
        self._cursor_up()

    def key_down(self, event):
        self._cursor_down()

    def key_up(self, event):
        self._cursor_up()

    def _do_toggle(self):
        item = self._get_selected_item()
        if item is None:
            return
        if item["done"]:
            mark_undone(self.todo_list, item["id"])
            self._update_display(f"Marked {item['id']} as pending.")
        else:
            mark_done(self.todo_list, item["id"])
            self._update_display(f"Marked {item['id']} as done.")
        self._changed = True

    def key_space(self, event):
        self._do_toggle()

    def action_add(self) -> None:
        def _on_result(result):
            if result is None:
                self._update_display("Add cancelled.")
                return
            try:
                add_item(self.todo_list, result)
            except ValueError as exc:
                self._update_display(f"Error: {exc}")
                return
            self._changed = True
            self._update_display("Added item.")
        self.push_screen(InputPrompt("New task: "), _on_result)

    def key_a(self, event):
        self.action_add()

    def action_edit(self) -> None:
        item = self._get_selected_item()
        if item is None:
            return
        def _on_result(result):
            if result is None:
                self._update_display("Edit cancelled.")
                return
            if not result.strip():
                self._update_display("Edit cancelled.")
                return
            try:
                edit_item(self.todo_list, item["id"], result)
            except ValueError as exc:
                self._update_display(f"Error: {exc}")
                return
            self._changed = True
            self._update_display(f"Updated item {item['id']}.")
        self.push_screen(InputPrompt(f"Edit item {item['id']}: ", item["task"]), _on_result)

    def key_e(self, event):
        self.action_edit()

    def action_detail(self) -> None:
        item = self._get_selected_item()
        if item is None:
            return
        def _on_close(_):
            self._update_display()
        self.push_screen(DetailScreen(item), _on_close)

    def key_i(self, event):
        self.action_detail()

    def key_enter(self, event):
        self.action_detail()

    def action_remove(self) -> None:
        item = self._get_selected_item()
        if item is None:
            return
        def _on_result(result):
            if result is None or result.lower() != "y":
                self._update_display("Removal cancelled.")
                return
            remove_item(self.todo_list, item["id"])
            self._changed = True
            self._update_display(f"Removed item {item['id']}.")
        self.push_screen(InputPrompt(f"Remove item {item['id']}? (y/N): "), _on_result)

    def key_x(self, event):
        self.action_remove()

    def action_cycle_filter(self) -> None:
        cycles = {"all": "done", "done": "pending", "pending": "all"}
        self._filter_by = cycles.get(self._filter_by, "all")
        self._update_display(f"Filter: {self._filter_by}")

    def action_cycle_sort(self) -> None:
        cycles = {"id": "priority", "priority": "due", "due": "status", "status": "created", "created": "id"}
        self._sort_by = cycles.get(self._sort_by, "id")
        self._update_display(f"Sort: {self._sort_by}")

    def action_search(self) -> None:
        def _on_result(result):
            if result is None:
                self._update_display("")
            elif result == "":
                self._search_query = ""
                self._update_display("Search cleared.")
            else:
                self._search_query = result
                self._update_display(f"Searching for '{result}'.")
        self.push_screen(InputPrompt("Search: "), _on_result)

    def key_slash(self, event):
        self.action_search()

    def action_undo(self) -> None:
        if _undo(self.todo_list):
            self._changed = True
            self._update_display("Undone last action.")
        else:
            self._update_display("Nothing to undo.")

    def action_show_help(self) -> None:
        self.push_screen(HelpScreen())


def run_tui(todo_list):
    app = TodoApp(todo_list)
    return app.run()


def _tui_main(todo_list):
    """Legacy compatibility shim for the previous curses TUI."""
    return run_tui(todo_list)
