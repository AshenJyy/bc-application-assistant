"""Generate invented grid PSRs; never accepts a real applicant document."""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle

HEADERS = ["COURSE\nCODE", "COURSE DESCRIPTION", "COMP DATE", "PROV EXAM\nDATE", "SCHOOL\nLG",
           "SCHOOL\n%", "PROV\nEXAM", "FINAL", "EQU", "CREDIT"]
WIDTHS = [60,162,60,60,37,35,33,26,26,36]


def _table(c, rows, y, widths=WIDTHS):
    table = Table(rows, colWidths=widths)
    table.setStyle(TableStyle([("GRID", (0,0), (-1,-1), .5, colors.black),
        ("FONT", (0,0), (-1,-1), "Helvetica", 7), ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5)]))
    for index, row in enumerate(rows):
        if row[0] in {"RECORD OF SCHOOLING", "ACHIEVEMENT/ATTENDANCE", "GRADUATION ASSESSMENTS"}:
            table.setStyle(TableStyle([("SPAN", (0,index), (-1,index))]))
    _, height = table.wrap(535, 800)
    table.drawOn(c, 30, y-height)
    return y-height-15


def _heading(c, title="PERMANENT STUDENT RECORD"):
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(30, 800, title)
    c.setFont("Helvetica", 9)
    c.drawString(30, 781, "SYNTHETIC TEST DATA - NOT A VALID STUDENT RECORD")


def write_fixture(path: Path, *, title="PERMANENT STUDENT RECORD", orphan=False, reordered=False,
                  unknown_row=False, nonnumeric=False, repeated=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=A4, invariant=1)
    _heading(c, title)
    y = _table(c, [["RECORD OF SCHOOLING", "", "", "", "", "", ""],
        ["MINCODE", "DISTRICT-SCHOOL NAME", "ENTRY GRADE", "ADMIT DATE", "EXIT GRADE", "WDR DATE", "REASON"],
        ["99990001", "900 - Synthetic Cedar School", "09", "01-Sep-2023", "10", "30-Jun-2025", "Transfer"],
        ["99990002", "900 - Synthetic Coast School", "11", "01-Sep-2025", "", "", ""]], 760,
        widths=[55,170,60,70,55,70,55])
    headers = list(HEADERS)
    if reordered:
        headers[5], headers[6] = headers[6], headers[5]
    rows = [["ACHIEVEMENT/ATTENDANCE"] + [""]*9, headers]
    if not orphan:
        rows.append(["99990001", "900 - Synthetic Cedar School", "2024", "", "Grade 09", "", "", "", "", "Abs 1"])
    rows += [
        ["MTEST09---", "SYNTHETIC COURSE 9", "31-Jan-2024", "", "PRF", "", "", "PRF", "", "0"],
        ["MTEST10---", "SYNTHETIC COURSE 10", "28-Jun-2024", "", "A", "NaN" if nonnumeric else "84", "", "84", "", "4"],
        ["99990001", "900 - Synthetic Cedar School", "2025", "", "Grade 10", "", "", "", "", "Abs 0"],
        ["MSPLT10---", "SYNTHETIC SPLIT CREDIT", "31-Jan-2025", "", "B", "78", "", "78", "", "2"]]
    if unknown_row:
        rows.append(["ZUNKNOWN", "UNSUPPORTED COURSE", "", "", "", "", "", "", "", ""])
    if repeated:
        rows.append(["MSPLT10---", "SYNTHETIC SPLIT CREDIT", "27-Jun-2025", "", "A", "87", "", "87", "", "2"])
    _table(c, rows, y)
    c.showPage()
    _heading(c, title)
    y = _table(c, [["ACHIEVEMENT/ATTENDANCE"] + [""]*9, headers,
        ["MWRAP11---", "SYNTHETIC WRAPPED COURSE\nDESCRIPTION 11", "27-Jun-2025", "", "A", "92", "", "92", "", "4"]], 760)
    y = _table(c, [["99990002", "900 - Synthetic Coast School", "2026", "", "Grade 11", "", "", "", "", "Abs 0"],
        ["ACAL-2A---", "AP CALCULUS BC 12A", "29-May-2026", "", "A", "93", "", "93", "E", "4"],
        ["MREPT11---", "SYNTHETIC REPEATED COURSE 11", "25-Jun-2026", "", "A", "86", "", "86", "", "4"]], y)
    y = _table(c, [["99990002", "900 - Synthetic Coast School", "2027", "", "Grade 12", "", "", "", "", "Abs 0"],
        ["MPLAN12---", "SYNTHETIC COURSE WITHOUT RESULTS", "", "", "", "", "", "", "", ""]], y)
    _table(c, [["GRADUATION ASSESSMENTS", "", "", "", ""],
        ["CODE", "ASSESSMENT NAME", "ASSESSMENT\nDATE", "PROFICIENCY", "Sp\nCase"],
        ["LTE10", "LITERACY ASSESSMENT 10", "07-Apr-25", "3", ""]], y,
        widths=[60,240,100,80,55])
    c.save()


def write_academic_fixture(path: Path):
    """Two schools in the same grade/year, with enough rows to exercise Add course."""
    path.parent.mkdir(parents=True,exist_ok=True)
    c=canvas.Canvas(str(path),pagesize=A4,invariant=1);_heading(c)
    y=_table(c,[["RECORD OF SCHOOLING","","","","","",""],
        ["MINCODE","DISTRICT-SCHOOL NAME","ENTRY GRADE","ADMIT DATE","EXIT GRADE","WDR DATE","REASON"],
        ["99990001","900 - Fictional Secondary 1","09","01-Sep-2023","09","31-Jan-2024","Transfer"],
        ["99990002","900 - Fictional Secondary 2","09","01-Feb-2024","","",""]],760,
        widths=[55,170,60,70,55,70,55])
    _table(c,[["ACHIEVEMENT/ATTENDANCE"]+[""]*9,HEADERS,
        ["99990001","900 - Fictional Secondary 1","2024","","Grade 09","","","","","Abs 0"],
        ["MTEST09---","SYNTHETIC COURSE 9","31-Jan-2024","","PRF","","","PRF","","0"],
        ["MEXTA09---","SYNTHETIC EXTRA COURSE A","31-Jan-2024","","PRF","","","PRF","","0"],
        ["MEXTB09---","SYNTHETIC EXTRA COURSE B","31-Jan-2024","","PRF","","","PRF","","0"],
        ["99990002","900 - Fictional Secondary 2","2024","","Grade 09","","","","","Abs 0"],
        ["MTEST10---","SYNTHETIC COURSE 10","28-Jun-2024","","A","84","","84","","4"],
        ["99990001","900 - Fictional Secondary 1","2025","","Grade 09","","","","","Abs 0"],
        ["MRPT09---","SYNTHETIC LATER YEAR COURSE","30-Jan-2025","","PRF","","","PRF","","0"]],y)
    c.save()


if __name__ == "__main__":
    folder = Path(__file__).resolve().parents[1] / "tests/fixtures"
    write_fixture(folder / "synthetic_psr.pdf")
    write_fixture(folder / "synthetic_transcript.pdf", title="STUDENT TRANSCRIPT")
    write_fixture(folder / "synthetic_unsupported_columns.pdf", reordered=True)
    write_academic_fixture(folder/'synthetic_academic_psr.pdf')
    c = canvas.Canvas(str(folder / "synthetic_scan.pdf"), pagesize=A4, invariant=1)
    c.rect(30, 600, 535, 100)  # image/no text layer deliberately unsupported
    c.save()
