import io
import os
from io import BytesIO
from django.http import HttpResponse
from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect

from reportlab.pdfgen import canvas
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.lib import colors

import arabic_reshaper
from bidi.algorithm import get_display

# Register Persian fonts for ReportLab
font_path = os.path.join(settings.STATIC_ROOT, "fonts")

try:
    pdfmetrics.registerFont(TTFont("Vazir", os.path.join(font_path, "Vazir.ttf")))
    pdfmetrics.registerFont(
        TTFont("Vazir-Bold", os.path.join(font_path, "Vazir-Bold.ttf"))
    )
except Exception as e:
    print("FONT REGISTRATION ERROR:", e)


def arabic_text(text):
    # Converts text to RTL and reshapes Persian characters
    reshaped = arabic_reshaper.reshape(str(text))
    return get_display(reshaped)


def wrap_rtl_text(c, text, max_width, font_name="Vazir", font_size=12):
    """
    Advanced RTL/LTR mixed text wrapper (Option B).

    Features:
    - NO internal reshaping; shaping happens only when drawing.
    - Persian words are kept whole (never hyphenated).
    - English words can be hyphenated when too long.
    - URLs are treated as atomic tokens (never broken).
    - Splits on whitespace + punctuation boundaries.
    - Ensures punctuation is not placed at the beginning of a line.
    """

    import re

    # ------------------------------------------
    # Helper: Is a token a URL?
    # ------------------------------------------
    def is_url(tok):
        return (
            tok.startswith("http://")
            or tok.startswith("https://")
            or tok.startswith("www.")
        )

    # ------------------------------------------
    # Helper: Hyphenate an English segment
    # Split long English tokens (e.g. identifiers)
    # into smaller parts with hyphens.
    # ------------------------------------------
    def hyphenate_english(word):
        if len(word) <= 12:
            return [word]

        parts = []
        chunk_size = 10

        for i in range(0, len(word), chunk_size):
            chunk = word[i : i + chunk_size]
            if i + chunk_size < len(word):
                parts.append(chunk + "-")  # add hyphen for continuation
            else:
                parts.append(chunk)  # last chunk no hyphen

        return parts

    # ------------------------------------------
    # STEP 1: Tokenization
    # Persian and English mixed tokens:
    # - Keep punctuation attached but separate when needed
    # - Letters, digits, underscores, hyphens stay together
    # ------------------------------------------
    tokens = re.findall(r"https?://\S+|www\.\S+|[\w\-]+|[^\s\w]", text)

    lines = []
    current = ""

    for tok in tokens:

        # URLs must stay intact
        if is_url(tok):
            tok_segments = [tok]
        else:
            # Detect whether this is Persian or English
            if re.search(r"[A-Za-z]", tok):
                # English → hyphenate if too long
                tok_segments = hyphenate_english(tok)
            else:
                tok_segments = [tok]  # Persian or punctuation → no hyphenation

        # Iterate over segments (English chunks or whole words)
        for segment in tok_segments:

            # Avoid starting a line with punctuation
            if segment in ",.:;)]}":
                # Punctuation should stick to previous word:
                test_line = current + segment
            else:
                # Normal spacing
                test_line = segment if current == "" else current + " " + segment

            # Measure visual width
            visual = arabic_text(test_line)
            if c.stringWidth(visual, font_name, font_size) <= max_width:
                current = test_line
            else:
                if current:
                    lines.append(current)
                current = segment

    if current:
        lines.append(current)

    return lines


def format_price(value):
    """
    Formats price with commas and Persian digits + Currency Symbol
    Matches the logic of your |currency template filter.
    """
    # 1. Format with commas (2500 -> 2,500)
    formatted = "{:,.0f}".format(int(value))
    # 2. Add Currency Symbol from settings
    text = f"{formatted} {settings.CURRENCY_SYMBOL}"
    # 3. Convert English digits to Persian
    english_digits = "0123456789"
    persian_digits = "۰۱۲۳۴۵۶۷۸۹"
    translation_table = str.maketrans(english_digits, persian_digits)
    text = text.translate(translation_table)
    # 4. Final reshape for PDF
    return arabic_text(text)


def draw_line(c, x1, y1, x2, y2):
    c.line(x1, y1, x2, y2)


def draw_text_centered_vertically(
    c, x, y, box_height, text, font="Vazir", size=12, rtl=True
):
    c.setFont(font, size)
    processed = arabic_text(text) if rtl else text
    text_y = y + (box_height / 2) - (size / 3)  # mathematical centering
    c.drawString(x, text_y, processed)


def draw_safe_text(
    c, text, x, y, max_width, font_name="Vazir", base_size=12, align="right"
):
    """
    Draws text but shrinks the font size automatically if it exceeds max_width.
    """
    c.setFont(font_name, base_size)
    text_width = c.stringWidth(text, font_name, base_size)

    # If text is too wide, calculate a smaller font size
    if text_width > max_width:
        new_size = base_size * (max_width / text_width)
        c.setFont(font_name, new_size)

    if align == "right":
        c.drawRightString(x, y, text)
    elif align == "center":
        c.drawCentredString(x, y, text)
    else:
        c.drawString(x, y, text)


def measure_text_widths(order, font_name="Vazir", font_size=12):
    """
    Scans all products and numeric values and determines:
    - max product name width
    - max price width
    - max sum width
    """
    dummy_canvas = canvas.Canvas(BytesIO())
    get_w = lambda txt: dummy_canvas.stringWidth(txt, font_name, font_size)

    max_name_w = 0
    max_price_w = 0
    max_sum_w = 0

    for item in order.items.all():
        # Product name (Persian reshaped)
        name_text = arabic_text(item.product.name)
        max_name_w = max(max_name_w, get_w(name_text))

        # Price (just numbers)
        price_text = arabic_text("{:,.0f}".format(int(item.price)))
        max_price_w = max(max_price_w, get_w(price_text))

        # Sum
        sum_text = arabic_text("{:,.0f}".format(int(item.get_cost())))
        max_sum_w = max(max_sum_w, get_w(sum_text))

    return {
        "name": max_name_w,
        "price": max_price_w,
        "sum": max_sum_w,
    }


# ┌─────────────────────────────────────────────────────────────────────────────┐
# │                             PDF TABLE COORDINATE MAP                       │
# └─────────────────────────────────────────────────────────────────────────────┘
#
# All X coordinates grow LEFT → RIGHT  (ReportLab default, even for RTL text)
#
#   table_left
#       │
#       ▼
#       ┌───────────────────────────────────────────────────────────────────────┐
#       │                                                                       │
#       │   ← product column →      ← quantity →    ← price →      ← sum →      │
#       │                                                                       │
#       └───────────────────────────────────────────────────────────────────────┘
#
#   table_left                 col_sum                col_price      col_quantity        col_product
#       │                         │                        │               │                    │
#       ▼                         ▼                        ▼               ▼                    ▼
#       0─────────────────────────┼────────────────────────┼───────────────┼────────────────────┼────▶ X
#                                 │                        │               │                    │
#                                 │                        │               │                    │
#                                 │                        │               │                    │
#             SUM COLUMN          │ PRICE COLUMN           │ QUANTITY COL  │ PRODUCT NAME COL   │
#
#
# COLUMN WIDTHS (computed dynamically)
# ------------------------------------
#
#   product_col_width  = col_product - col_quantity
#   quantity_col_width = col_quantity - col_price
#   price_col_width    = col_price - col_sum
#   sum_col_width      = col_sum - table_left
#
#
# TRUE COLUMN CENTERS (use these for centered labels!)
# -----------------------------------------------------
#
#   sum_center      = table_left + ((col_sum      - table_left)   / 2)
#   price_center    = col_sum    + ((col_price    - col_sum)      / 2)
#   quantity_center = col_price  + ((col_quantity - col_price)    / 2)
#   product_center  = col_quantity + ((col_product - col_quantity) / 2)

#
#
# VISUAL EXPLANATION WITH ANNOTATED TEXT POSITIONS
# ------------------------------------------------
#
#                                     (CENTER)
#                           price_center (x)
#                                 │
#                                 ▼
#        0-------sum─col------------col_price----------quantity-col----------product-col-------
#        │                     │                  │                   │                        │
#        │                     │                  │                   │                        │
#        │<-----sum width----->│<---price width-->|<----qty width---->|<----product width----->│
#
#
# TEXT ALIGNMENT RULES
# --------------------
#
#   Product names:  RTL, right-aligned  →  draw at (col_product - 10)
#
#   Quantity:       centered            →  draw at quantity_center
#
#   Price:          centered            →  draw at price_center
#
#   Sum:            centered or left    →  draw at sum_center  (recommended)
#
#
# SEPARATOR LINES
# ---------------
#
#   Vertical lines drawn exactly at:
#
#       c.line(col_sum,       y_top, y_bottom)
#       c.line(col_price,     y_top, y_bottom)
#       c.line(col_quantity,  y_top, y_bottom)
#
#
# IMPORTANT:
# ----------
# Never draw text at col_price / col_quantity / col_sum
# because these are separator lines — text will overlap!
#
# Always use:
#
#       quantity_center
#       price_center
#       sum_center
#
# Or right-aligned:
#
#       drawRightString(col_product - padding)
#
#
# END OF COORDINATE MAP


def generate_invoice_pdf(order):
    """
    Fully refactored professional Persian invoice generator (RTL).
    Includes:
    - Page border
    - QR code (left), invoice info (right)
    - Paid/unpaid badge
    - Customer info box
    - Product table (multi-page, repeated header, column lines)
    - Totals box aligned with table
    - Footer + page numbers
    - SmartShrink two-line wrapping for product names
    """

    # ---------------------------------------
    # IMPORTS
    # ---------------------------------------
    from reportlab.lib.colors import HexColor, black
    from reportlab.graphics.shapes import Drawing
    from reportlab.graphics import renderPDF
    import qrcode

    labels = settings.ORDER_LABELS

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # ---------------------------------------
    # STANDARDIZED MARGINS & GRID
    # ---------------------------------------
    M_LEFT = 40
    M_RIGHT = 40
    M_TOP = 50
    M_BOTTOM = 50

    y = height - M_TOP
    page_number = 1

    table_left = M_LEFT
    table_right = width - M_RIGHT
    table_width = table_right - table_left

    # ---------------------------------------
    # PAGE BORDER
    # ---------------------------------------
    c.setStrokeColor(HexColor("#444"))
    c.setLineWidth(1.4)
    c.rect(
        M_LEFT - 20,
        M_BOTTOM - 20,
        width - (M_LEFT + M_RIGHT) + 40,
        height - (M_TOP + M_BOTTOM) + 40,
    )

    # ---------------------------------------
    # INVOICE IDENTIFIERS
    # ---------------------------------------
    invoice_number = f"INV-{order.created.year}-{order.id:06d}"
    is_paid = getattr(order, "paid", False)
    badge = labels["paid_label"] if is_paid else labels["unpaid_label"]

    # ---------------------------------------
    # QR CODE (LEFT)
    # ---------------------------------------
    qr_size = 85
    qr_x = M_LEFT
    qr_y = y - qr_size

    qr_data = f"{invoice_number} | https://myshop.com"
    qr = qrcode.QRCode(box_size=2, border=1)
    qr.add_data(qr_data)
    qr.make()
    img = qr.make_image(fill_color="black", back_color="white")

    qr_buffer = BytesIO()
    img.save(qr_buffer)
    qr_buffer.seek(0)
    qr_reader = ImageReader(qr_buffer)

    c.drawImage(qr_reader, qr_x, qr_y, width=qr_size, height=qr_size)

    # ---------------------------------------
    # INVOICE TEXT (RIGHT)
    # ---------------------------------------
    text_x = width - M_RIGHT

    c.setFont("Vazir-Bold", 14)
    c.drawRightString(
        text_x,
        qr_y + qr_size - 5,
        arabic_text(f"{labels['invoice_number_label']}: {invoice_number}"),
    )

    c.setFont("Vazir", 12)
    c.drawRightString(
        text_x,
        qr_y + qr_size - 28,
        arabic_text(f"{labels['order_label']}: {order.id}"),
    )
    c.drawRightString(
        text_x,
        qr_y + qr_size - 50,
        arabic_text(f"{labels['date_label']}: {order.created.strftime('%Y/%m/%d')}"),
    )

    # Badge next to QR
    c.setFont("Vazir-Bold", 20)
    c.setFillColor(HexColor("#27ae60") if is_paid else HexColor("#c0392b"))
    badge_y = qr_y + (qr_size / 2) - 10
    c.drawString(qr_x + qr_size + 20, badge_y, arabic_text(badge))
    c.setFillColor(black)

    y = qr_y - 40

    # ---------------------------------------
    # ORDER INFO BLOCK
    # ---------------------------------------
    c.setFont("Vazir-Bold", 14)
    c.drawRightString(text_x, y, arabic_text(labels["order_label"] + f": {order.id}"))
    y -= 25

    c.setFont("Vazir", 12)
    c.drawRightString(
        text_x,
        y,
        arabic_text(f"{labels['date_label']}: {order.created.strftime('%Y/%m/%d')}"),
    )
    y -= 40

    # ---------------------------------------
    # CUSTOMER BOX
    # ---------------------------------------
    box_h = 70
    box_y = y - box_h

    # Background
    c.setFillColor(HexColor("#fafafa"))
    c.rect(M_LEFT, box_y, table_width, box_h, stroke=0, fill=1)

    # Border
    c.setFillColor(black)
    c.setStrokeColor(HexColor("#999"))
    c.rect(M_LEFT, box_y, table_width, box_h, stroke=1, fill=0)

    # Label
    draw_text_centered_vertically(
        c,
        M_LEFT + table_width - 140,
        box_y,
        box_h,
        labels["customer_label"],
        font="Vazir-Bold",
        size=13,
    )

    # Value
    customer_name = f"{order.first_name} {order.last_name}"
    draw_text_centered_vertically(
        c, M_LEFT + 80, box_y, box_h, customer_name, font="Vazir", size=12
    )

    y = box_y - 40

    # ---------------------------------------
    # DYNAMIC TABLE SIZING
    # ---------------------------------------
    text_widths = measure_text_widths(order)

    max_name = text_widths["name"]
    max_price = text_widths["price"]
    max_sum = text_widths["sum"]

    # Minimum widths (safe values)
    MIN_NAME_COL = 160
    MIN_PRICE_COL = 70
    MIN_SUM_COL = 110
    QTY_COL_WIDTH = 50  # fixed narrow quantity column

    name_col_width = max(MIN_NAME_COL, max_name + 20)
    price_col_width = max(MIN_PRICE_COL, max_price + 20)
    sum_col_width = max(MIN_SUM_COL, max_sum + 20)

    # Now we compute column anchors dynamically (RTL alignment)
    table_total_width = name_col_width + QTY_COL_WIDTH + price_col_width + sum_col_width
    if table_total_width > table_width:
        # reduce name column if necessary
        overflow = table_total_width - table_width
        name_col_width = max(MIN_NAME_COL, name_col_width - overflow)

    # Rightmost column is "Product Name"
    col_product_right = table_right
    col_quantity_right = col_product_right - name_col_width
    col_price_right = col_quantity_right - QTY_COL_WIDTH
    col_sum_right = col_price_right - price_col_width

    # These will be used as anchors:
    col_product = col_product_right
    col_quantity = col_quantity_right
    col_price = col_price_right
    col_sum = col_sum_right

    # For visual separators, precompute list of x positions (lines)
    column_lines = [col_sum, col_price, col_quantity, col_product]

    # compute real centers of each column
    quantity_center = col_price + ((col_quantity - col_price) / 2)
    price_center = col_sum + ((col_price - col_sum) / 2)
    sum_center = table_left + ((col_sum - table_left) / 2)
    product_center = col_quantity + ((col_product - col_quantity) / 2)

    # ---------------------------------------
    # PRODUCT TABLE HEADER
    # ---------------------------------------
    def draw_table_header(y_pos):
        header_h = 25

        c.setFillColor(HexColor("#f0f0f0"))
        c.rect(table_left, y_pos - header_h, table_width, header_h, fill=1, stroke=0)
        c.setFillColor(black)

        label_y = y_pos - header_h + 7
        c.setFont("Vazir-Bold", 12)

        # compute real centers of each column
        quantity_center = col_price + ((col_quantity - col_price) / 2)
        price_center = col_sum + ((col_price - col_sum) / 2)
        sum_center = table_left + ((col_sum - table_left) / 2)
        product_center = col_quantity + ((col_product - col_quantity) / 2)

        # product name header (RTL, right aligned)
        c.drawRightString(
            col_product - 10, label_y, arabic_text(labels["product_name"])
        )

        # quantity header (center)
        c.drawCentredString(quantity_center, label_y, arabic_text(labels["quantity"]))

        # price header (center)
        c.drawCentredString(
            price_center,
            label_y,
            arabic_text(f"{labels['price']} ({settings.CURRENCY_SYMBOL})"),
        )

        # sum header (center)
        c.drawCentredString(
            sum_center,
            label_y,
            arabic_text(f"{labels['sum']} ({settings.CURRENCY_SYMBOL})"),
        )

        # separators
        c.setStrokeColor(HexColor("#bbb"))
        c.setLineWidth(0.8)

        c.line(col_quantity, y_pos, col_quantity, y_pos - header_h)
        c.line(col_price, y_pos, col_price, y_pos - header_h)
        c.line(col_sum, y_pos, col_sum, y_pos - header_h)

        c.setStrokeColor(black)
        return header_h

    header_h = draw_table_header(y)
    y -= header_h + 10

    # ---------------------------------------
    # PRODUCT ROWS (Multi-page)
    # ---------------------------------------
    min_y = M_BOTTOM + 140
    toggle = False
    base_font = 12
    line_height_base = 14

    for item in order.items.all():

        # Prepare text before height computation
        raw_name = str(item.product.name)
        product_max_width = (col_product - 10) - col_quantity
        font_size = base_font
        lines = wrap_rtl_text(c, raw_name, product_max_width, "Vazir", font_size)

        # SmartShrink loop (min 8pt, ≤2 lines)
        while len(lines) > 2 and font_size > 8:
            font_size -= 0.5
            lines = wrap_rtl_text(c, raw_name, product_max_width, "Vazir", font_size)

        # Trim if still > 2 lines
        if len(lines) > 2:
            lines = lines[:2]
            if len(lines[1]) > 3:
                lines[1] = lines[1][:-3] + "…"

        line_height = line_height_base * (font_size / base_font)
        row_h = max(28, len(lines) * line_height + 10)

        # PAGE BREAK check uses correct row_h
        if y - row_h < min_y:
            c.setFont("Vazir", 9)
            c.drawCentredString(
                width / 2, M_BOTTOM - 10, arabic_text(f"صفحه {page_number}")
            )
            page_number += 1
            c.showPage()
            y = height - M_TOP
            header_h = draw_table_header(y)
            y -= header_h + 10

        # Zebra background
        if toggle:
            c.setFillColor(HexColor("#f0f0f0"))
            c.rect(table_left, y - row_h, table_width, row_h, fill=1, stroke=0)
        toggle = not toggle
        c.setFillColor(black)

        # Centered baselines
        text_y = y - (row_h / 2) - (base_font * 0.25)

        # --- Product name drawing ---
        c.setFont("Vazir", font_size)
        first_line_y = y - (row_h / 2) + ((len(lines) - 1) * (line_height / 2))
        reshaped_lines = [arabic_text(line) for line in lines]
        for i, line in enumerate(reshaped_lines):
            line_y = first_line_y - (i * line_height)
            c.drawRightString(col_product - 10, line_y, line)

        # --- Quantity (fixed 12pt reset) ---
        c.setFont("Vazir", base_font)
        c.drawCentredString(quantity_center, text_y, str(item.quantity))

        # --- Price ---
        price_clean = arabic_text("{:,.0f}".format(int(item.price)))
        draw_safe_text(
            c,
            price_clean,
            price_center,
            text_y,
            max_width=price_col_width,
            font_name="Vazir",
            base_size=base_font,
            align="center",
        )

        # --- Sum ---
        sum_clean = arabic_text("{:,.0f}".format(int(item.get_cost())))
        draw_safe_text(
            c,
            sum_clean,
            sum_center,
            text_y,
            max_width=sum_col_width,
            font_name="Vazir",
            base_size=base_font,
            align="center",
        )

        # Column lines
        c.setStrokeColor(HexColor("#bbb"))
        c.setLineWidth(0.8)
        c.line(col_quantity, y, col_quantity, y - row_h)
        c.line(col_price, y, col_price, y - row_h)
        c.line(col_sum, y, col_sum, y - row_h)
        c.setStrokeColor(black)

        # Move cursor
        y -= row_h + 2

    # ---------------------------------------
    # TOTALS BOX (Right-aligned labels, Left-aligned values)
    # ---------------------------------------
    y -= 20

    totals_box_h = 130 if order.coupon else 95

    # Draw totals box border
    c.setStrokeColor(HexColor("#999"))
    c.rect(table_left, y - totals_box_h, table_width, totals_box_h, stroke=1, fill=0)

    # Padding inside the box
    right_edge = table_right - 20  # labels anchor (RTL)
    left_edge = table_left + 20  # values anchor (LTR)

    LINE_GAP = 28

    # ---- Subtotal ----
    y -= LINE_GAP
    c.setFont("Vazir-Bold", 14)

    subtotal_value = order.get_total_cost() + order.discount

    label = arabic_text(f"{labels['subtotal_label']} :")
    value = format_price(subtotal_value)

    # Label (right), Value (left)
    c.drawRightString(right_edge, y, label)
    c.drawString(left_edge, y, value)

    # ---- Discount section ----
    if order.coupon:
        # Coupon title
        y -= LINE_GAP
        c.setFont("Vazir", 12)

        label = arabic_text(f"{labels['discount_title']} :")
        value = arabic_text(order.coupon.code)

        c.drawRightString(right_edge, y, label)
        c.drawString(left_edge, y, value)

        # Discount amount
        y -= LINE_GAP - 8

        label = arabic_text(f"{labels['discount_label']} :")
        value = format_price(order.discount)

        c.drawRightString(right_edge, y, label)
        c.drawString(left_edge, y, value)

    # ---- Final amount ----
    y -= LINE_GAP + 5
    c.setFont("Vazir-Bold", 15)

    final_amount = subtotal_value - order.discount

    label = arabic_text(f"{labels['final_amount_title']} :")
    value = format_price(final_amount)

    c.drawRightString(right_edge, y, label)
    c.drawString(left_edge, y, value)

    # ---------------------------------------
    # FOOTER (left: contact info, right: address)
    # ---------------------------------------
    c.setFont("Vazir", 10)
    c.setFillColor(HexColor("#555"))

    # Right side (inside border)
    addr_text = arabic_text("آدرس پیش‌فرض فروشگاه. اینجا را ویرایش کنید.")
    c.drawRightString(width - M_RIGHT, M_BOTTOM + 10, addr_text)

    # Left side (inside border)
    site = arabic_text("وب‌سایت: https://myshop.com")
    email = arabic_text("ایمیل: support@myshop.com")
    phone = arabic_text("تلفن: 021-12345678")

    left_x = M_LEFT + 10
    base_y = M_BOTTOM - 15

    c.drawString(left_x, base_y + 24, site)
    c.drawString(left_x, base_y + 12, email)
    c.drawString(left_x, base_y, phone)

    # ---------------------------------------
    # PAGE NUMBER FOR FINAL PAGE
    # ---------------------------------------
    c.setFont("Vazir", 9)
    c.drawCentredString(width / 2, M_BOTTOM - 10, arabic_text(f"صفحه {page_number}"))

    # ---------------------------------------
    # FINISH (no extra blank page)
    # ---------------------------------------
    c.save()
    buffer.seek(0)
    return buffer


def render_invoice_pdf(request, template_path, context):
    order = context.get("order")

    try:
        pdf_buffer = generate_invoice_pdf(order)
    except Exception as exc:
        return HttpResponse(f"Error generating PDF: {exc}", status=500)

    response = HttpResponse(pdf_buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="invoice-{order.id}.pdf"'

    return response
