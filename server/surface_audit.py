"""Bounded public-page collector for Surface Audit. Never uses account credentials."""
import ipaddress,socket
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from html.parser import HTMLParser
from urllib.error import HTTPError,URLError
from urllib.parse import urljoin,urlparse
from urllib.request import HTTPRedirectHandler,Request,build_opener

MAX_BYTES=900_000
MAX_REDIRECTS=3
TIMEOUT=8

class NoRedirect(HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):return None

class PageParser(HTMLParser):
 def __init__(self):
  super().__init__(convert_charrefs=True);self.title='';self.description='';self.og_title='';self.og_description='';self.canonical='';self.links=[];self.forms=0;self.viewport=False;self._title=False
 def handle_starttag(self,tag,attrs):
  attrs={str(k).lower():str(v or '') for k,v in attrs};tag=tag.lower()
  if tag=='title':self._title=True
  if tag=='meta':
   key=(attrs.get('name') or attrs.get('property')).lower();value=attrs.get('content','').strip()
   if key=='description' and not self.description:self.description=value[:500]
   if key=='og:title' and not self.og_title:self.og_title=value[:300]
   if key=='og:description' and not self.og_description:self.og_description=value[:500]
   if key=='viewport':self.viewport=True
  if tag=='link' and 'canonical' in attrs.get('rel','').lower():self.canonical=attrs.get('href','')[:2000]
  if tag=='a' and attrs.get('href') and len(self.links)<500:self.links.append(attrs['href'][:2000])
  if tag=='form':self.forms+=1
 def handle_endtag(self,tag):
  if tag.lower()=='title':self._title=False
 def handle_data(self,data):
  if self._title and len(self.title)<300:self.title=(self.title+' '+data.strip()).strip()[:300]

def _public_ip(host):
 try:
  literal=ipaddress.ip_address(host.strip('[]'))
  if not literal.is_global:raise ValueError('PRIVATE_ADDRESS')
  return
 except ValueError as exc:
  if str(exc)=='PRIVATE_ADDRESS':raise
 try:addresses={item[4][0] for item in socket.getaddrinfo(host,None,type=socket.SOCK_STREAM)}
 except socket.gaierror:raise ValueError('DNS_FAILED')
 if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):raise ValueError('PRIVATE_ADDRESS')

def validate_public_url(value):
 parsed=urlparse(value)
 if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:raise ValueError('INVALID_URL')
 if parsed.port and parsed.port not in (80,443):raise ValueError('UNSAFE_PORT')
 host=parsed.hostname.lower().rstrip('.')
 if host in ('localhost','localhost.localdomain') or host.endswith(('.local','.internal','.localhost')):raise ValueError('PRIVATE_ADDRESS')
 _public_ip(host);return value

def summarize_html(raw,final_url,status,content_type):
 parser=PageParser();parser.feed(raw.decode('utf-8','replace'))
 links=[urljoin(final_url,link) for link in parser.links]
 lowered=raw[:MAX_BYTES].lower()
 social_hosts=('instagram.com','facebook.com','tiktok.com','linkedin.com','youtube.com','x.com','twitter.com','threads.net','pinterest.')
 return {
  'status':'available','httpStatus':status,'finalUrl':final_url,'contentType':content_type,
  'title':parser.og_title or parser.title,'description':parser.og_description or parser.description,'canonical':urljoin(final_url,parser.canonical) if parser.canonical else '',
  'signals':{
   'mobileViewport':parser.viewport,'forms':min(parser.forms,99),
   'whatsApp':any('wa.me/' in link or 'whatsapp.com/' in link for link in links),
   'socialLinks':sum(any(host in link.lower() for host in social_hosts) for link in links),
   'analytics':any(token in lowered for token in (b'googletagmanager',b'gtag(',b'google-analytics',b'fbq(',b'connect.facebook.net/en_us/fbevents')),
   'structuredData':b'application/ld+json' in lowered
  }
 }

def inspect_url(url):
 current=url;opener=build_opener(NoRedirect)
 for _ in range(MAX_REDIRECTS+1):
  try:validate_public_url(current)
  except ValueError as exc:return {'status':'blocked','reason':str(exc)}
  req=Request(current,headers={'User-Agent':'NEMDAR-Surface-Audit/0.6 (+https://nemdar.tech)','Accept':'text/html,application/xhtml+xml;q=0.9,*/*;q=0.1'})
  try:response=opener.open(req,timeout=TIMEOUT)
  except HTTPError as exc:
   if exc.code in (301,302,303,307,308) and exc.headers.get('Location'):
    current=urljoin(current,exc.headers['Location']);continue
   return {'status':'unavailable','httpStatus':exc.code,'reason':'HTTP_ERROR'}
  except (URLError,TimeoutError,OSError):return {'status':'unavailable','reason':'NETWORK_ERROR'}
  content_type=response.headers.get_content_type().lower()
  if content_type not in ('text/html','application/xhtml+xml'):return {'status':'unavailable','httpStatus':getattr(response,'status',200),'reason':'NON_HTML'}
  raw=response.read(MAX_BYTES+1)
  if len(raw)>MAX_BYTES:return {'status':'unavailable','httpStatus':getattr(response,'status',200),'reason':'PAGE_TOO_LARGE'}
  return summarize_html(raw,response.geturl(),getattr(response,'status',200),content_type)
 return {'status':'unavailable','reason':'TOO_MANY_REDIRECTS'}

def collect(urls):
 results={};workers=min(4,max(1,len(urls)))
 with ThreadPoolExecutor(max_workers=workers,thread_name_prefix='surface-audit') as pool:
  futures={pool.submit(inspect_url,url):key for key,url in urls.items()}
  for future in as_completed(futures):
   key=futures[future]
   try:results[key]=future.result()
   except Exception:results[key]={'status':'unavailable','reason':'COLLECTOR_ERROR'}
 results['observedAt']=datetime.now(timezone.utc).isoformat();return results
