from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
import hashlib,hmac,mimetypes,os,secrets,subprocess,sys,threading,time
from pathlib import Path
from uuid import uuid4
from fastapi import FastAPI,UploadFile,File,Form,HTTPException,Request
from fastapi.responses import Response,JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .storage import Storage,ROOT,UserError,protect
from .formats import FORMATS
from .detection import model_status
from .raster import ocr_ready
from . import vault
from .transport import MemoryUploads

store=Storage()
executor=ThreadPoolExecutor(max_workers=1)
processes={}
mutation_lock=threading.RLock()
pair_code=os.environ.get('RD_PAIR_CODE') or secrets.token_urlsafe(24)
pair_created=time.time()
session_secret=secrets.token_urlsafe(32)
csrf_secret=secrets.token_urlsafe(32)
MAX_BYTES=100*1024**2
ACTIVE={'queued','extracting','detecting','queued_export','redacting','verifying'}

def schedule(job_id,action):
    generation=store.load(job_id).get('generation',0)
    def task():
        with mutation_lock:
            job=store.load(job_id)
            if job['status']=='cancelled' or job.get('generation',0)!=generation: return
            env=os.environ.copy()
            env.update(PYTHONPATH=str(ROOT/'backend'),PYTHONIOENCODING='utf-8',PADDLE_PDX_CACHE_HOME=str(ROOT/'runtime/paddlex-cache'))
            process=subprocess.Popen([sys.executable,'-E','-s','-m','app.worker',job_id,action],cwd=ROOT/'backend',env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            processes[job_id]=process
        try: process.wait(timeout=3600)
        except subprocess.TimeoutExpired: process.kill();process.wait()
        finally:
            with mutation_lock:
                processes.pop(job_id,None)
                job=store.load(job_id)
                if job['status'] in ACTIVE and job.get('generation',0)==generation:
                    job.pop('export_password',None)
                    job.update(status='interrupted',error='处理进程中断或超时，可重新识别。',verification_passed=False)
                    store.save(job)
    executor.submit(task)

def cleanup():
    for job_id in store.lifecycle_ids(ACTIVE,time.time()-24*3600): store.delete(job_id)

@asynccontextmanager
async def lifespan(app):
    for job_id in store.lifecycle_ids(ACTIVE):
        job=store.load(job_id)
        job.pop('export_password',None)
        job.update(status='interrupted',error='上次运行中断，请重新识别。',verification_passed=False);store.save(job)
    cleanup()
    stop=threading.Event()
    def janitor():
        while not stop.wait(300):
            with mutation_lock: cleanup()
    threading.Thread(target=janitor,daemon=True).start()
    yield
    stop.set()
    for process in list(processes.values()): process.terminate()
    executor.shutdown(wait=False,cancel_futures=True)

app=FastAPI(title='本地文件脱敏',version='2.0.0',lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost'])
app.add_middleware(MemoryUploads)

@app.middleware('http')
async def guard(request:Request,call_next):
    if request.url.path.startswith('/api/'):
        origin=request.headers.get('origin')
        if origin and origin not in ('http://127.0.0.1:8080','http://localhost:8080'): return JSONResponse({'detail':'禁止跨来源请求。'},403)
        if request.url.path not in ('/api/health','/api/session','/api/pair'):
            if not hmac.compare_digest(request.cookies.get('rd_session',''),session_secret): return JSONResponse({'detail':'请从本机启动入口打开应用。'},401)
            if request.method not in ('GET','HEAD') and not hmac.compare_digest(request.headers.get('x-rd-csrf',''),csrf_secret): return JSONResponse({'detail':'会话校验失败，请重新打开应用。'},403)
    response=await call_next(request)
    response.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','X-Frame-Options':'DENY','Content-Security-Policy':"default-src 'self'; img-src 'self' blob: data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; object-src 'none'"})
    return response

@app.exception_handler(UserError)
async def user_error(request,exc): return JSONResponse({'detail':str(exc)},400)

@app.get('/api/health')
def health(): return {'ok':True,'version':'2.0.0'}

@app.get('/api/session')
def session_info(request:Request):
    authenticated=hmac.compare_digest(request.cookies.get('rd_session',''),session_secret)
    return {'authenticated':authenticated,'csrf':csrf_secret if authenticated else None}

class Pair(BaseModel): code:str=Field(max_length=200)

@app.post('/api/pair')
def pair(payload:Pair):
    global pair_code
    with mutation_lock:
        pair_file=store.root/'pair.dpapi'
        current=protect(pair_file.read_bytes(),True).decode() if pair_file.exists() else pair_code
        created=pair_file.stat().st_mtime if pair_file.exists() else pair_created
        if not current or time.time()-created>300 or not hmac.compare_digest(payload.code,current): raise HTTPException(403,'配对入口已失效，请重新打开启动入口。')
        pair_code=''
        if pair_file.exists(): pair_file.unlink()
    response=JSONResponse({'authenticated':True,'csrf':csrf_secret})
    response.set_cookie('rd_session',session_secret,httponly=True,samesite='strict',path='/')
    return response

@app.get('/api/capabilities')
def capabilities(): return {'formats':FORMATS,'model':model_status(),'ocr_ready':ocr_ready(),'max_file_mb':100,'max_pages':200,'recovery':'exact_original'}

def public_job(job):
    return {key:job.get(key) for key in ('job_id','filename','status','progress','error','input_type','output_format','reversible','created_at','updated_at','warnings','revision','reviewed_pages','analysis_complete','verification_passed','export_revision','output_sha256','strategy','model_digest')} | {'page_count':len(job.get('pages',[])),'finding_count':len(job.get('findings',[]))}

@app.get('/api/jobs')
def list_jobs(): return [public_job(job) for job in store.list()]

@app.get('/api/jobs/{job_id}')
def get_job(job_id:str): return public_job(store.load(job_id))

async def upload_bytes(file,limit=MAX_BYTES):
    data=bytearray()
    while chunk:=await file.read(1024*1024):
        data.extend(chunk)
        if len(data)>limit: raise HTTPException(413,'文件超过大小限制。')
    if not data: raise UserError('文件为空。')
    return bytes(data)

@app.post('/api/jobs')
async def create_job(input_file:UploadFile=File(...),output_format:str=Form('auto'),strategy:str=Form('model'),reversible:bool=Form(True),business:bool=Form(False),terms:str=Form(''),allow:str=Form('')):
    extension=Path(input_file.filename or '').suffix.lower().lstrip('.')
    if extension not in FORMATS: raise UserError('不支持此文件类型。')
    if output_format=='auto': output_format=FORMATS[extension][0]
    if output_format not in FORMATS[extension]: raise UserError('输出格式与输入文件不匹配。')
    if strategy not in ('model','rules_only'): raise UserError('识别策略无效。')
    if strategy=='model' and not model_status()['ready']: raise UserError('本地模型尚未就绪，请启动模型或选择仅规则识别。')
    if len(terms)+len(allow)>20000: raise UserError('词典内容过长。')
    data=await upload_bytes(input_file)
    with mutation_lock:
        if len([j for j in store.list() if j['status'] in ACTIVE])>=20: raise UserError('队列已满，请等待任务完成。')
        identifier=uuid4().hex
        job={'job_id':identifier,'filename':Path(input_file.filename or 'document').name,'input_type':extension,'output_format':output_format,'strategy':strategy,'reversible':reversible,'options':{'business':business,'terms':[v.strip() for v in terms.splitlines() if v.strip()],'allow':[v.strip() for v in allow.splitlines() if v.strip()]},'status':'queued','created_at':time.time(),'updated_at':time.time(),'progress':'等待处理','warnings':[],'revision':1,'pages':[],'findings':[],'reviewed_pages':[],'verification_passed':False,'error':None}
        store.write(identifier,'source',data);store.save(job);schedule(identifier,'analyze')
    return public_job(job)

@app.get('/api/jobs/{job_id}/review')
def review_data(job_id:str):
    job=store.load(job_id)
    return {'pages':job.get('pages',[]),'findings':job.get('findings',[]),'blocks':[{k:b.get(k) for k in ('id','text','label')} for b in job.get('blocks',[])],'revision':job['revision'],'reviewed_pages':job.get('reviewed_pages',[])}

@app.get('/api/jobs/{job_id}/pages/{page_id}')
def page_image(job_id:str,page_id:int):
    job=store.load(job_id)
    if not 0<=page_id<len(job.get('pages',[])): raise HTTPException(404)
    return Response(store.read(job_id,job['pages'][page_id]['artifact']),media_type='image/png')

class Manual(BaseModel):
    page:int
    box:list[float]=Field(min_length=4,max_length=4)

class Review(BaseModel):
    revision:int
    keep_ids:list[int]=Field(default_factory=list,max_length=100000)
    confirmed_pages:list[int]=Field(default_factory=list,max_length=200)
    manual:list[Manual]=Field(default_factory=list,max_length=2000)
    extra_terms:list[str]=Field(default_factory=list,max_length=1000)

@app.post('/api/jobs/{job_id}/review')
def save_review(job_id:str,payload:Review):
    from . import detection
    with mutation_lock:
        job=store.load(job_id)
        if job['status'] not in ('needs_review','completed'): raise HTTPException(409,'当前任务不能修改复核。')
        if payload.revision!=job['revision']: raise HTTPException(409,'复核版本已变化，请刷新。')
        valid_pages=set(p['id'] for p in job['pages'])
        if not set(payload.confirmed_pages)<=valid_pages: raise UserError('页面编号无效。')
        base=[f for f in job['findings'] if not f['manual']]
        valid_ids={f['id'] for f in base}
        if not set(payload.keep_ids)<=valid_ids: raise UserError('候选编号无效。')
        for finding in base: finding['keep']=finding['id'] in payload.keep_ids
        next_id=max(valid_ids,default=0)+1
        for manual in payload.manual:
            if manual.page not in valid_pages or job['pages'][manual.page]['kind']!='image': raise UserError('文本页面请用补充敏感词，图片页面支持框选。')
            x1,y1,x2,y2=manual.box
            if not (0<=x1<x2<=1 and 0<=y1<y2<=1): raise UserError('框选坐标无效。')
            base.append({'id':next_id,'type':'CUSTOM_TERM','value':'手动区域','source':'人工框选','block_id':'','start':0,'end':0,'page':manual.page,'boxes':[manual.box],'keep':False,'manual':True});next_id+=1
        added=False
        for term in payload.extra_terms:
            if not term or len(term)>500: raise UserError('补充敏感词需为 1–500 个字符。')
            for block in job['blocks']:
                for finding in (f for f in detection.rules(block['text'],{'terms':[term]}) if f['source']=='自定义词'):
                    same=[f for f in base if f['block_id']==block['id'] and f['start']<finding['end'] and f['end']>finding['start']]
                    if same:
                        primary=same[0]
                        primary['start']=min(finding['start'],*(f['start'] for f in same))
                        primary['end']=max(finding['end'],*(f['end'] for f in same))
                        primary['value']=block['text'][primary['start']:primary['end']]
                        primary['boxes']=[s['box'] for s in block.get('spans',[]) if s['start']<primary['end'] and s['end']>primary['start']]
                        primary['keep']=False
                        primary['source']='人工补充 / '+primary['source']
                        base=[f for f in base if f not in same[1:]]
                        added=True
                        continue
                    page=block.get('page',next((p['id'] for p in job['pages'] if block['id'] in p['blocks']),0))
                    boxes=[s['box'] for s in block.get('spans',[]) if s['start']<finding['end'] and s['end']>finding['start']]
                    finding.update(id=next_id,block_id=block['id'],page=page,boxes=boxes,keep=False,manual=False)
                    base.append(finding);next_id+=1;added=True
        job.update(findings=base,reviewed_pages=[] if added else sorted(set(payload.confirmed_pages)),revision=job['revision']+1,status='needs_review',verification_passed=False,export_revision=None,error=None)
        store.save(job)
        return public_job(job)

class Export(BaseModel):
    revision:int
    password:str=Field(default='',max_length=256)

@app.post('/api/jobs/{job_id}/exports')
def create_export(job_id:str,payload:Export):
    with mutation_lock:
        job=store.load(job_id)
        if job['status']!='needs_review' or payload.revision!=job['revision']: raise HTTPException(409,'请完成当前版本复核后导出。')
        if set(job['reviewed_pages'])!=set(p['id'] for p in job['pages']): raise UserError('请逐页确认后导出。')
        if job['reversible'] and len(payload.password)<10: raise UserError('恢复密码至少 10 个字符。')
        job.update(status='queued_export',export_password=payload.password,progress='等待生成脱敏文件',generation=job.get('generation',0)+1)
        store.save(job);schedule(job_id,'export')
    return public_job(job)

@app.get('/api/jobs/{job_id}/download/{kind}')
def download(job_id:str,kind:str):
    job=store.load(job_id)
    if job['status']!='completed' or not job.get('verification_passed') or job.get('export_revision')!=job['revision']: raise HTTPException(409,'此版本尚未通过导出验证。')
    if kind not in ('redacted','vault','report') or (kind=='vault' and not job['reversible']): raise HTTPException(404)
    raw=store.read(job_id,kind)
    if kind=='redacted' and hashlib.sha256(raw).hexdigest()!=job['output_sha256']: raise HTTPException(409,'输出摘要校验失败。')
    ext={'redacted':job['output_format'],'vault':'rdvault','report':'json'}[kind]
    return Response(raw,media_type=mimetypes.guess_type('document.'+ext)[0] or 'application/octet-stream',headers={'Content-Disposition':f'attachment; filename="document_{job_id}_{kind}.{ext}"'})

@app.post('/api/restore')
async def restore_file(redacted:UploadFile=File(...),recovery:UploadFile=File(...),password:str=Form(...)):
    output=await upload_bytes(redacted,MAX_BYTES*5)
    bundle=await upload_bytes(recovery,MAX_BYTES+8192)
    source,extension=vault.restore(bundle,output,password)
    return Response(source,media_type='application/octet-stream',headers={'Content-Disposition':f'attachment; filename="document_{uuid4().hex}_restored.{extension}"'})

@app.post('/api/jobs/{job_id}/cancel')
def cancel(job_id:str):
    with mutation_lock:
        job=store.load(job_id)
        process=processes.get(job_id)
        if process: process.terminate();process.wait(timeout=10)
        job=store.load(job_id);job.pop('export_password',None)
        job.update(status='cancelled',verification_passed=False,error=None,generation=job.get('generation',0)+1);store.save(job)
    return public_job(job)

@app.post('/api/jobs/{job_id}/retry')
def retry(job_id:str):
    with mutation_lock:
        job=store.load(job_id)
        if job['status'] not in ('failed','interrupted','cancelled'): raise HTTPException(409,'当前任务不能重试。')
        job.update(status='queued',error=None,verification_passed=False,export_revision=None,generation=job.get('generation',0)+1);store.save(job);schedule(job_id,'analyze')
    return public_job(job)

@app.delete('/api/jobs/{job_id}')
def delete(job_id:str):
    with mutation_lock:
        job=store.load(job_id)
        if job['status'] in ACTIVE or job_id in processes: raise HTTPException(409,'请先取消正在处理的任务。')
        store.delete(job_id)
    return {'ok':True}

if (ROOT/'frontend/dist').is_dir(): app.mount('/',StaticFiles(directory=ROOT/'frontend/dist',html=True),name='frontend')
