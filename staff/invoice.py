# staff/invoice.py
from io import BytesIO
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
)
from reportlab.lib.enums import TA_RIGHT, TA_CENTER


def generate_invoice_pdf(order):
    """
    Generate a professional PDF invoice for an order.
    Returns a BytesIO buffer containing the PDF.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=18,
    )

    elements = []
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=28,
        textColor=colors.HexColor("#1a1a1a"),
        spaceAfter=30,
        alignment=TA_CENTER,
    )

    heading_style = ParagraphStyle(
        "CustomHeading",
        parent=styles["Heading2"],
        fontSize=12,
        textColor=colors.HexColor("#2c3e50"),
        spaceAfter=8,
        fontName="Helvetica-Bold",
    )

    # Title
    elements.append(Paragraph("INVOICE", title_style))
    elements.append(Spacer(1, 20))

    # Company and Invoice Info Table
    company_data = [
        [
            Paragraph(
                "<b>My Shop</b><br/>123 Business Street<br/>City, State 12345<br/>contact@myshop.com",
                styles["Normal"],
            ),
            Paragraph(
                f"<b>Invoice #:</b> {order.id}<br/>"
                f"<b>Date:</b> {order.created.strftime('%B %d, %Y')}<br/>"
                f"<b>Status:</b> {order.fulfillment_status.upper()}<br/>"
                f"<b>Payment:</b> {order.payment_status.upper()}",
                styles["Normal"],
            ),
        ]
    ]

    info_table = Table(company_data, colWidths=[3.5 * inch, 3 * inch])
    info_table.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (0, 0), "LEFT"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )
    elements.append(info_table)
    elements.append(Spacer(1, 30))

    # Bill To Section
    elements.append(Paragraph("Bill To:", heading_style))
    customer_info = (
        f"<b>{order.first_name} {order.last_name}</b><br/>"
        f"{order.email}<br/>"
        f"{order.address}<br/>"
        f"{order.city}, {order.postal_code}"
    )
    elements.append(Paragraph(customer_info, styles["Normal"]))
    elements.append(Spacer(1, 30))

    # Order Items Section
    elements.append(Paragraph("Order Items:", heading_style))
    elements.append(Spacer(1, 10))

    # Build items table
    table_data = [["Item", "Quantity", "Unit Price", "Total"]]

    for item in order.items.all():
        table_data.append(
            [
                item.product_name,
                str(item.quantity),
                f"${item.price:.2f}",
                f"${(item.quantity * item.price):.2f}",
            ]
        )

    # Calculate totals
    subtotal = float(order.get_total_cost())

    # Add spacing row
    table_data.append(["", "", "", ""])

    # Add totals
    table_data.append(["", "", "Subtotal:", f"${subtotal:.2f}"])

    if order.discount:
        table_data.append(["", "", "Discount:", f"-${float(order.discount):.2f}"])
        final_total = subtotal - float(order.discount)
    else:
        final_total = subtotal

    table_data.append(["", "", "Total:", f"${final_total:.2f}"])

    # Create table with styling
    items_table = Table(
        table_data,
        colWidths=[3.2 * inch, 1 * inch, 1.2 * inch, 1.2 * inch],
    )

    items_table.setStyle(
        TableStyle(
            [
                # Header styling
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3498db")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 11),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
                ("TOPPADDING", (0, 0), (-1, 0), 10),
                # Data rows styling
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("ALIGN", (0, 1), (0, -1), "LEFT"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -1), 10),
                ("TOPPADDING", (0, 1), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 8),
                # Alternating row colors (only for item rows, not totals)
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, len(order.items.all())),
                    [colors.white, colors.HexColor("#f8f9fa")],
                ),
                # Grid for item rows only
                (
                    "GRID",
                    (0, 0),
                    (-1, len(order.items.all())),
                    0.5,
                    colors.HexColor("#dee2e6"),
                ),
                # Totals section styling
                ("LINEABOVE", (2, -4), (-1, -4), 1, colors.HexColor("#dee2e6")),
                ("FONTNAME", (2, -3), (-1, -1), "Helvetica"),
                ("FONTSIZE", (2, -3), (-1, -1), 10),
                # Bold final total
                ("FONTNAME", (2, -1), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (2, -1), (-1, -1), 11),
                ("LINEABOVE", (2, -1), (-1, -1), 2, colors.HexColor("#2c3e50")),
                ("TOPPADDING", (2, -1), (-1, -1), 10),
            ]
        )
    )

    elements.append(items_table)
    elements.append(Spacer(1, 30))

    # Tracking info
    if hasattr(order, "shipment") and order.shipment and order.shipment.tracking_code:
        elements.append(
            Paragraph(
                f"<b>Tracking Number:</b> {order.shipment.tracking_code}",
                styles["Normal"],
            )
        )
        elements.append(Spacer(1, 12))

    # Shipment notes
    if hasattr(order, "shipment") and order.shipment and order.shipment.notes:
        elements.append(Paragraph("Shipment Notes:", heading_style))
        elements.append(Paragraph(order.shipment.notes, styles["Normal"]))
        elements.append(Spacer(1, 12))

    # Footer
    elements.append(Spacer(1, 40))
    footer_style = ParagraphStyle(
        "Footer",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        textColor=colors.HexColor("#7f8c8d"),
        fontSize=10,
        fontName="Helvetica-Oblique",
    )
    elements.append(Paragraph("Thank you for your business!", footer_style))

    # Build PDF
    doc.build(elements)

    pdf = buffer.getvalue()
    buffer.close()
    return pdf
