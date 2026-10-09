"""Printable customer communications; ledger rows always come from the server."""
from datetime import datetime
from decimal import Decimal
from html import escape
from io import BytesIO
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from tools.customer_account_rows import open_account_entries
from tools.customer_credit_templates import TOKEN


def money(value):
    return f'{Decimal(value or 0):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.') + ' €'


def default_template(kind):
    reminder = kind == 'reminder'
    return dict(subject=('Sollecito di pagamento' if reminder else 'Estratto conto aggiornato') + ' - {{cliente}}',
                body='Spett.le {{cliente}},\n\n' + (
                    'Vi chiediamo cortesemente di provvedere al saldo delle partite aperte o di segnalarci eventuali difformità.'
                    if reminder else 'Trasmettiamo la situazione contabile aggiornata risultante dai nostri archivi.') +
                '\n\nSaldo attuale: {{saldo}}\n\n{{partite}}\n\nPer chiarimenti potete rispondere a questa comunicazione.\n\nCordiali saluti\nLD Enoteca')


def communication_pdf(kind, customer, entries, balance, template=None):
    data = template or default_template(kind)
    values = dict(cliente=customer.customer_name or '', codice_cliente=customer.source_customer_code, saldo=money(balance))
    subject = TOKEN.sub(lambda match: str(values[match.group(1)]), data['subject'])
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=42, bottomMargin=42)
    styles = getSampleStyleSheet()
    normal = ParagraphStyle('CreditBody', parent=styles['Normal'], fontSize=10, leading=14, spaceAfter=8)
    cell = ParagraphStyle('CreditCell', parent=normal, fontSize=8, leading=11, spaceAfter=0, splitLongWords=True)
    amount_style = ParagraphStyle('CreditAmount', parent=cell, alignment=TA_RIGHT)
    def paragraph(value, style=normal):
        return Paragraph(escape(str(value or '')).replace('\n', '<br/>'), style)
    story = [paragraph('LD Enoteca', styles['Title']), paragraph(subject, styles['Heading2']),
             paragraph('Codice cliente: ' + customer.source_customer_code + ' - Situazione al ' + datetime.now(ZoneInfo('Europe/Rome')).strftime('%d/%m/%Y')), Spacer(1, 10)]
    # Split around the mandatory ledger placeholder without interpreting user HTML.
    parts = TOKEN.split(data['body'])
    text = ''
    for index, part in enumerate(parts):
        if index % 2 == 0:
            text += part
        elif part == 'partite':
            if text.strip(): story.append(paragraph(text.strip()))
            text = ''
            rows = [[paragraph(label, cell) for label in ('Data', 'Documento', 'Descrizione', 'Importo')]]
            for entry in open_account_entries(entries):
                ref = entry.document_date or entry.registration_date or entry.due_date
                rows.append([paragraph(ref.strftime('%d/%m/%Y') if ref else '-', cell), paragraph(entry.document_number or '-', cell),
                             paragraph(entry.description or '-', cell), paragraph(money(entry.signed_amount), amount_style)])
            if len(rows) == 1:
                story.append(paragraph('Nessuna partita aperta.'))
            else:
                table = Table(rows, colWidths=[64, 88, doc.width - 235, 83], repeatRows=1, hAlign='LEFT', splitInRow=1)
                table.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), colors.HexColor('#e8edf2')),
                    ('VALIGN', (0,0), (-1,-1), 'TOP'), ('GRID', (0,0), (-1,-1), .4, colors.HexColor('#b6c0cc')),
                    ('TOPPADDING',(0,0),(-1,-1),6), ('BOTTOMPADDING',(0,0),(-1,-1),6)]))
                story.extend([table, Spacer(1,14)])
        else:
            text += str(values[part])
    if text.strip(): story.append(paragraph(text.strip()))
    def footer(canvas, document):
        canvas.setFont('Helvetica', 8)
        canvas.drawRightString(A4[0]-36, 24, f'Pagina {document.page}')
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return subject, output.getvalue()
