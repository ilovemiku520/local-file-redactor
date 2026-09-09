"""Start/stop only this project's processes and pair the local browser once."""
from __future__ import annotations
import argparse,hashlib,json,os,secrets,subprocess,sys,time,webbrowser
from pathlib import Path
import psutil,requests
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app.storage import Storage,protect,UserError
RUN=ROOT/'runtime'
FLAGS=getattr(subprocess,'CREATE_NO_WINDOW',0)

def client():
    value=requests.Session();value.trust_env=False;return value

def owned(record):
    try:
        process=psutil.Process(record['pid'])
        return abs(process.create_time()-record['created'])<1 and Path(process.exe()).resolve()==Path(record['exe']).resolve()
    except (psutil.Error,KeyError):return False

def start_process(command,env,name):
    logs=RUN/'logs';logs.mkdir(parents=True,exist_ok=True)
    with (logs/(name+'.log')).open('ab') as log:
        process=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=log,creationflags=FLAGS)
    proc=psutil.Process(process.pid)
    return {'pid':process.pid,'created':proc.create_time(),'exe':proc.exe()}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--stop',action='store_true');parser.add_argument('--no-browser',action='store_true');args=parser.parse_args()
    RUN.mkdir(exist_ok=True)
    state_path=RUN/'processes.json'
    state=json.loads(state_path.read_text()) if state_path.exists() else {}
    if args.stop:
        for name in ('backend','ollama'):
            record=state.get(name)
            if record and owned(record):
                parent=psutil.Process(record['pid'])
                descendants=parent.children(recursive=True)
                for child in descendants: child.terminate()
                parent.terminate()
                psutil.wait_procs([parent]+descendants,timeout=8)
        state_path.write_text('{}')
        print('Project services stopped.');return
    store=Storage()
    # Restrict the private job directory to the current user and SYSTEM.
    import ctypes
    from ctypes import wintypes
    size=wintypes.DWORD(256);buffer=ctypes.create_unicode_buffer(256)
    ctypes.windll.advapi32.GetUserNameW(buffer,ctypes.byref(size))
    subprocess.run(['icacls',str(store.root),'/inheritance:r','/grant:r',buffer.value+':(OI)(CI)F','*S-1-5-18:(OI)(CI)F'],stdout=subprocess.DEVNULL,check=True,creationflags=FLAGS)
    env=os.environ.copy()
    env.update(OLLAMA_HOST='127.0.0.1:11434',OLLAMA_MODELS=str(RUN/'models/ollama'),OLLAMA_NO_CLOUD='1',OLLAMA_NUM_PARALLEL='1',OLLAMA_MAX_LOADED_MODELS='1',OLLAMA_CONTEXT_LENGTH='8192',OLLAMA_LLM_LIBRARY='cuda_v12',PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK='True',PADDLE_PDX_CACHE_HOME=str(RUN/'paddlex-cache'),PYTHONIOENCODING='utf-8')
    http=client()
    try:
        http.get('http://127.0.0.1:11434/api/version',timeout=2).raise_for_status()
        record=state.get('ollama')
        if not record:
            old=RUN/'ollama.pid'
            if old.exists():
                candidate=psutil.Process(int(old.read_text().strip()))
                if Path(candidate.exe()).resolve()==(RUN/'ollama/ollama.exe').resolve():
                    environ=candidate.environ()
                    if environ.get('OLLAMA_NO_CLOUD')=='1' and environ.get('OLLAMA_MODELS')==str(RUN/'models/ollama'):
                        record={'pid':candidate.pid,'created':candidate.create_time(),'exe':candidate.exe()};state['ollama']=record
        if not record or not owned(record): raise UserError('模型端口被其他服务占用，请先关闭该服务。')
    except requests.RequestException:
        state['ollama']=start_process([str(RUN/'ollama/ollama.exe'),'serve'],env,'ollama-managed')
        for _ in range(60):
            try: http.get('http://127.0.0.1:11434/api/version',timeout=1).raise_for_status();break
            except requests.RequestException:time.sleep(.5)
        else:raise UserError('Ollama 启动失败，请查看本项目 runtime/logs。')
    lock=json.loads((ROOT/'models.lock.json').read_text('utf-8'))
    models=http.get('http://127.0.0.1:11434/api/tags',timeout=5).json()['models']
    if not any(m['name']==lock['llm']['name'] and m['digest']==lock['llm']['digest'] for m in models): raise UserError('本地模型摘要不匹配，请重新准备模型。')
    for source in [*lock['ocr'],{'files':lock['tokenizer']}]:
        for relative,expected in source['files'].items():
            path=(ROOT/relative).resolve()
            if not path.is_relative_to(ROOT) or hashlib.file_digest(path.open('rb'),'sha256').hexdigest()!=expected: raise UserError('OCR 或 tokenizer 文件校验失败。')
    code=None
    try:
        http.get('http://127.0.0.1:8080/api/health',timeout=2).raise_for_status()
        if not state.get('backend') or not owned(state['backend']): raise UserError('8080 端口被其他服务占用。')
    except requests.RequestException:
        code=secrets.token_urlsafe(24);env['RD_PAIR_CODE']=code
        (store.root/'pair.dpapi').write_bytes(protect(code.encode()))
        state['backend']=start_process([sys.executable,'-E','-s','-m','uvicorn','app.main:app','--app-dir',str(ROOT/'backend'),'--host','127.0.0.1','--port','8080','--no-access-log'],env,'backend')
        for _ in range(60):
            try:http.get('http://127.0.0.1:8080/api/health',timeout=1).raise_for_status();break
            except requests.RequestException:time.sleep(.5)
        else:raise UserError('后端启动失败，请查看本项目 runtime/logs。')
    if code is None:
        code=secrets.token_urlsafe(24)
        (store.root/'pair.dpapi').write_bytes(protect(code.encode()))
    state_path.write_text(json.dumps(state,indent=2))
    if not args.no_browser:webbrowser.open('http://127.0.0.1:8080/'+('#pair='+code if code else ''))
    print('Local Redactor ready: http://127.0.0.1:8080')

if __name__=='__main__':
    try:main()
    except (UserError,OSError,KeyError,ValueError) as error:
        print('Startup failed:',str(error));sys.exit(1)
