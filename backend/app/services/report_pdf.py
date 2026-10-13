"""Verified report PDF — reportlab (Windows-friendly, no WeasyPrint).

One-page researcher summary (KPIs, waterfall, integrity flags) plus an
appendix listing every citation. QR encodes PUBLIC_BASE_URL/verify/{id};
the root hash is printed in full; synthetic demo rows are disclosed.
"""
import io

import qrcode
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.config import settings
from app.services.explain import explain_waterfall

_ACCENT = colors.HexColor("#0f766e")  # teal, per PRD design direction
_GRAY = colors.HexColor("#6b7280")


def _qr_png(verify_url: str, size_mm: float = 34) -> Image:
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(verify_url)
    qr.make(fit=True)
    buf = io.BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(buf, format="PNG")
    buf.seek(0)
    img = Image(buf, width=size_mm * mm, height=size_mm * mm)
    return img


def _table_style(header_bg=_ACCENT) -> TableStyle:
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d5db")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ])


def build_report_pdf(payload: dict, report_id: int) -> bytes:
    """Render a stored report payload to PDF bytes."""
    subject = payload.get("subject", {})
    kpis = payload.get("kpis", {})
    waterfall = payload.get("waterfall", [])
    flags = payload.get("integrity_flags", [])
    evidence = sorted(payload.get("evidence", []), key=lambda r: r["citation_id"])
    notice = payload.get("data_notice", {})
    policy = payload.get("policy", {})
    generated_at = payload.get("generated_at", "")
    root_hash = payload.get("root_hash", "")

    scope_type = payload.get("scope_type", "researcher")
    subject_name = subject.get("name", f"#{report_id}")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm,
                            title=f"CiteWise verified report — {subject_name}")
    styles = getSampleStyleSheet()
    h1, h2, body = styles["Heading1"], styles["Heading2"], styles["BodyText"]
    small = ParagraphStyle("Small", parent=body, fontSize=8, leading=10, textColor=colors.grey)


    verify_url = f"{settings.PUBLIC_BASE_URL.rstrip('/')}/verify/{report_id}"

    story = []
    story.append(Paragraph("CiteWise — Verified Citation Report", h1))
    story.append(Paragraph(f"{scope_type.title()} report: <b>{subject_name}</b>", body))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        f"Generated {generated_at} · Policy v{policy.get('version')} "
        f"({policy.get('headline_metric')}) · {len(evidence)} evidence records", small))
    story.append(Spacer(1, 4 * mm))

    # KPI table
    kpi_rows = [["Metric", "Value"],
                ["Papers", kpis.get("papers", 0)],
                ["Unique citations", kpis.get("unique_citations", 0)],
                ["Verified citations (headline)", kpis.get("verified_total", 0)],
                ["Verified h-index", kpis.get("h_index_verified", 0)],
                ["Raw h-index", kpis.get("h_index_raw", 0)],
                ["Verified i10", kpis.get("i10_verified", 0)],
                ["Self / Internal / External",
                 f"{kpis.get('self', 0)} / {kpis.get('internal', 0)} / {kpis.get('external', 0)}"]]
    t = Table(kpi_rows, colWidths=[85 * mm, 75 * mm])
    t.setStyle(_table_style())
    story.append(t)
    story.append(Spacer(1, 4 * mm))

    # Waterfall
    story.append(Paragraph("Raw → verified", h2))
    wf_rows = [["Step", "Value"]] + [[b["label"], b["value"]] for b in waterfall]
    t = Table(wf_rows, colWidths=[110 * mm, 50 * mm])
    t.setStyle(_table_style())
    story.append(t)
    story.append(Spacer(1, 2 * mm))
    for line in explain_waterfall(waterfall):
        story.append(Paragraph(line, small))
    story.append(Spacer(1, 4 * mm))

    # Integrity flags
    story.append(Paragraph("Integrity flags", h2))
    if flags:
        flag_rows = [["Flag", "Severity", "Note"]]
        for f in flags:
            note = (f.get("details") or {}).get("note", "")
            flag_rows.append([f.get("flag_type", ""), f.get("severity", ""), note])
        t = Table(flag_rows, colWidths=[55 * mm, 30 * mm, 75 * mm])
        t.setStyle(_table_style(colors.HexColor("#4f46e5")))
    else:
        t = Table([["No integrity flags raised"]], colWidths=[160 * mm])
        t.setStyle(_table_style(colors.HexColor("#4f46e5")))
    story.append(t)
    story.append(Spacer(1, 6 * mm))

    # Verification block
    story.append(Paragraph("Verification", h2))
    story.append(Paragraph(f"Root hash: <font face='Courier' size='7'>{root_hash}</font>", body))
    story.append(Paragraph(f"Verify independently: {verify_url}", body))
    story.append(Spacer(1, 3 * mm))
    story.append(_qr_png(verify_url))
    if notice.get("has_synthetic"):
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph(
            f"Demo disclosure: this report includes {notice.get('synthetic_rows', 0)} "
            "synthetic demonstration rows (planted duplicates/mentions), flagged "
            "is_synthetic=true in the data.", small))

    # Appendix: citation list
    story.append(PageBreak())
    story.append(Paragraph("Appendix — citations", h1))
    story.append(Spacer(1, 3 * mm))
    rows = [["#", "Class", "Intent", "Citing work", "Mentions"]]
    for r in evidence:
        citing = r.get("citing", {})
        title = (citing.get("title") or "")[:90]
        year = citing.get("year") or ""
        rows.append([r["citation_id"], r.get("class", ""), r.get("intent", ""),
                     f"{title} ({year})", r.get("mention_count", 1)])
    t = Table(rows, colWidths=[12 * mm, 22 * mm, 22 * mm, 88 * mm, 16 * mm], repeatRows=1)
    t.setStyle(_table_style())
    story.append(t)

    doc.build(story)
    return buf.getvalue()
