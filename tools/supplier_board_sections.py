"""Small attribute-free rich text format for supplier card sections."""
from html import escape
from html.parser import HTMLParser
import re

BADGE_COLORS = ('badge_fill', 'badge_text', 'badge_border')


def section_colors(payload, existing=None):
    colors = {}
    for key in BADGE_COLORS:
        value = payload.get(key, getattr(existing, key, None))
        if value is not None:
            if not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
                raise ValueError('Scegli un colore valido per riempimento, testo e cornice (formato #RRGGBB).')
            value = value.lower()
        colors[key] = value
    return colors

DEFAULT_SECTIONS = (
    'Nuove annate', 'Nuovi prodotti', 'Omaggi', 'Anomalia',
    'Variazione di prezzo', 'Controllare Prezzi', 'Contributi', 'Fine Anno',
    'Interventi da ricevere', 'Anomalia Sistemata', 'Consegna Parziale',
)
ALLOWED_TAGS = {'p', 'div', 'br', 'strong', 'b', 'em', 'i', 'u', 's',
                'ul', 'ol', 'li', 'blockquote', 'h3', 'h4'}
BLOCK_TAGS = {'p', 'div', 'br', 'li', 'blockquote', 'h3', 'h4'}
DROP_TAGS = {'script', 'style', 'iframe', 'object', 'svg', 'math', 'template'}


class RichTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output = []; self.text = []; self.stack = []; self.dropped = []

    def handle_starttag(self, tag, attrs):
        if self.dropped:
            if tag in DROP_TAGS: self.dropped.append(tag)
            return
        if tag in DROP_TAGS:
            self.dropped.append(tag); return
        if tag not in ALLOWED_TAGS: return
        if tag in BLOCK_TAGS: self.text.append('\n')
        if len(self.stack) >= 64: return
        self.output.append('<'+tag+'>')
        if tag != 'br': self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag != 'br': self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.dropped:
            if tag in self.dropped:
                self.dropped = self.dropped[:self.dropped.index(tag)]
            return
        if tag not in self.stack: return
        while self.stack:
            current = self.stack.pop(); self.output.append('</'+current+'>')
            if current == tag: break
        if tag in BLOCK_TAGS: self.text.append('\n')

    def handle_data(self, data):
        if not self.dropped:
            self.output.append(escape(data)); self.text.append(data)

    def result(self):
        while self.stack: self.output.append('</'+self.stack.pop()+'>')
        plain = '\n'.join(line.strip() for line in ''.join(self.text).splitlines() if line.strip())
        return (''.join(self.output) if plain else ''), plain


def rich_text(value):
    if not isinstance(value, str) or len(value) > 20000:
        raise ValueError('Il testo di ogni sezione deve essere di massimo 20.000 caratteri.')
    parser = RichTextParser(); parser.feed(value); parser.close()
    return parser.result()


def validate_section(payload):
    if not isinstance(payload, dict): raise ValueError('Dati sezione non validi.')
    name = payload.get('name')
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 80:
        raise ValueError('Inserisci un nome di massimo 80 caratteri.')
    position = payload.get('order_index', 0)
    if type(position) is not int or not 0 <= position <= 10000:
        raise ValueError('Posizione non valida (da 0 a 10.000).')
    return name.strip(), position
