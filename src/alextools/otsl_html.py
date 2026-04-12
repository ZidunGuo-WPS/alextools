"""OTSL ↔ HTML table conversion (OTSL uses token tags like <fcel>, <nl>, etc.)."""

from __future__ import annotations

import re
from html import escape

from bs4 import BeautifulSoup


def otsl2html(otsl_str: str) -> str:
    """
    Convert an OTSL string to an HTML table fragment (no <html> wrapper).

    OTSL (no closing tags):
    - ``<ecel>`` — empty cell
    - ``<fcel>`` — cell with text until the next tag
    - ``<lcel>`` — merge with cell to the left (colspan)
    - ``<ucel>`` — merge with cell above (rowspan)
    - ``<xcel>`` — merge both left and up
    - ``<nl>`` — new row
    """
    if not otsl_str or not otsl_str.strip():
        return "<table></table>"

    rows_tokens = otsl_str.split("<nl>")
    if rows_tokens and rows_tokens[-1] == "":
        rows_tokens.pop()

    grid: list[list[dict | None]] = []

    for r_idx, row_str in enumerate(rows_tokens):
        if not row_str.strip():
            if r_idx >= len(grid):
                grid.append([])
            continue

        parts = re.findall(r"<([a-z]+)>(.*?)(?=<[a-z]+>|$)", row_str)

        if r_idx >= len(grid):
            grid.append([])

        col_idx = 0

        for tag, content in parts:
            while True:
                while len(grid[r_idx]) <= col_idx:
                    grid[r_idx].append(None)

                if grid[r_idx][col_idx] is not None:
                    col_idx += 1
                else:
                    break

            if tag == "fcel" or tag == "ecel":
                text = content.strip() if tag == "fcel" else ""
                grid[r_idx][col_idx] = {
                    "text": text,
                    "rowspan": 1,
                    "colspan": 1,
                    "valid": True,
                }
                col_idx += 1

            elif tag == "lcel":
                search_c = col_idx - 1
                found = False
                while search_c >= 0:
                    if len(grid[r_idx]) > search_c:
                        cell = grid[r_idx][search_c]
                        if cell and cell.get("valid"):
                            cell["colspan"] += 1
                            found = True
                            break
                    search_c -= 1

                if found:
                    grid[r_idx][col_idx] = {"valid": False, "type": "lcel"}
                else:
                    grid[r_idx][col_idx] = {
                        "text": "",
                        "rowspan": 1,
                        "colspan": 1,
                        "valid": True,
                    }
                col_idx += 1

            elif tag == "ucel":
                search_r = r_idx - 1
                found = False
                while search_r >= 0:
                    if len(grid[search_r]) > col_idx:
                        cell = grid[search_r][col_idx]
                        if cell and cell.get("valid"):
                            cell["rowspan"] += 1
                            found = True
                            break
                    search_r -= 1

                if found:
                    grid[r_idx][col_idx] = {"valid": False, "type": "ucel"}
                else:
                    grid[r_idx][col_idx] = {
                        "text": "",
                        "rowspan": 1,
                        "colspan": 1,
                        "valid": True,
                    }
                col_idx += 1

            elif tag == "xcel":
                grid[r_idx][col_idx] = {"valid": False, "type": "xcel"}
                col_idx += 1
            else:
                col_idx += 1

    html_parts = ["<table>"]

    for row in grid:
        html_parts.append("<tr>")
        for cell in row:
            if cell is None:
                continue
            if cell.get("valid"):
                attrs = []
                if cell["rowspan"] > 1:
                    attrs.append(f'rowspan="{cell["rowspan"]}"')
                if cell["colspan"] > 1:
                    attrs.append(f'colspan="{cell["colspan"]}"')

                attr_str = " " + " ".join(attrs) if attrs else ""
                text = escape(cell["text"])
                html_parts.append(f"<td{attr_str}>{text}</td>")
        html_parts.append("</tr>")

    html_parts.append("</table>")
    return "".join(html_parts)


def _clean_text(text: str) -> str:
    if not text:
        return ""
    return text.strip().replace("\n", " ")


def _is_empty_cell(tag) -> bool:
    return len(tag.get_text().strip()) == 0


def html2otsl(html_str: str) -> str:
    """
    Convert an HTML fragment containing a single ``<table>`` to OTSL.

    Returns an empty string if no table is found or on parse failure.
    """
    try:
        soup = BeautifulSoup(html_str, "html.parser")
        table = soup.find("table")
        if not table:
            return ""

        rows = table.find_all("tr")
        ostl_tokens: list[str] = []
        col_managers: dict[int, dict] = {}

        for r_idx, row in enumerate(rows):
            row_tokens: list[str] = []
            cells = row.find_all(["td", "th"])

            logical_col = 0
            html_cell_idx = 0

            while True:
                if logical_col in col_managers and col_managers[logical_col]["rows_left"] > 0:
                    info = col_managers[logical_col]
                    if info["is_primary"]:
                        row_tokens.append("<ucel>")
                    else:
                        row_tokens.append("<xcel>")

                    col_managers[logical_col]["rows_left"] -= 1
                    if col_managers[logical_col]["rows_left"] == 0:
                        del col_managers[logical_col]

                    logical_col += 1
                    continue

                if html_cell_idx < len(cells):
                    cell = cells[html_cell_idx]

                    if _is_empty_cell(cell):
                        row_tokens.append("<ecel>")
                    else:
                        text = _clean_text(cell.get_text())
                        row_tokens.append(f"<fcel>{text}")

                    try:
                        colspan = int(cell.get("colspan", 1))
                    except (ValueError, TypeError):
                        colspan = 1

                    try:
                        rowspan = int(cell.get("rowspan", 1))
                    except (ValueError, TypeError):
                        rowspan = 1

                    if rowspan > 1:
                        col_managers[logical_col] = {
                            "rows_left": rowspan - 1,
                            "is_primary": True,
                        }

                    html_cell_idx += 1
                    logical_col += 1

                    if colspan > 1:
                        for k in range(1, colspan):
                            row_tokens.append("<lcel>")
                            if rowspan > 1:
                                col_managers[logical_col] = {
                                    "rows_left": rowspan - 1,
                                    "is_primary": False,
                                }
                            logical_col += 1

                else:
                    if logical_col in col_managers and col_managers[logical_col]["rows_left"] > 0:
                        pass
                    else:
                        future_cols = [
                            c
                            for c in col_managers
                            if c > logical_col and col_managers[c]["rows_left"] > 0
                        ]
                        if future_cols:
                            logical_col += 1
                            continue
                        break

            row_tokens.append("<nl>")
            ostl_tokens.extend(row_tokens)

        return "".join(ostl_tokens)
    except Exception:
        return ""
