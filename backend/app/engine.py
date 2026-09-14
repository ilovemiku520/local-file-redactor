from __future__ import annotations
from collections import Counter
from io import BytesIO
import hashlib
import importlib.metadata
import json
import time
from PIL import Image
from .storage import Storage, UserError
from . import formats, raster, detection, vault, office


def analyze(store, job):
    job_id=job['job_id']
    job.update(status='extracting',progress='正在解析文件',pages=[],findings=[],reviewed_pages=[],revision=1)
    store.save(job)
    original=store.read(job_id,'source')
    extension=job['input_type']
    ocr=None
    def add_image(image, native='', native_spans=None, size=None):
        nonlocal ocr
        if ocr is None: ocr=raster.OCR()
        index=len(job['pages'])
        if index>=200: raise UserError('文件超过 200 页/图片的处理上限。')
        identifier=f'page{index}'
        store.write(job_id,identifier,formats.image_bytes(image))
        text,spans,uncertain=ocr.read(image)
        page={'id':index,'artifact':identifier,'width':image.width,'height':image.height,'size':size or [image.width*72/150,image.height*72/150],'kind':'image','blocks':[],'uncertain':uncertain}
        job['pages'].append(page)
        for source,body,locations in [('OCR',text,spans),('PDF文字层',native,native_spans or [])]:
            if body:
                block={'id':f'{identifier}_{source}','text':body,'spans':locations,'page':index,'label':f'第 {index+1} 页 / {source}','context':''}
                image_blocks.append(block)
                page['blocks'].append(block['id'])
        if uncertain:
            job['warnings'].append('存在低清晰度文字区域，请逐页检查并手动遮除遗漏信息。')
        job['progress']=f'已解析 {len(job["pages"])} 页/图片'
        store.save(job)
        return index
    image_blocks=[]
    job['warnings']=[]
    if extension=='pdf':
        for image,native,spans,size in raster.pdf_pages(original):
            add_image(image,native,spans,size)
        document={'blocks':[],'layout':[],'warnings':[]}
    elif extension in ('png','jpg','jpeg','webp','bmp'):
        add_image(formats.load_image(original))
        document={'blocks':[],'layout':[],'warnings':[]}
    else:
        document=formats.parse(original,extension,add_image)
        for image,refs in formats.text_pages(document,extension):
            index=len(job['pages'])
            if index>=200: raise UserError('文档预览超过 200 页，请拆分文件。')
            store.write(job_id,f'page{index}',formats.image_bytes(image))
            job['pages'].append({'id':index,'artifact':f'page{index}','width':image.width,'height':image.height,'size':[595.28,841.89],'kind':'text','blocks':refs,'uncertain':[]})
        job['warnings'].extend(document['warnings'])
        if extension in ('docx','xlsx') and job['output_format']=='pdf':
            job['warnings'].append('Office 转 PDF 为简化排版。保留原样式请选择 DOCX/XLSX；需要原样 PDF 时请先在 Office 中另存为 PDF 后导入。')
    blocks=document['blocks']+image_blocks
    if sum(len(block['text']) for block in blocks)>2_000_000:
        raise UserError('文件文字超过 200 万字符，请拆分文件。')
    job['document']=document
    job['blocks']=blocks
    job['status']='detecting'
    model=detection.LocalModel() if job['strategy']=='model' else None
    job['model_digest']=model.digest if model else None
    if not model: job['warnings'].append('仅规则识别：语义模型未运行，姓名、地址等信息需重点复核。')
    # Composite text gives the model surrounding context and covers adjacent-block entities.
    offsets=[]
    cursor=0
    for block in blocks:
        offsets.append((cursor,cursor+len(block['text']),block['id']))
        cursor+=len(block['text'])+1
    composite='\n'.join(block['text'] for block in blocks)
    global_items=detection.rules(composite,job['options'])
    if model and composite.strip():
        job['progress']='正在进行全文本地模型识别';store.save(job)
        global_items+=model.detect(composite,job['options'])
    projected={block['id']:[] for block in blocks}
    for item in global_items:
        for start,end,block_id in offsets:
            left,right=max(start,item['start']),min(end,item['end'])
            if left<right and composite[left:right].strip():
                projected[block_id].append(dict(item,start=left-start,end=right-start,value=composite[left:right]))
    for index,block in enumerate(blocks):
        items=detection.rules(block['text'],job['options'],block.get('context',''))
        items+=projected[block['id']]
        for item in detection.merge(items,block['text']):
            item.update(id=len(job['findings'])+1,block_id=block['id'],keep=False,manual=False)
            if 'spans' in block:
                item['page']=block['page']
                item['boxes']=[span['box'] for span in block['spans'] if span['start']<item['end'] and span['end']>item['start'] and span['box'][0]<span['box'][2] and span['box'][1]<span['box'][3]]
                if not item['boxes']: raise UserError('敏感文字缺少可靠坐标，无法继续。')
            else:
                item['page']=next((p['id'] for p in job['pages'] if block['id'] in p['blocks']),0)
                item['boxes']=[]
            job['findings'].append(item)
        job['progress']=f'已识别 {index+1} / {len(blocks)} 个文本块'
        store.save(job)
    job.update(status='needs_review',progress='识别完成，请逐页复核',analysis_complete=True,warnings=list(dict.fromkeys(job['warnings'])))
    store.save(job)


def export(store, job, password):
    if set(job['reviewed_pages'])!=set(p['id'] for p in job['pages']):
        raise UserError('请确认所有页面，包括没有候选项的页面。')
    job_id=job['job_id']
    job.update(status='redacting',progress='正在生成并检查脱敏文件')
    store.save(job)
    findings=job['findings']
    texts={b['id']:detection.replace(b['text'],[f for f in findings if f['block_id']==b['id']]) for b in job['blocks']}
    def clean_image(index):
        page=job['pages'][index]
        image=Image.open(BytesIO(store.read(job_id,page['artifact']))).convert('RGB')
        boxes=[box for finding in findings if finding['page']==index and not finding['keep'] for box in finding['boxes']]
        image=raster.redact(image,boxes)
        return image
    extension=job['output_format']
    source_type=job['input_type']
    formula_count=0
    if source_type in ('docx','xlsx') and extension!='pdf':
        texts={b['id']:office.mask_text(b['text'],[f for f in findings if f['block_id']==b['id']]) for b in job['blocks']}
    if source_type in ('png','jpg','jpeg','webp','bmp'):
        data=formats.image_bytes(clean_image(0),extension)
        verified=formats.load_image(data)
        if verified.size!=(job['pages'][0]['width'],job['pages'][0]['height']):
            raise UserError('图片尺寸验证失败。')
    elif extension=='pdf':
        if source_type=='pdf':
            data=raster.make_pdf((clean_image(p['id']),p['size']) for p in job['pages'])
        else:
            # Native Office previews are explicitly simplified; rebuild from redacted text.
            document=json.loads(json.dumps(job['document']))
            for block in document['blocks']: block['text']=texts[block['id']]
            def pages():
                for image,_ in formats.text_pages(document,source_type): yield image,[595.28,841.89]
                for page in job['pages']:
                    if page['kind']=='image': yield clean_image(page['id']),page['size']
            data=raster.make_pdf(pages())
    else:
        data,formula_count=formats.native_export(job['document'],extension,texts,lambda i:formats.image_bytes(clean_image(i)),original=store.read(job_id,'source'))
        # Parse with a separate reader and check removed text did not survive reconstruction.
        if extension=='txt':
            extracted=data.decode('utf-8')
        elif extension=='csv':
            import csv
            from io import StringIO
            extracted='\n'.join(' '.join(row) for row in csv.reader(StringIO(data.decode('utf-8-sig'),newline=''),delimiter=job['document']['delimiter']))
        else:
            import zipfile
            from lxml import etree
            with zipfile.ZipFile(BytesIO(data)) as archive:
                roots=[etree.fromstring(archive.read(name)) for name in archive.namelist() if name.endswith(('.xml','.rels'))]
                extracted='\n'.join(''.join(root.itertext())+'\n'+'\n'.join(value for node in root.iter() for value in node.attrib.values()) for root in roots)
                if any(part in name for name in archive.namelist() for part in ('comments','externalLinks','embeddings','vbaProject')):
                    raise UserError('Office 输出包含不允许的附加内容。')
        kept={f['value'] for f in findings if f['keep']}
        for finding in findings:
            if not finding['keep'] and not finding['boxes'] and finding['value'] not in kept and finding['value'] in extracted:
                raise UserError('导出后的文本检查发现待遮除原文残留，请复核重复出现位置。')
    if not data: raise UserError('导出文件为空。')
    job.update(status='verifying',progress='正在验证输出和恢复包')
    store.save(job)
    digest=hashlib.sha256(data).hexdigest()
    store.write(job_id,'redacted',data)
    if job['reversible']:
        source=store.read(job_id,'source')
        bundle=vault.create(source,data,source_type,password)
        recovered,_=vault.restore(bundle,data,password)
        if recovered!=source: raise UserError('恢复包校验失败。')
        store.write(job_id,'vault',bundle)
    report={'job_id':job_id,'version':'2.1','input_format':source_type,'output_format':extension,
            'pages':len(job['pages']),'review_revision':job['revision'],'reviewed_pages':len(job['reviewed_pages']),
            'strategy':job['strategy'],'model':detection.MODEL if job['model_digest'] else None,'model_digest':job['model_digest'],
            'redacted_counts':dict(Counter(f['type'] for f in findings if not f['keep'])),
            'kept_count':sum(f['keep'] for f in findings),'manual_regions':sum(f['manual'] for f in findings),
            'formula_protected_cells':formula_count,'output_sha256':digest,'created_at':time.time(),
            'verification':{'structure':True,'selected_content':True,'human_page_review':True,'recovery_roundtrip':True if job['reversible'] else None},
            'warnings':job['warnings'],'recovery_mode':'password_encrypted_exact_original' if job['reversible'] else None,
            'layout_mode':('ooxml_preserved' if source_type in ('docx','xlsx') and extension!='pdf' else 'simplified_office_pdf' if source_type in ('docx','xlsx') else 'original_page_pixels' if source_type=='pdf' or source_type in ('png','jpg','jpeg','webp','bmp') else 'text'),
            'limitations':['自动识别无法保证发现全部敏感信息；手写、印章、人脸、二维码需人工复核。','反脱敏恢复原始文件，不合并对脱敏文件的后续编辑。'],
            'packages':{p:importlib.metadata.version(p) for p in ('Pillow','pypdf','pypdfium2','paddleocr','paddlepaddle','cryptography','python-docx','openpyxl')}}
    store.write(job_id,'report',json.dumps(report,ensure_ascii=False,indent=2).encode())
    job.update(status='completed',progress='脱敏文件已生成并通过检查',output_sha256=digest,export_revision=job['revision'],verification_passed=True)
    store.save(job)


def run(job_id, action):
    store=Storage()
    job=store.load(job_id)
    try:
        if action=='analyze': analyze(store,job)
        else:
            password=job.pop('export_password','')
            store.save(job)
            export(store,job,password)
    except UserError as exc:
        job.pop('export_password',None)
        job.update(status='failed',error=str(exc),progress='处理未完成',verification_passed=False)
        store.save(job)
    except Exception as exc:
        job.pop('export_password',None)
        # Exception values can contain original content; only retain the exception class.
        job.update(status='failed',error='处理组件异常（'+type(exc).__name__+'），请检查环境或文件格式。',error_code=type(exc).__name__,progress='处理未完成',verification_passed=False)
        store.save(job)
