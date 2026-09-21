"""WSGI entrypoint. Run behind HTTPS with Waitress for deployment."""
import json,mimetypes,os,secrets,sys,traceback,hashlib
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs,urlparse
from server.core import Store,Problem
ROOT=Path(__file__).resolve().parents[1]
class App:
 def __init__(self,path=None,origin=None):
  self.store=Store(path or os.environ.get('DATABASE_PATH',str(ROOT/'data/workspace.db')))
  self.origin=origin or os.environ.get('APP_ORIGIN','http://localhost:8080')
  parsed=urlparse(self.origin)
  if parsed.scheme not in ['http','https'] or not parsed.netloc:raise ValueError('APP_ORIGIN must be a full origin')
  self.secure=parsed.scheme=='https'
 def __call__(self,env,start):
  status=200;extra=[];mime='application/json';payload=None
  path=env.get('PATH_INFO','/');method=env.get('REQUEST_METHOD','GET')
  try:
   if method not in ['GET','POST']:raise Problem('الطريقة غير مدعومة',405)
   if method=='POST' and env.get('HTTP_ORIGIN')!=self.origin:raise Problem('مصدر الطلب غير مسموح',403)
   cookies=SimpleCookie()
   try:cookies.load(env.get('HTTP_COOKIE',''))
   except Exception:pass
   token=cookies['session'].value if 'session' in cookies else ''
   body={}
   if method=='POST':
    try:length=int(env.get('CONTENT_LENGTH','0'))
    except ValueError:raise Problem('حجم الطلب غير صالح')
    if length<0 or length>15*1024*1024:raise Problem('حجم الطلب كبير',413)
    if env.get('CONTENT_TYPE','').split(';')[0]!='application/json':raise Problem('نوع الطلب غير مدعوم',415)
    try:body=json.loads(env['wsgi.input'].read(length))
    except (ValueError,UnicodeDecodeError):raise Problem('البيانات غير صالحة')
    if not isinstance(body,dict):raise Problem('البيانات غير صالحة')
   cookie_flags='; Path=/; HttpOnly; SameSite=Strict'+('; Secure' if self.secure else '')
   qs=parse_qs(env.get('QUERY_STRING',''),keep_blank_values=True)
   if path=='/api/health' and method=='GET':payload={'ok':True,'version':'0.9.0'}
   elif path=='/api/setup' and method=='POST':
    configured=os.environ.get('BOOTSTRAP_TOKEN_HASH','')
    supplied=body.get('token','')
    if not isinstance(supplied,str) or not configured or not secrets.compare_digest(hashlib.sha256(supplied.encode()).hexdigest(),configured):raise Problem('رابط الإعداد غير صالح',403)
    email=body.get('email','')
    if not isinstance(email,str) or '@' not in email or len(email)>200:raise Problem('البريد غير صحيح')
    self.store.setup(email,body.get('password',''),body.get('name','Administrator')[:100])
    payload={'ok':True}
   elif path=='/api/login' and method=='POST':
    email=body.get('email','');password=body.get('password','')
    if not isinstance(email,str) or len(email)>200 or not isinstance(password,str):raise Problem('بيانات غير صحيحة')
    token,csrf=self.store.login(email,password,env.get('REMOTE_ADDR',''))
    extra.append(('Set-Cookie','session='+token+cookie_flags+'; Max-Age=28800'));payload={'ok':True,'csrf':csrf}
   elif path.startswith('/api/public-media/') and method=='GET':
    from server.instagram import public_media
    payload,mime=public_media(self.store,path.rsplit('/',1)[-1],env.get('QUERY_STRING',''));extra.append(('Content-Disposition','inline'))
   elif path.startswith('/api/'):
    user=self.store.session(token)
    if method=='POST' and not secrets.compare_digest(env.get('HTTP_X_CSRF_TOKEN',''),user['csrf']):raise Problem('حدّث الصفحة ثم حاول مرة أخرى',403)
    if path=='/api/state' and method=='GET':payload=self.store.state(user)
    elif path=='/api/facebook/connect' and method=='POST':
     from server.facebook import connect
     payload=connect(self.store,user,body)
    elif path=='/api/facebook/disconnect' and method=='POST':
     from server.facebook import disconnect
     payload=disconnect(self.store,user,body.get('accountId'))
    elif path=='/api/facebook/send' and method=='POST':
     from server.facebook import send_target
     payload=send_target(self.store,user,body)
    elif path=='/api/instagram/connect' and method=='POST':
     from server.instagram import connect
     payload=connect(self.store,user,body)
    elif path=='/api/instagram/disconnect' and method=='POST':
     from server.instagram import disconnect
     payload=disconnect(self.store,user,body.get('accountId'))
    elif path=='/api/instagram/send' and method=='POST':
     from server.instagram import send_target
     payload=send_target(self.store,user,body)
    elif path=='/api/insights/sync' and method=='POST':
     from server.insights import sync_account
     payload=sync_account(self.store,user,body)
    elif path=='/api/audit' and method=='GET':
     from server.audit_engine import get_current
     payload=get_current(self.store,user,(qs.get('clientId') or [None])[0])
    elif path=='/api/audit/history' and method=='GET':
     from server.audit_engine import get_history
     payload=get_history(self.store,user,(qs.get('clientId') or [None])[0])
    elif path=='/api/audit/run' and method=='POST':
     from server.audit_engine import run_audit
     payload=run_audit(self.store,user,body.get('clientId'))
    elif path=='/api/action' and method=='POST':
     if not isinstance(body.get('payload'),dict):raise Problem('بيانات الإجراء غير صالحة')
     payload=self.store.mutate(user,body.get('action'),body['payload'],body.get('revision'))
    elif path=='/api/logout' and method=='POST':
     self.store.logout(token);extra.append(('Set-Cookie','session='+cookie_flags+'; Max-Age=0'));payload={'ok':True}
    elif path=='/api/password' and method=='POST':
     self.store.change_password(user,body.get('current',''),body.get('password',''));payload={'ok':True}
    elif path.startswith('/api/media/') and method=='GET':
     payload,mime=self.store.file(user,path.rsplit('/',1)[-1]);extra.append(('Content-Disposition','inline'))
    else:raise Problem('المسار غير موجود',404)
   else:
    if method!='GET':raise Problem('المسار غير موجود',404)
    # Explicit allowlist prevents exposing database, tests, secrets, or source on the server.
    allowed=['/index.html','/login.html','/design-preview.html','/screens.json']
    path='/index.html' if path=='/' else path
    if path not in allowed and not (path.startswith('/src/') and path.endswith(('.js','.css'))) and not (path.startswith('/designs/') and path.endswith('.html')):raise Problem('المسار غير موجود',404)
    file=(ROOT/path.lstrip('/')).resolve()
    if ROOT not in file.parents or not file.is_file():raise Problem('المسار غير موجود',404)
    payload=file.read_bytes();mime=mimetypes.guess_type(file)[0] or 'application/octet-stream'
  except Problem as e:status=e.status;payload={'error':e.message}
  except Exception:
   traceback.print_exc();status=500;payload={'error':'حدث خطأ على الخادم؛ لم يتم تأكيد الحفظ'}
  if not isinstance(payload,bytes):payload=json.dumps(payload,ensure_ascii=False).encode()
  headers=[('Content-Type',mime+('; charset=utf-8' if mime.startswith('text/') or mime in ['application/json','application/javascript'] else '')),('Content-Length',str(len(payload))),('Cache-Control','no-store'),('X-Content-Type-Options','nosniff'),('X-Frame-Options','SAMEORIGIN'),('Referrer-Policy','same-origin'),('Permissions-Policy','camera=(), microphone=(), geolocation=()')]+extra
  # Legacy Stitch preview uses inline scripts and CDN. The operational app is stricter.
  if not path.startswith('/designs/') and path!='/design-preview.html':headers.append(('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'self'"))
  if self.secure:headers.append(('Strict-Transport-Security','max-age=31536000'))
  from http import HTTPStatus
  start(f'{status} {HTTPStatus(status).phrase}',headers);return [payload]

def create_app():return App()
if __name__=='__main__':
 from wsgiref.simple_server import make_server
 app=App();print('Development server: '+app.origin,flush=True)
 with make_server('127.0.0.1',int(os.environ.get('PORT','8080')),app) as httpd:httpd.serve_forever()
