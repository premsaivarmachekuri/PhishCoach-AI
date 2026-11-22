import csv
import io
from typing import Any

from fpdf import FPDF, XPos, YPos


def export_metrics_csv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "department,user_count,delivered_count,clicked_count,submitted_count,reported_count,avg_risk_score\n"
    buf = io.StringIO()
    fieldnames = list(rows[0].keys())
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return buf.getvalue()


def export_metrics_pdf(title: str, rows: list[dict[str, Any]]) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    pdf.set_font("Helvetica", "", 10)
    if not rows:
        pdf.cell(0, 8, "No records available for the selected filter.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    else:
        for row in rows:
            line = " | ".join(f"{k}: {v}" for k, v in row.items())
            pdf.multi_cell(0, 6, line)
            pdf.ln(1)

    return bytes(pdf.output())
