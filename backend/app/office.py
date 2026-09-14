"""Edit supported OOXML content in place; retain layout instead of rebuilding it.

Only an allow-listed relationship graph is exported. Text offsets refer to a
deterministically cleaned source, so text spanning differently styled runs can
be removed without collapsing the surrounding formatting.
"""
from __future__ import annotations

from copy import deepcopy
from io import BytesIO
import posixpath
import re
import unicodedata
import zipfile

from lxml import etree as ET

from .storage import UserError

NS = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    's': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'xdr': 'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'p': 'http://schemas.openxmlformats.org/package/2006/relationships',
    'ct': 'http://schemas.openxmlformats.org/package/2006/content-types',
}
XML_SPACE = '{http://www.w3.org/XML/1998/namespace}space'
REL_BASE = NS['r'] + '/'
ALLOWED = {'officeDocument', 'styles', 'numbering', 'settings', 'fontTable',
           'theme', 'header', 'footer', 'footnotes', 'endnotes', 'worksheet',
           'sharedStrings', 'drawing', 'image', 'table', 'font', 'stylesWithEffects'}
CONTENT = {'document', 'hdr', 'ftr', 'footnotes', 'endnotes'}
WARNING = ('保留原文件的字体、样式与页面设置；敏感文字按原字符位置替换为遮罩。'
           '字体字宽及阅读软件差异仍可能影响自动换行。复核预览为内容视图，不是 Office 打印预览。')


def q(prefix, name):
    return '{' + NS[prefix] + '}' + name


def local(element):
    return ET.QName(element).localname


def remove(element):
    if element.getparent() is not None:
        element.getparent().remove(element)


def unwrap(element):
    parent = element.getparent()
    if parent is not None:
        at = parent.index(element)
        for child in list(element):
            parent.insert(at, child)
            at += 1
        parent.remove(element)


def xml(data):
    return ET.fromstring(data, ET.XMLParser(resolve_entities=False, no_network=True,
                                          remove_comments=True, remove_pis=True))


def encoded(root):
    return ET.tostring(root, encoding='UTF-8', xml_declaration=True, standalone=True)


def rel_path(name):
    return posixpath.join(posixpath.dirname(name), '_rels', posixpath.basename(name) + '.rels')


def resolve(owner, target):
    if '\\' in target or ':' in target or '?' in target or '#' in target:
        raise UserError('Office 关联路径不受支持，请先另存为标准 Office 文件。')
    value = posixpath.normpath(posixpath.join(posixpath.dirname(owner), target)) if not target.startswith('/') else target[1:]
    if value.startswith('../') or value in ('..', '.'):
        raise UserError('Office 关联路径超出文件包。')
    return value


def mask_text(text, findings):
    """Keep character count, whitespace and run boundaries; never retain originals."""
    chars = list(text)
    for finding in findings:
        if finding.get('keep'):
            continue
        for i in range(finding['start'], finding['end']):
            if not chars[i].isspace():
                chars[i] = '■' if unicodedata.east_asian_width(chars[i]) in ('W', 'F') else '*'
    return ''.join(chars)


def patch_nodes(nodes, before, after):
    if len(before) != len(after):
        raise UserError('保留格式导出需要等长文字映射，请重新识别文件。')
    cursor = 0
    for node, value in nodes:
        length = len(value)
        updated = after[cursor:cursor + length]
        if updated != value:
            node.text = updated
            node.set(XML_SPACE, 'preserve')
        cursor += length
    if cursor != len(before):
        raise UserError('原文件文字映射已失效，请重新识别。')


class Package:
    def __init__(self, data, extension):
        from .formats import package
        self.extension = extension
        self.main = 'word/document.xml' if extension == 'docx' else 'xl/workbook.xml'
        self.parts, self.rels, self.roots = {}, {}, {}
        with package(data, extension) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or any('\\' in n for n in names):
                raise UserError('Office 包含重复或非标准文件路径。')
            if any('/charts/' in n or '/diagrams/' in n for n in names):
                raise UserError('Office 含图表或 SmartArt，请先转换为 PDF 后处理。')
            self.types = xml(archive.read('[Content_Types].xml'))
            pending = [self.main]
            while pending:
                name = pending.pop(0)
                if name in self.parts:
                    continue
                if name not in names:
                    raise UserError('Office 缺少关联内容。')
                self.parts[name] = archive.read(name)
                if name.endswith('.xml'):
                    self.roots[name] = xml(self.parts[name])
                relations = []
                if rel_path(name) in names:
                    ids = set()
                    for relation in xml(archive.read(rel_path(name))):
                        if not relation.get('Id') or relation.get('Id') in ids:
                            raise UserError('Office 包含重复或空的关联标识。')
                        ids.add(relation.get('Id'))
                        relation_type = relation.get('Type', '')
                        kind = relation_type.removeprefix(REL_BASE)
                        if relation_type == 'http://schemas.microsoft.com/office/2007/relationships/stylesWithEffects':
                            kind = 'stylesWithEffects'
                        if relation.get('TargetMode') == 'External':
                            if kind in ('image', 'drawing'):
                                raise UserError('Office 含外链图片，请先嵌入图片。')
                            continue
                        if kind not in ALLOWED:
                            continue
                        target = resolve(name, relation.get('Target', ''))
                        relations.append({'id': relation.get('Id'), 'kind': kind, 'type': relation_type, 'target': target})
                        pending.append(target)
                self.rels[name] = relations
        expected = q('w', 'document') if extension == 'docx' else q('s', 'workbook')
        if self.roots[self.main].tag != expected:
            raise UserError('暂不支持 Strict OOXML，请另存为标准 DOCX/XLSX。')
        self.warnings = [WARNING]
        self._clean()
        self._validate_graph()

    def _validate_graph(self):
        expected = {
            'header': q('w', 'hdr'), 'footer': q('w', 'ftr'),
            'footnotes': q('w', 'footnotes'), 'endnotes': q('w', 'endnotes'),
            'styles': q('w', 'styles') if self.extension == 'docx' else q('s', 'styleSheet'),
            'stylesWithEffects': q('w', 'styles'), 'numbering': q('w', 'numbering'),
            'settings': q('w', 'settings'), 'fontTable': q('w', 'fonts'),
            'theme': q('a', 'theme'), 'worksheet': q('s', 'worksheet'),
            'sharedStrings': q('s', 'sst'), 'drawing': q('xdr', 'wsDr'), 'table': q('s', 'table'),
        }
        for name, relations in self.rels.items():
            for relation in relations:
                kind, target = relation['kind'], relation['target']
                if kind in expected and (target not in self.roots or self.roots[target].tag != expected[kind]):
                    raise UserError('Office 关联内容类型不受支持，请先另存为标准静态文件。')
            root = self.roots.get(name)
            if root is None:
                continue
            identifiers = {r['id'] for r in relations}
            for node in root.iter():
                for attr, value in node.attrib.items():
                    if attr.startswith('{' + NS['r'] + '}') and value not in identifiers:
                        raise UserError('Office 包含无法保留的关联对象，请先转换为 PDF。')
                if local(node) == 'imagedata' and not node.get(q('r', 'id')):
                    raise UserError('Word 含不支持的旧式图片引用，请先转换为 PDF。')

    def _clean(self):
        word_drop = {'del', 'delText', 'moveFrom', 'commentRangeStart', 'commentRangeEnd',
                     'commentReference', 'annotationRef', 'bookmarkStart', 'bookmarkEnd',
                     'proofErr', 'permStart', 'permEnd', 'sdtPr', 'sdtEndPr',
                     'customXmlPr', 'smartTagPr', 'dataBinding', 'docVars', 'rsids',
                     'mailMerge', 'attachedTemplate', 'trackRevisions', 'docId',
                     'people', 'printerSettings', 'saveThroughXslt'}
        sheet_drop = {'extLst', 'hyperlinks', 'legacyDrawing', 'legacyDrawingHF',
                      'oleObjects', 'controls', 'webPublishItems', 'externalReferences',
                      'dataValidations', 'conditionalFormatting', 'connections',
                      'customWorkbookViews', 'customSheetViews', 'cellWatch',
                      'smartTags', 'phoneticPr', 'rPh'}
        for name, root in self.roots.items():
            for node in list(root.iter()):
                tag = local(node)
                if self.extension == 'xlsx' and tag == 'legacyDrawingHF':
                    raise UserError('Excel 含旧式页眉页脚图片，请先转换为 PDF。')
                if self.extension == 'docx':
                    if tag in ('altChunk', 'object', 'oMath', 'oMathPara', 'subDoc'):
                        raise UserError('Word 含无法完整复核的公式或嵌入对象，请先转换为 PDF。')
                    if node.tag.startswith('{' + NS['w'] + '}') and (tag in word_drop or tag.endswith('PrChange')):
                        remove(node)
                    if node.tag == q('w', 'r') and any(is_on(node.find('./' + q('w', 'rPr') + '/' + q('w', t))) for t in ('vanish', 'webHidden', 'specVanish')):
                        remove(node)
                    if node.tag in (q('w', 'ins'), q('w', 'moveTo'), q('w', 'hyperlink'), q('w', 'smartTag'), q('w', 'customXml')):
                        unwrap(node)
                    if node.tag == q('w', 'sdt'):
                        content = node.find(q('w', 'sdtContent'))
                        if content is not None:
                            for child in list(content):
                                node.append(child)
                        remove(content) if content is not None else None
                        unwrap(node)
                elif tag in sheet_drop:
                    if tag in ('conditionalFormatting', 'dataValidations'):
                        self.warnings.append('条件格式与数据验证已移除；静态单元格样式保留。')
                    remove(node)
                if self.extension == 'xlsx' and tag == 'pageSetup':
                    # Vendor printer blobs are not carried over; standardized
                    # paper/orientation/scale/margins remain on the XML element.
                    node.attrib.pop(q('r', 'id'), None)
                # Alternative descriptions and editing identities are not visible text.
                for attr in list(node.attrib):
                    key = ET.QName(attr).localname
                    if key in ('author', 'initials', 'date', 'descr', 'title', 'paraId', 'textId') or key.startswith('rsid'):
                        del node.attrib[attr]
                if tag in ('docPr', 'cNvPr'):
                    node.set('name', 'Image ' + node.get('id', '1'))
                    for child in list(node):
                        if local(child).startswith('hlink'):
                            remove(child)
            if self.extension == 'docx':
                self._clean_fields(root)
                # A hidden inherited style must not carry its text into the output.
                hidden = set()
                style_nodes = {}
                for styles in self.roots.values():
                    for style in styles.iter(q('w', 'style')):
                        style_nodes[style.get(q('w', 'styleId'))] = style
                        if any(is_on(style.find('./' + q('w', 'rPr') + '/' + q('w', t))) for t in ('vanish', 'webHidden', 'specVanish')):
                            hidden.add(style.get(q('w', 'styleId')))
                for _ in range(len(style_nodes)):
                    previous = len(hidden)
                    for identifier, style in style_nodes.items():
                        base = style.find(q('w', 'basedOn'))
                        override = style.find('./' + q('w', 'rPr') + '/' + q('w', 'vanish'))
                        if base is not None and base.get(q('w', 'val')) in hidden and override is None:
                            hidden.add(identifier)
                    if previous == len(hidden):
                        break
                for node in list(root.iter()):
                    if node.tag in (q('w', 'p'), q('w', 'r')) and any(s.get(q('w', 'val')) in hidden for s in node.iter() if s.tag in (q('w', 'pStyle'), q('w', 'rStyle'))):
                        remove(node)
            if name.endswith('/settings.xml'):
                allowed = {'zoom', 'defaultTabStop', 'characterSpacingControl', 'evenAndOddHeaders',
                           'compat', 'themeFontLang', 'clrSchemeMapping', 'decimalSymbol',
                           'listSeparator', 'footnotePr', 'endnotePr', 'mirrorMargins', 'gutterAtTop',
                           'autoHyphenation', 'consecutiveHyphenLimit', 'hyphenationZone',
                           'doNotHyphenateCaps', 'displayBackgroundShape'}
                for node in list(root):
                    if local(node) not in allowed:
                        remove(node)
        self.warnings.append('移除批注、修订历史、隐藏文字、外部链接和文档属性；恢复包仍可精确还原原件。')

    def _clean_fields(self, root):
        # Only page numbering has a safe, predictable field instruction. Other
        # fields retain their displayed result but cannot update to secret data.
        safe = re.compile(r'^\s*(PAGE|NUMPAGES|SECTIONPAGES)\s*(?:\\\*\s+(?:MERGEFORMAT|Arabic|ROMAN|roman))?\s*$', re.I)
        instructions = list(root.iter(q('w', 'instrText')))
        if any(not safe.fullmatch(n.text or '') for n in instructions):
            for node in list(root.iter()):
                if node.tag in (q('w', 'instrText'), q('w', 'fldChar')):
                    remove(node)
        for node in list(root.iter(q('w', 'fldSimple'))):
            if not safe.fullmatch(node.get(q('w', 'instr'), '')):
                unwrap(node)

    def graph(self):
        visited, pending = set(), [self.main]
        while pending:
            name = pending.pop()
            if name not in visited:
                visited.add(name)
                pending.extend(r['target'] for r in self.rels.get(name, []) if r['target'] in self.parts)
        return visited

    def write(self, images, read_image):
        kept = self.graph()
        renames = {name: posixpath.join(posixpath.dirname(name), f'redacted-{i}.png') for i, name in enumerate(images)}
        for name in kept:
            if name not in self.roots and name not in images:
                raise UserError('Office 含无法检查的二进制附加内容，请先转换为 PDF。')
        types = ET.Element(q('ct', 'Types'), nsmap={None: NS['ct']})
        ET.SubElement(types, q('ct', 'Default'), Extension='rels', ContentType='application/vnd.openxmlformats-package.relationships+xml')
        defaults = {n.get('Extension'): n.get('ContentType') for n in self.types if local(n) == 'Default'}
        overrides = {n.get('PartName').lstrip('/'): n.get('ContentType') for n in self.types if local(n) == 'Override'}
        out = BytesIO()
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name in sorted(kept):
                output_name = renames.get(name, name)
                mime = 'image/png' if name in images else overrides.get(name, defaults.get(name.rsplit('.', 1)[-1]))
                if not mime:
                    raise UserError('Office 内容类型缺失。')
                ET.SubElement(types, q('ct', 'Override'), PartName='/' + output_name, ContentType=mime)
                data = read_image(images[name]) if name in images else encoded(self.roots[name])
                archive.writestr(output_name, data)
                rels = ET.Element(q('p', 'Relationships'), nsmap={None: NS['p']})
                for relation in self.rels.get(name, []):
                    if relation['target'] in kept:
                        target = renames.get(relation['target'], relation['target'])
                        ET.SubElement(rels, q('p', 'Relationship'), Id=relation['id'],
                                      Type=relation['type'],
                                      Target=posixpath.relpath(target, posixpath.dirname(name)))
                if len(rels):
                    archive.writestr(rel_path(name), encoded(rels))
            top = ET.Element(q('p', 'Relationships'), nsmap={None: NS['p']})
            ET.SubElement(top, q('p', 'Relationship'), Id='rId1', Type=REL_BASE + 'officeDocument', Target=self.main)
            archive.writestr('_rels/.rels', encoded(top))
            archive.writestr('[Content_Types].xml', encoded(types))
        return out.getvalue()


def word_segments(paragraph):
    result = []
    for node in paragraph.iter():
        # Nested text boxes have their own paragraphs and their own offsets.
        if next((p for p in node.iterancestors() if p.tag == q('w', 'p')), None) is not paragraph:
            continue
        if node.tag == q('w', 't'):
            result.append((node, node.text or ''))
        elif node.tag == q('w', 'tab'):
            result.append((node, '\t'))
        elif node.tag in (q('w', 'br'), q('w', 'cr')):
            result.append((node, '\n'))
    return result


def is_on(node):
    return node is not None and node.get(q('w', 'val'), '1').lower() not in ('0', 'false', 'off')


def strings(element):
    return [(n, n.text or '') for n in element.iter(q('s', 't'))]


def header_chunks(value):
    # Keep Excel's font/size/color/position/page-number control sequences intact.
    spans, cursor = [], 0
    controls = r'&(?:"[^"]*"|K[0-9A-Fa-f]{6}|[0-9]{1,3}|[A-Za-z&+\-])'
    for match in re.finditer(controls, value):
        if cursor < match.start():
            spans.append((cursor, match.start()))
        cursor = match.end()
    if cursor < len(value):
        spans.append((cursor, len(value)))
    return spans


def prepare(data, extension, add_image, previous=None, texts=None):
    from .formats import load_image
    pack = Package(data, extension)
    blocks, layout, bindings = [], [], []
    images = {}

    def block(value, label, nodes=None, context='', attribute=None):
        ref = f'b{len(blocks)}'
        blocks.append({'id': ref, 'text': value, 'label': label, 'context': context})
        if texts is not None:
            if len(blocks) > len(previous['blocks']) or previous['blocks'][len(blocks)-1] != blocks[-1]:
                raise UserError('原文件文字映射已改变，请重新识别。')
            if attribute is not None:
                node, attr = attribute
                node.set(attr, texts[ref])
            elif nodes is not None:
                patch_nodes(nodes, value, texts[ref])
        bindings.append(ref)
        return ref

    if extension == 'docx':
        for name, root in pack.roots.items():
            if local(root) in CONTENT:
                for index, paragraph in enumerate(root.iter(q('w', 'p'))):
                    nodes = word_segments(paragraph)
                    value = ''.join(v for _, v in nodes)
                    label = ('正文' if name == pack.main else {'hdr': '页眉', 'ftr': '页脚', 'footnotes': '脚注', 'endnotes': '尾注'}.get(local(root), '文字')) + f' / 段落 {index+1}'
                    layout.append({'kind': 'p', 'block': block(value, label, nodes)})
            if local(root) == 'numbering':
                for node in root.iter(q('w', 'lvlText')):
                    value = node.get(q('w', 'val'), '')
                    # Numbering labels can contain user-written sensitive text.
                    if value and not re.fullmatch(r'[%0-9.()、\s\-•\uf0b7]+', value):
                        layout.append({'kind': 'p', 'block': block(value, '列表编号文字', attribute=(node, q('w', 'val')))})
    else:
        _spreadsheet(pack, block, layout)

    # Every retained image is re-encoded and reviewed; no orphan original media
    # or thumbnails are copied to the new package.
    for name in sorted(pack.graph()):
        if name not in pack.roots:
            if not any(r['target'] == name and r['kind'] == 'image' for rels in pack.rels.values() for r in rels):
                raise UserError('Office 含不支持的字体或二进制对象，请先转换为 PDF。')
            if previous is None:
                images[name] = add_image(load_image(pack.parts[name]))
            else:
                images[name] = previous['office_images'][name]
    document = {'blocks': blocks, 'layout': layout, 'warnings': list(dict.fromkeys(pack.warnings)),
                'office_layout_version': 1, 'office_images': images}
    if previous is not None and len(previous['blocks']) != len(blocks):
        raise UserError('原文件文字映射已改变，请重新识别。')
    return document, pack


def _spreadsheet(pack, block, layout):
    from openpyxl.utils.cell import coordinate_to_tuple, get_column_letter
    workbook = pack.roots[pack.main]
    sheets = workbook.find(q('s', 'sheets'))
    relations = {r['id']: r for r in pack.rels[pack.main]}
    shared = next((root for root in pack.roots.values() if root.tag == q('s', 'sst')), None)
    shared_values = list(shared) if shared is not None else []
    total, visible = 0, 0
    original_names = [s.get('name') for s in sheets]
    active_indices = {}
    rename = {}
    for old_index, sheet in enumerate(list(sheets)):
        rid = sheet.get(q('r', 'id'))
        if sheet.get('state', 'visible') != 'visible':
            remove(sheet)
            pack.rels[pack.main] = [r for r in pack.rels[pack.main] if r['id'] != rid]
            pack.warnings.append('隐藏工作表已排除，不写入成品。')
            continue
        if rid not in relations:
            raise UserError('工作表关联信息缺失。')
        name = relations[rid]['target']
        ws = pack.roots[name]
        if ws.tag != q('s', 'worksheet'):
            raise UserError('暂不支持图表工作表，请先转换为 PDF。')
        active_indices[old_index] = visible
        visible += 1
        title = sheet.get('name')
        name_ref = block(title, '工作表名称', attribute=(sheet, 'name'))
        # Worksheet names have additional syntax constraints, including '*'.
        new_name = sheet.get('name').replace('*', '■')
        used = set(rename.values())
        if new_name in used:
            suffix = f'_{visible}'
            new_name = new_name[:31-len(suffix)] + suffix
        sheet.set('name', new_name)
        rename[title] = new_name
        cells, images, widths = [], [], {}
        hidden_columns = []
        for col in ws.iter(q('s', 'col')):
            if col.get('hidden') in ('1', 'true'):
                hidden_columns.append((int(col.get('min')), int(col.get('max'))))
            if col.get('width'):
                widths[get_column_letter(int(col.get('min')))] = float(col.get('width'))
        header_context = {}
        for row in ws.iter(q('s', 'row')):
            hidden_row = row.get('hidden') in ('1', 'true')
            for cell in row.findall(q('s', 'c')):
                coordinate = cell.get('r', '')
                r, c = coordinate_to_tuple(coordinate)
                if hidden_row or any(a <= c <= b for a, b in hidden_columns):
                    for item in list(cell):
                        remove(item)
                    cell.attrib.pop('t', None)
                    pack.warnings.append('隐藏行列内容已清除，行列位置和尺寸保留。')
                    continue
                value = cell.find(q('s', 'v'))
                inline = cell.find(q('s', 'is'))
                formula = cell.find(q('s', 'f'))
                if formula is not None:
                    if value is None or value.text is None:
                        raise UserError('Excel 公式没有可靠的缓存值，请在 Excel 中计算并保存后重新上传。')
                    remove(formula)
                    pack.warnings.append('公式固定为保存时的静态缓存值；数字、日期格式保留。')
                if cell.get('t') == 's':
                    if value is None or value.text is None or not value.text.isdigit() or int(value.text) >= len(shared_values):
                        raise UserError('Excel 共享字符串索引无效。')
                    inline = deepcopy(shared_values[int(value.text)])
                    inline.tag = q('s', 'is')
                    remove(value)
                    cell.append(inline)
                    cell.set('t', 'inlineStr')
                    value = None
                nodes = strings(inline) if inline is not None else ([(value, value.text or '')] if value is not None else [])
                if not nodes:
                    continue
                text = ''.join(v for _, v in nodes)
                total += 1
                if total > 200000 or r > 100000 or c > 1000:
                    raise UserError('Excel 使用区域超过本版本上限，请拆分工作簿。')
                ref = block(text, f'工作表 {visible} / {coordinate}', nodes, header_context.get(c, '') if r > 1 else '')
                after = ''.join(n.text or '' for n, _ in nodes)
                if r == 1:
                    header_context[c] = text
                # A masked numeric/date cell must become text, preserving its
                # style index so borders, alignment and fonts remain unchanged.
                if after != text and inline is None:
                    remove(value)
                    inline = ET.SubElement(cell, q('s', 'is'))
                    ET.SubElement(inline, q('s', 't')).text = after
                    cell.set('t', 'inlineStr')
                cells.append({'row': r, 'col': c, 'block': ref, 'value': text, 'format': 'General'})
        for hf in ws.iter(q('s', 'headerFooter')):
            for node in hf:
                raw = node.text or ''
                spans = header_chunks(raw)
                for index, (start, end) in enumerate(spans):
                    # Only literal text is included; format codes are preserved.
                    value = raw[start:end]
                    temp = ET.Element('text')
                    temp.text = value
                    ref = block(value, f'工作表 {visible} / 页眉页脚 {index+1}', [(temp, value)])
                    raw = raw[:start] + temp.text + raw[end:]
                    cells.append({'row': 0, 'col': 0, 'block': ref, 'value': value, 'format': 'General'})
                node.text = raw
        layout.append({'name': name_ref, 'cells': cells, 'images': images, 'widths': widths})
    if not visible:
        raise UserError('工作簿中没有可见工作表。')
    # Shared strings (including unused and hidden originals) are fully removed.
    pack.rels[pack.main] = [r for r in pack.rels[pack.main] if r['kind'] != 'sharedStrings']
    for view in workbook.iter(q('s', 'workbookView')):
        for key in ('activeTab', 'firstSheet'):
            if key in view.attrib:
                view.set(key, str(active_indices.get(int(view.get(key)), 0)))
    for names in workbook.findall(q('s', 'definedNames')):
        for item in list(names):
            index = int(item.get('localSheetId', '-1'))
            if item.get('name') not in ('_xlnm.Print_Area', '_xlnm.Print_Titles', '_xlnm._FilterDatabase') or index not in active_indices:
                remove(item)
                continue
            old, new = original_names[index], rename[original_names[index]]
            value = item.text or ''
            value = value.replace("'" + old.replace("'", "''") + "'!", "'" + new.replace("'", "''") + "'!")
            if old != new:
                value = value.replace(old + '!', "'" + new.replace("'", "''") + "'!")
            item.text = value
            item.set('localSheetId', str(active_indices[index]))
    for name in sorted(pack.graph()):
        root = pack.roots.get(name)
        if root is None:
            continue
        if local(root) == 'wsDr' and any(local(n) in ('sp', 'graphicFrame', 'grpSp', 'cxnSp') for n in root.iter()):
            raise UserError('Excel 含非图片绘图对象，请先转换为 PDF。')
        if local(root) == 'table':
            # Table headers may duplicate cell content in attributes.
            for column in root.iter(q('s', 'tableColumn')):
                for attribute in ('name', 'totalsRowLabel'):
                    if attribute in column.attrib:
                        value = column.get(attribute)
                        ref = block(value, '表格列标题/汇总标签', attribute=(column, attribute))
                        layout[-1]['cells'].append({'row': 0, 'col': 0, 'block': ref, 'value': value, 'format': 'General'})
            for node in list(root.iter()):
                if local(node) in ('calculatedColumnFormula', 'totalsRowFormula'):
                    remove(node)
            root.set('name', 'Table' + root.get('id', '1'))
            root.set('displayName', root.get('name'))
        if local(root) == 'styleSheet':
            for fmt in root.iter(q('s', 'numFmt')):
                code = fmt.get('formatCode', '')
                for match in list(re.finditer(r'"([^"]*)"', code)):
                    value = match.group(1)
                    temp = ET.Element('text')
                    temp.text = value
                    ref = block(value, '数字格式中的文字', [(temp, value)])
                    code = code[:match.start(1)] + temp.text + code[match.end(1):]
                    layout[-1]['cells'].append({'row': 0, 'col': 0, 'block': ref, 'value': value, 'format': 'General'})
                fmt.set('formatCode', code)


def parse(data, extension, add_image):
    return prepare(data, extension, add_image)[0]


def export(data, document, extension, texts, read_image):
    if document.get('office_layout_version') != 1:
        raise UserError('此任务使用旧版排版方案，请重新上传并识别后导出。')
    current, pack = prepare(data, extension, None, document, texts)
    return pack.write(current['office_images'], read_image), 0
