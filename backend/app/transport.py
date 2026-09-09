"""Keep multipart originals in RAM; bound the body before the parser can spool."""
from starlette.formparsers import MultiPartParser,MultiPartException
from starlette.responses import JSONResponse

MAX_BODY_BYTES=640*1024**2
# Starlette normally writes files larger than 1 MiB to the system temp directory.
# The receive wrapper below stops requests before this raised spool threshold.
MultiPartParser.spool_max_size=MAX_BODY_BYTES+1

class MemoryUploads:
    def __init__(self,app,max_bytes=MAX_BODY_BYTES):
        self.app=app
        self.max_bytes=max_bytes

    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.app(scope,receive,send)
        headers=dict(scope.get('headers',[]))
        try:
            declared=int(headers.get(b'content-length',b'0'))
            if declared<0:raise ValueError()
        except ValueError:
            return await JSONResponse({'detail':'上传长度无效。'},400)(scope,receive,send)
        if declared>self.max_bytes:
            return await JSONResponse({'detail':'上传总大小超过限制，请拆分文件。'},413)(scope,receive,send)
        received=0
        async def bounded_receive():
            nonlocal received
            message=await receive()
            if message['type']=='http.request':
                received+=len(message.get('body',b''))
                if received>self.max_bytes:
                    # Multipart parser closes all in-memory files on this exception.
                    raise MultiPartException('上传总大小超过限制，请拆分文件。')
            return message
        await self.app(scope,bounded_receive,send)
