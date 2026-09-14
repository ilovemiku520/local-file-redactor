"""Bounded parsers, content previews and format-preserving native export."""
from __future__ import annotations
import csv
from io import BytesIO, StringIO
import math
import os
from pathlib import Path
import re
import zipfile
from PIL import Image, ImageOps, ImageDraw, ImageFont
from lxml import etree
from .storage import ROOT, UserError

FORMATS = {'txt':['txt'],'csv':['csv'],'docx':['docx','pdf'],'xlsx':['xlsx','pdf'],
           'pdf':['pdf'], **{x:['png','jpg','jpeg','webp','bmp'] for x in ('png','jpg','jpeg','webp','bmp')}}
IMAGE_FORMATS = {'PNG','JPEG','WEBP','BMP'}
MAX_PIXELS = 40_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


def text_decode(data):
    if len(data)>8_000_000:
        raise UserError('文本/CSV 超过 800 万字节，请拆分后处理。')
    if data.startswith((b'\xff\xfe', b'\xfe\xff')):
        return data.decode('utf-16'), 'UTF-16'
    for encoding in ('utf-8-sig','gb18030'):
        try:
            text=data.decode(encoding)
            if '\x00' in text:
                raise UserError('文件包含二进制内容，不能作为文本处理。')
            return text, encoding
        except UnicodeError:
            continue
    raise UserError('无法识别文本编码，请先另存为 UTF-8。')


def load_image(data):
    with Image.open(BytesIO(data)) as source:
        if source.format not in IMAGE_FORMATS or getattr(source,'n_frames',1) != 1:
            raise UserError('仅支持单帧 PNG、JPEG、WebP、BMP 图片。')
        if source.width * source.height > MAX_PIXELS:
            raise UserError('图片超过 4000 万像素上限。')
        fixed = ImageOps.exif_transpose(source).convert('RGBA')
        background = Image.new('RGBA', fixed.size, 'white')
        background.alpha_composite(fixed)
        return background.convert('RGB')


def image_bytes(image, extension='png'):
    out=BytesIO()
    options={'quality':95,'subsampling':0} if extension in ('jpg','jpeg') else ({'lossless':True} if extension=='webp' else {})
    image.convert('RGB').save(out,format={'jpg':'JPEG','jpeg':'JPEG'}.get(extension,extension.upper()),**options)
    return out.getvalue()


def package(data, extension):
    if not data.startswith(b'PK'):
        raise UserError('文件内容与 Office 扩展名不匹配。')
    try:
        archive=zipfile.ZipFile(BytesIO(data))
        members=archive.infolist()
        if len(members)>10000 or sum(i.file_size for i in members)>512*1024**2:
            raise UserError('Office 文件解压规模超过限制。')
        for item in members:
            if item.filename.startswith(('/', '\\')) or '..' in Path(item.filename).parts or ':' in item.filename:
                raise UserError('Office 文件包含异常路径。')
            if item.file_size>1024**2 and item.file_size/max(item.compress_size,1)>500:
                raise UserError('Office 文件压缩比异常。')
            lower=item.filename.lower()
            if any(x in lower for x in ('vbaproject','/embeddings/','/activex/','/externallinks/')):
                raise UserError('文件含宏、嵌入对象或外部数据，请先另存为静态文档。')
            if lower.endswith(('.xml','.rels')):
                content=archive.read(item)
                if b'<!DOCTYPE' in content.upper() or b'<!ENTITY' in content.upper():
                    raise UserError('XML 文件包含不允许的实体声明。')
                etree.fromstring(content,parser=etree.XMLParser(resolve_entities=False,no_network=True))
        expected='word/document.xml' if extension=='docx' else 'xl/workbook.xml'
        if expected not in archive.namelist():
            raise UserError('Office 文件类型不匹配。')
        return archive
    except (zipfile.BadZipFile,etree.XMLSyntaxError) as exc:
        raise UserError('Office 文件损坏或格式不受支持。') from exc


def csv_safe(value):
    if re.fullmatch(r'\s*-?\d+(?:\.\d+)?\s*',value):
        return value,False
    candidate=value.lstrip(' \r\n\t')
    if candidate.startswith(('=','+','-','@')) or value.startswith(('\t','\r','\n')):
        return "'"+value,True
    return value,False


def parse(data, extension, add_image):
    blocks,layout,warnings=[],[],[]
    def block(text, label='', context=''):
        index=len(blocks)
        blocks.append({'id':f'b{index}','text':str(text),'label':label,'context':context})
        return f'b{index}'
    if extension=='txt':
        text,encoding=text_decode(data)
        # Preserve exact separators while keeping each source block manageable.
        parts=re.findall(r'[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+$',text) or ['']
        for index,part in enumerate(parts):
            layout.append({'kind':'p','block':block(part,f'段落 {index+1}')})
        return {'blocks':blocks,'layout':layout,'warnings':warnings,'encoding':encoding}
    if extension=='csv':
        text,encoding=text_decode(data)
        try:
            dialect=csv.Sniffer().sniff(text[:8192],delimiters=',;\t|')
            delimiter=dialect.delimiter
        except csv.Error:
            delimiter=','
        rows=list(csv.reader(StringIO(text,newline=''),delimiter=delimiter,strict=True))
        if sum(len(row) for row in rows)>200000:
            raise UserError('CSV 超过 20 万单元格上限。')
        refs=[]
        for r,row in enumerate(rows):
            refs.append([block(value,f'第 {r+1} 行 / 第 {c+1} 列',rows[0][c] if r and c<len(rows[0]) else '') for c,value in enumerate(row)])
        return {'blocks':blocks,'layout':refs,'warnings':warnings,'delimiter':delimiter,'encoding':encoding}
    if extension in ('docx','xlsx'):
        from . import office
        return office.parse(data,extension,add_image)
    raise UserError('该格式不使用文本解析器。')


def native_export(document, extension, texts, read_image, original=None):
    out=BytesIO()
    changed=0
    if extension=='txt':
        return ''.join(texts[item['block']] for item in document['layout']).encode('utf-8'),0
    if extension=='csv':
        stream=StringIO(newline='')
        writer=csv.writer(stream,delimiter=document['delimiter'])
        for row in document['layout']:
            safe=[csv_safe(texts[ref]) for ref in row]
            changed+=sum(v[1] for v in safe)
            writer.writerow([v[0] for v in safe])
        return stream.getvalue().encode('utf-8-sig'),changed
    if extension in ('docx','xlsx'):
        from . import office
        if original is None:
            raise UserError('保留格式导出需要原文件，请重新识别。')
        return office.export(original,document,extension,texts,read_image)
    raise UserError('无法生成指定格式。')


def text_pages(document, extension):
    """Explicit simplified previews: wrapping, no silent row or column truncation."""
    records=[]
    if extension=='csv':
        for row in document['layout']:
            records.extend(row)
    elif extension=='xlsx':
        for sheet in document['layout']:
            records.append(sheet['name'])
            records.extend(item['block'] for item in sheet['cells'])
    else:
        def walk(nodes):
            for item in nodes:
                if item['kind']=='p':
                    records.append(item['block'])
                elif item['kind']=='table':
                    for row in item['rows']:
                        for cell in row:
                            walk(cell)
        walk(document['layout'])
    lookup={item['id']:item for item in document['blocks']}
    font_path=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/msyh.ttc'
    font=ImageFont.truetype(str(font_path),24)
    image=Image.new('RGB',(1240,1754),'white')
    draw=ImageDraw.Draw(image)
    y=55
    refs=[]
    for ref in records:
        text=lookup[ref]['text']
        value=(lookup[ref]['label']+'  '+text).replace('\r\n','\n').replace('\r','\n')
        line=''
        for character in value+'\n':
            if character=='\n' or draw.textlength(line+character,font=font)>1120:
                if y>1670:
                    yield image,list(dict.fromkeys(refs))
                    image=Image.new('RGB',(1240,1754),'white');draw=ImageDraw.Draw(image);y=55;refs=[]
                draw.text((55,y),line,font=font,fill='#243042')
                refs.append(ref)
                y+=34
                line='' if character=='\n' else character
            else:
                line+=character
        y+=12
    if refs or not records:
        yield image,list(dict.fromkeys(refs))
