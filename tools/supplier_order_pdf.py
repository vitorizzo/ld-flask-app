"""Order sheet patterned after the two-column supplier reference PDF."""
from collections import OrderedDict
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Table, TableStyle, Spacer


def generate_supplier_order_pdf(*, order_id, title, order_date, rows, subgroup_names, quantities, single_page=False, _font_size=9):
    """Return immutable PDF bytes; unselected products keep an empty quantity."""
    output = BytesIO()
    page_width, page_height = landscape(A4)
    margin, gap = 38, 26
    width = (page_width - 2 * margin - gap) / 2
    navy = colors.HexColor('#082664')
    blue = colors.HexColor('#245c8c')
    text = ParagraphStyle('order_text', fontName='Helvetica', fontSize=_font_size, leading=_font_size+1, spaceAfter=0)
    code_style = ParagraphStyle('order_code', parent=text, alignment=TA_RIGHT)
    qty_style = ParagraphStyle('order_qty', parent=code_style, fontName='Helvetica-Bold', textColor=blue)
    header_style = ParagraphStyle('order_header', parent=text, fontName='Helvetica-BoldOblique')
    section_style = ParagraphStyle('order_section', parent=text, fontName='Helvetica-BoldOblique', alignment=TA_CENTER, textColor=colors.white)

    def paragraph(value, style=text):
        return Paragraph(escape(str(value)), style)

    sections = OrderedDict()
    for row in rows:
        name = subgroup_names.get(row.get('subgroup_id'), 'Altri prodotti')
        sections.setdefault(name, []).append(row)
    total = sum(quantities.values())

    def page_header_footer(canvas, document):
        canvas.saveState()
        canvas.setFont('Helvetica-Bold', 11)
        # Wrapped header permits long group/order names without crossing the margin.
        heading = paragraph(title, ParagraphStyle('title', parent=text, fontName='Helvetica-Bold', fontSize=10, leading=11))
        _, height = heading.wrap(page_width - 2 * margin - 130, 50)
        heading.drawOn(canvas, margin, page_height - 24 - height)
        canvas.setFont('Helvetica', 9)
        canvas.drawRightString(page_width - margin, page_height - 35, f'Ordine n. {order_id}')
        canvas.setFillColor(blue)
        canvas.setFont('Helvetica-BoldOblique', 10)
        canvas.drawString(margin, 30, 'Totale confezioni ordinate')
        canvas.drawRightString(margin + width, 30, str(total))
        canvas.setFillColor(colors.black)
        canvas.setFont('Helvetica', 9)
        canvas.drawString(page_width / 2 + gap / 2, 30, 'Data ordine')
        canvas.drawRightString(page_width - margin, 30, order_date.strftime('%d/%m/%Y'))
        canvas.setFont('Helvetica', 7)
        canvas.drawCentredString(page_width / 2, 13, f'Pagina {document.page}')
        canvas.restoreState()

    document = BaseDocTemplate(output, pagesize=(page_width, page_height), title=title, author='LD Enoteca',
                               leftMargin=margin, rightMargin=margin, topMargin=65, bottomMargin=50)
    frames = [Frame(margin, 50, width, page_height - 115, id='left', leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0),
              Frame(margin + width + gap, 50, width, page_height - 115, id='right', leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)]
    document.addPageTemplates(PageTemplate(id='order', frames=frames, onPage=page_header_footer))
    story = []
    for name, products in sections.items():
        data = [[paragraph(name, section_style), '', ''],
                [paragraph('Descrizione', header_style), paragraph('Codice', header_style), paragraph('Quantità', header_style)]]
        for row in products:
            quantity = quantities.get(row['root'])
            data.append([paragraph(row.get('order_description') or row['description']), paragraph(row.get('supplier_code') or '', code_style), paragraph(quantity if quantity is not None else '', qty_style)])
        table = Table(data, colWidths=[width * .65, width * .20, width * .15], repeatRows=2, hAlign='LEFT')
        table.setStyle(TableStyle([
            ('SPAN', (0, 0), (-1, 0)), ('BACKGROUND', (0, 0), (-1, 0), navy),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 3), ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, 0), 4), ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
            ('TOPPADDING', (0, 1), (-1, -1), 1), ('BOTTOMPADDING', (0, 1), (-1, -1), 1),
            ('LINEBELOW', (0, 1), (-1, -1), .4, colors.HexColor('#999999')),
        ]))
        story.extend([table, Spacer(1, 12)])
    document.build(story)
    if single_page and document.page > 1:
        if _font_size <= 7:
            raise ValueError('Il modulo supera una pagina: accorcia le descrizioni per il PDF.')
        return generate_supplier_order_pdf(order_id=order_id,title=title,order_date=order_date,
            rows=rows,subgroup_names=subgroup_names,quantities=quantities,single_page=True,_font_size=_font_size-.5)
    return output.getvalue()
