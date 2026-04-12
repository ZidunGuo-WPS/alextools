"""Tests for OTSL ↔ HTML conversion and round-trip invariants."""

from __future__ import annotations

import pytest
from bs4 import BeautifulSoup

from alextools.otsl_html import html2otsl, otsl2html


def _normalize_cell_text(s: str) -> str:
    return " ".join(s.split())


def table_to_expanded_matrix(html_fragment: str) -> list[list[str]]:
    """
    Expand rowspan/colspan into a dense text matrix (one string per logical slot).

    ``th`` and ``td`` are treated the same. Used to assert two tables are
    content-equivalent regardless of empty ``<tr>`` or attribute ordering.
    """
    soup = BeautifulSoup(html_fragment, "html.parser")
    table = soup.find("table")
    if not table:
        return []

    # col -> (rows_remaining, text) for cells that extend downward
    rowspan_by_col: dict[int, tuple[int, str]] = {}
    matrix: list[list[str]] = []

    for tr in table.find_all("tr"):
        row: list[str] = []
        col = 0
        cells = tr.find_all(["td", "th"], recursive=False)

        def consume_rowspans() -> None:
            nonlocal col
            while col in rowspan_by_col:
                rem, txt = rowspan_by_col[col]
                row.append(txt)
                rem -= 1
                if rem > 0:
                    rowspan_by_col[col] = (rem, txt)
                else:
                    del rowspan_by_col[col]
                col += 1

        ci = 0
        while ci < len(cells):
            consume_rowspans()
            cell = cells[ci]
            ci += 1
            text = _normalize_cell_text(cell.get_text())
            try:
                rs = int(cell.get("rowspan", 1))
            except (ValueError, TypeError):
                rs = 1
            try:
                cs = int(cell.get("colspan", 1))
            except (ValueError, TypeError):
                cs = 1
            rs = max(1, rs)
            cs = max(1, cs)

            for dc in range(cs):
                row.append(text)
                if rs > 1:
                    rowspan_by_col[col + dc] = (rs - 1, text)
            col += cs

        consume_rowspans()
        matrix.append(row)

    if not matrix:
        return []

    width = max(len(r) for r in matrix)
    return [r + [""] * (width - len(r)) for r in matrix]


def assert_html_table_equivalent(a: str, b: str) -> None:
    assert table_to_expanded_matrix(a) == table_to_expanded_matrix(b), (
        f"Expanded matrices differ:\n{a!r}\nvs\n{b!r}"
    )


# OTSL fixtures: strict round-trip is html2otsl(otsl2html(s)) == s (byte-for-byte).
# Each string is also the pytest case id so ``pytest -v`` shows the exact input.
_OTSL_STRICT_CASES: list[str] = [
    "<fcel>A<fcel>B<nl><fcel>C<fcel>D<nl>",
    "<fcel>Name<ecel><fcel>Age<nl><fcel>John<ecel><fcel>25<nl>",
    "<fcel>Header<lcel><lcel><nl><fcel>A<fcel>B<fcel>C<nl>",
    "<fcel>Name<fcel>Value<nl><fcel>Item1<ucel><nl><fcel>Item2<fcel>200<nl>",
    "<fcel>Big<lcel><fcel>A<nl><ucel><xcel><fcel>B<nl>",
    "<fcel>Title<lcel><lcel><nl><fcel>Left<ecel><fcel>Right<nl><fcel>Bottom<ecel><fcel>Data<nl>",
    "<fcel>ID<fcel>Name<fcel>Score<nl><fcel>1<fcel>Alice<ucel><nl><fcel>2<fcel>Bob<fcel>85<nl>",
    "<fcel>Header1<fcel>Header2<fcel>Header3<nl><fcel>Data1<lcel><ecel><nl><ucel><xcel><fcel>Data4<nl>",
    "<ecel><ecel><ecel><nl><fcel>Data<ecel><ecel><nl>",
    "<fcel>A<fcel>B<nl><fcel>C<ucel><nl><fcel>D<fcel>E<nl>",
    "<fcel>A<lcel><nl><ucel><xcel><nl>",
    "<fcel>Merged<lcel><lcel><fcel>Normal<nl><ucel><xcel><xcel><fcel>Data1<nl><fcel>Data2<fcel>Data3<fcel>Data4<nl>",
    "<fcel>Price: $100<fcel>Count: 5<nl><fcel>Total: $500<fcel>Note: test<nl>",
]


@pytest.mark.parametrize("otsl", _OTSL_STRICT_CASES, ids=lambda s: s)
def test_otsl_strict_roundtrip_via_html(otsl: str) -> None:
    """otsl → otsl2html → html2otsl must reproduce the exact OTSL string.

    In ``pytest -v`` output, the ``[...]`` suffix after the test name is the
    exact OTSL input (same as ``_OTSL_STRICT_CASES``), not an abbreviated label.
    """
    html = otsl2html(otsl)
    back = html2otsl(html)
    assert back == otsl, (
        "OTSL round-trip mismatch (strings must be identical):\n"
        f"  in:  {otsl!r}\n"
        f"  out: {back!r}\n"
        f"  html: {html!r}"
    )


# --- HTML round-trip: html → otsl → html (structure via expanded matrix) ---

HTML_ROUNDTRIP_CASES = [
    "<table><tr><td>A</td><td>B</td></tr><tr><td>C</td><td>D</td></tr></table>",
    "<table><tr><td></td><td> </td></tr></table>",
    "<table><tr><td colspan='2'>Head</td></tr><tr><td>A</td><td>B</td></tr></table>",
    "<table><tr><td rowspan='2'>Side</td><td>A</td></tr><tr><td>B</td></tr></table>",
    "<table><tr><td rowspan='2' colspan='2'>Big</td><td>A</td></tr><tr><td>B</td></tr></table>",
    "<table><tbody><tr><th>X</th><td>Y</td></tr></tbody></table>",
    (
        "<table>"
        "<tr><td>a</td><td>b</td></tr>"
        "<tr><td>c</td><td>d</td></tr>"
        "</table>"
    ),
]


@pytest.mark.parametrize("html", HTML_ROUNDTRIP_CASES)
def test_html_roundtrip_content_equivalent(html: str) -> None:
    """Without style, html → OTSL → html preserves logical cell content."""
    otsl = html2otsl(html)
    assert otsl, f"html2otsl returned empty for {html!r}"
    rebuilt = otsl2html(otsl)
    assert_html_table_equivalent(html, rebuilt)


@pytest.mark.parametrize("html", HTML_ROUNDTRIP_CASES)
def test_html_roundtrip_otsl_stable(html: str) -> None:
    """OTSL is stable when re-derived from the rebuilt table."""
    o1 = html2otsl(html)
    h2 = otsl2html(o1)
    o2 = html2otsl(h2)
    assert o1 == o2, f"OTSL drift:\n  o1: {o1!r}\n  o2: {o2!r}\n  h2: {h2!r}"


def test_html_special_chars_roundtrip() -> None:
    html = "<table><tr><td>&amp; &lt;</td></tr></table>"
    otsl = html2otsl(html)
    rebuilt = otsl2html(otsl)
    assert_html_table_equivalent(html, rebuilt)
    assert "&amp;" in rebuilt and "&lt;" in rebuilt
