import curses
from datetime import datetime

from .models import _PRIORITY_ORDER
from .models import undo
from .core import (
    add_item,
    edit_item,
    mark_done,
    mark_undone,
    remove_item,
)


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


def _tui_color_pair(n):
    try:
        return curses.color_pair(n)
    except curses.error:
        return 0


def _tui_addstr(stdscr, y, x, text, attr=None):
    height, width = stdscr.getmaxyx()
    if y < 0 or y >= height:
        return
    if x >= width:
        return
    clipped = text[: max(0, width - x - 1)]
    try:
        if attr is None:
            stdscr.addstr(y, x, clipped)
        else:
            stdscr.addstr(y, x, clipped, attr)
    except curses.error:
        pass


def _tui_is_overdue(item):
    if item["done"]:
        return False
    due = item.get("due")
    if not due:
        return False
    return due < datetime.now().strftime("%Y-%m-%d")


def _tui_render(stdscr, todo_list, selected_index, scroll_offset=0, message="",
                filter_by="all", sort_by="id"):
    stdscr.clear()
    height, width = stdscr.getmaxyx()

    title = "TODO LIST"
    mode_str = ""
    if filter_by != "all":
        mode_str += f" [filter: {filter_by}]"
    if sort_by != "id":
        mode_str += f" [sort: {sort_by}]"
    help_line = "j/k arrows move | space toggle | x remove | a add | e edit | / search | h help | q quit"
    header = f"{len(todo_list)} item{'s' if len(todo_list) != 1 else ''}{mode_str}"

    _tui_addstr(stdscr, 0, 0, title, curses.A_BOLD)
    _tui_addstr(stdscr, 0, max(0, width - len(header) - 1), header, curses.A_DIM)
    _tui_addstr(stdscr, 1, 0, help_line, curses.A_DIM)
    _tui_addstr(stdscr, 2, 0, message or "Select a task to manage it.", curses.A_BOLD if message else curses.A_DIM)

    if not todo_list:
        _tui_addstr(stdscr, 4, 0, "No items yet. Press a to add one from the TUI.", curses.A_DIM)
        stdscr.refresh()
        return

    visible_rows = max(0, height - 6)
    end_index = min(scroll_offset + visible_rows, len(todo_list))
    display_items = todo_list[scroll_offset:end_index]

    for row, item in enumerate(display_items):
        actual_row = 4 + row
        line_text, priority = _tui_item_line(item)
        prefix = "> " if (scroll_offset + row) == selected_index else "  "
        line = prefix + line_text

        if item["done"]:
            color_attr = curses.A_DIM
        elif _tui_is_overdue(item):
            color_attr = curses.A_BOLD | _tui_color_pair(1)
        elif priority == "high":
            color_attr = _tui_color_pair(1)
        elif priority == "low":
            color_attr = _tui_color_pair(2)
        elif priority == "medium":
            color_attr = _tui_color_pair(3)
        else:
            color_attr = 0

        if (scroll_offset + row) == selected_index:
            attr = curses.A_REVERSE | (color_attr if color_attr else 0)
        else:
            attr = color_attr if color_attr else None

        _tui_addstr(stdscr, actual_row, 0, line, attr)

    done_count = sum(1 for item in todo_list if item["done"])
    total = len(todo_list)
    pct = int(done_count / total * 100) if total else 0
    progress = f"Progress: {done_count}/{total} done ({pct}%)"

    if scroll_offset > 0:
        _tui_addstr(stdscr, height - 2, 0, "↑ scroll up", curses.A_DIM)

    _tui_addstr(stdscr, height - 1, 0, progress, curses.A_DIM)

    stdscr.refresh()


def _tui_prompt(stdscr, prompt, y=None):
    height, width = stdscr.getmaxyx()
    if y is None:
        y = max(0, height - 1)
    buffer = []

    while True:
        _tui_addstr(stdscr, y, 0, " " * max(0, width - 1))
        _tui_addstr(stdscr, y, 0, f"{prompt}{''.join(buffer)}", curses.A_BOLD)
        stdscr.refresh()
        key = stdscr.getch()

        if key in (10, 13, curses.KEY_ENTER):
            return "".join(buffer).strip()
        if key in (27,):
            return None
        if key in (curses.KEY_BACKSPACE, 127, 8):
            if buffer:
                buffer.pop()
            continue
        if 32 <= key <= 126:
            buffer.append(chr(key))


def _tui_handle_mouse(display_list, todo_list, selected_index):
    try:
        _, _, y, _, bstate = curses.getmouse()
    except curses.error:
        return selected_index, False, ""

    row = y - 4
    if row < 0 or row >= len(display_list):
        return selected_index, False, ""

    item_id = display_list[row]["id"]
    if bstate & curses.BUTTON3_CLICKED:
        if remove_item(todo_list, item_id):
            if selected_index >= len(display_list):
                selected_index = max(0, len(display_list) - 1)
            return selected_index, True, f"Removed item {item_id}."
        return selected_index, False, ""

    if bstate & curses.BUTTON1_CLICKED:
        if row != selected_index:
            return row, False, f"Selected item {item_id}."
        item = next((i for i in todo_list if i["id"] == item_id), None)
        if item and item["done"]:
            mark_undone(todo_list, item_id)
            return selected_index, True, f"Marked {item_id} as pending."
        mark_done(todo_list, item_id)
        return selected_index, True, f"Marked {item_id} as done."

    return selected_index, False, ""


def _tui_help(stdscr):
    height, width = stdscr.getmaxyx()
    help_lines = [
        ("TODO LIST — HELP", curses.A_BOLD),
        ("", 0),
        ("Navigation", curses.A_BOLD),
        ("  j / Up          Move selection up", 0),
        ("  k / Down        Move selection down", 0),
        ("", 0),
        ("Actions", curses.A_BOLD),
        ("  Space           Toggle task done/pending", 0),
        ("  x               Remove selected task (with confirmation)", 0),
        ("  a               Add a new task", 0),
        ("  e               Edit selected task text", 0),
        ("  i / Enter       Show full item details", 0),
        ("  u               Undo last action", 0),
        ("", 0),
        ("Display", curses.A_BOLD),
        ("  f               Cycle filter: all / done / pending", 0),
        ("  s               Cycle sort: id / priority / due / status / created", 0),
        ("  /               Search tasks by text", 0),
        ("  Esc (in search) Clear search query", 0),
        ("", 0),
        ("Mouse", curses.A_BOLD),
        ("  Left-click      Select or toggle task", 0),
        ("  Right-click     Remove task", 0),
        ("", 0),
        ("Other", curses.A_BOLD),
        ("  h / ?           Show this help screen", 0),
        ("  q               Quit TUI", 0),
    ]
    stdscr.clear()
    y = 0
    for line, attr in help_lines:
        if y >= height:
            break
        _tui_addstr(stdscr, y, 0, line[: max(0, width - 1)], attr)
        y += 1
    _tui_addstr(stdscr, height - 1, 0, "Press any key to return.", curses.A_DIM)
    stdscr.refresh()
    stdscr.getch()


def _tui_item_detail(stdscr, item):
    height, width = stdscr.getmaxyx()
    lines = [
        f"Item #{item['id']}",
        f"Task:    {item['task']}",
        f"Status:  {'Done' if item['done'] else 'Pending'}",
        f"Priority: {item.get('priority', 'medium')}",
        f"Due:     {item.get('due', 'None')}",
        f"Tags:    {', '.join(item.get('tags', [])) or 'None'}",
        f"Created: {item.get('created_at', 'Unknown')}",
    ]
    box_height = len(lines) + 2
    box_width = max(len(l) for l in lines) + 4
    start_y = max(0, (height - box_height) // 2)
    start_x = max(0, (width - box_width) // 2)

    for i in range(box_height):
        _tui_addstr(stdscr, start_y + i, start_x, " " * box_width)
    for i, line in enumerate(lines):
        _tui_addstr(stdscr, start_y + 1 + i, start_x + 2, line, curses.A_BOLD if i == 0 else 0)
    _tui_addstr(stdscr, start_y + box_height, start_x, "Press any key to close.", curses.A_DIM)
    stdscr.refresh()
    stdscr.getch()


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


def _tui_main(stdscr, todo_list):
    changed = False
    selected_index = 0
    scroll_offset = 0
    message = ""
    filter_by = "all"
    sort_by = "id"
    search_query = ""

    try:
        curses.curs_set(0)
    except curses.error:
        pass

    stdscr.keypad(True)

    curses.start_color()
    curses.init_pair(1, curses.COLOR_RED, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_CYAN, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK)

    try:
        mouse_events = getattr(curses, "ALL_MOUSE_EVENTS", 0) | getattr(curses, "REPORT_MOUSE_POSITION", 0)
        curses.mousemask(mouse_events)
    except (AttributeError, curses.error):
        pass

    while True:
        display_list = _tui_build_display(todo_list, filter_by, sort_by, search_query)

        if display_list and selected_index >= len(display_list):
            selected_index = len(display_list) - 1
        if not display_list:
            selected_index = 0

        height, _ = stdscr.getmaxyx()
        visible_rows = max(0, height - 6)
        if selected_index < scroll_offset:
            scroll_offset = selected_index
        if selected_index >= scroll_offset + visible_rows:
            scroll_offset = selected_index - visible_rows + 1

        _tui_render(stdscr, display_list, selected_index, scroll_offset=scroll_offset,
                    message=message, filter_by=filter_by, sort_by=sort_by)
        message = ""
        key = stdscr.getch()

        if key in (ord("q"), ord("Q")):
            return changed

        if key == curses.KEY_RESIZE:
            stdscr.clear()
            continue

        if key in (curses.KEY_UP, ord("k")):
            if display_list:
                selected_index = max(0, selected_index - 1)
            continue

        if key in (curses.KEY_DOWN, ord("j")):
            if display_list:
                selected_index = min(len(display_list) - 1, selected_index + 1)
            continue

        if key in (ord("a"), ord("A")):
            try:
                new_task = _tui_prompt(stdscr, "New task: ")
            except curses.error:
                message = "Unable to open the add prompt."
                continue
            if new_task is None:
                message = "Add cancelled."
                continue
            try:
                add_item(todo_list, new_task)
            except ValueError as exc:
                message = f"Error: {exc}"
                continue
            selected_index = len(display_list)
            changed = True
            message = f"Added item {new_task}."
            continue

        if key == curses.KEY_MOUSE:
            selected_index, mouse_changed, mouse_message = _tui_handle_mouse(display_list, todo_list, selected_index)
            if mouse_message:
                message = mouse_message
            changed = changed or mouse_changed
            continue

        if key in (ord("e"), ord("E")):
            if not display_list:
                continue
            try:
                new_text = _tui_prompt(stdscr, f"Edit item {display_list[selected_index]['id']}: ")
            except curses.error:
                message = "Unable to open the edit prompt."
                continue
            if new_text is None:
                message = "Edit cancelled."
                continue
            try:
                edit_item(todo_list, display_list[selected_index]["id"], new_text)
            except ValueError as exc:
                message = f"Error: {exc}"
                continue
            changed = True
            message = f"Updated item {display_list[selected_index]['id']}."
            continue

        if key in (ord("h"), ord("?")):
            _tui_help(stdscr)
            continue

        if key == ord("/"):
            try:
                query = _tui_prompt(stdscr, "Search: ")
            except curses.error:
                message = "Unable to open search prompt."
                continue
            if query is None:
                pass
            elif query == "":
                search_query = ""
                message = "Search cleared."
            else:
                search_query = query
                message = f"Searching for '{query}'."
            selected_index = 0
            scroll_offset = 0
            continue

        if key in (ord("f"), ord("F")):
            cycles = {"all": "done", "done": "pending", "pending": "all"}
            filter_by = cycles.get(filter_by, "all")
            message = f"Filter: {filter_by}"
            selected_index = 0
            scroll_offset = 0
            continue

        if key in (ord("s"), ord("S")):
            cycles = {"id": "priority", "priority": "due", "due": "status", "status": "created", "created": "id"}
            sort_by = cycles.get(sort_by, "id")
            message = f"Sort: {sort_by}"
            selected_index = 0
            scroll_offset = 0
            continue

        if key in (ord("u"), ord("U")):
            if undo(todo_list):
                changed = True
                message = "Undone last action."
            else:
                message = "Nothing to undo."
            selected_index = 0
            scroll_offset = 0
            continue

        if key in (ord("i"), ord("I"), 10, 13, curses.KEY_ENTER):
            if not display_list:
                continue
            _tui_item_detail(stdscr, display_list[selected_index])
            continue

        if not display_list:
            continue

        item_id = display_list[selected_index]["id"]

        if key == ord(" "):
            if display_list[selected_index]["done"]:
                mark_undone(todo_list, item_id)
                message = f"Marked {item_id} as pending."
            else:
                mark_done(todo_list, item_id)
                message = f"Marked {item_id} as done."
            changed = True
        elif key in (ord("x"), ord("X")):
            try:
                confirm = _tui_prompt(stdscr, f"Remove item {item_id}? (y/N): ")
            except curses.error:
                message = "Unable to open confirmation prompt."
                continue
            if confirm and confirm.lower() == "y":
                if remove_item(todo_list, item_id):
                    changed = True
                    message = f"Removed item {item_id}."
                    if selected_index >= len(display_list):
                        selected_index = max(0, len(display_list) - 1)
            else:
                message = "Removal cancelled."


def run_tui(todo_list):
    return bool(curses.wrapper(_tui_main, todo_list))
