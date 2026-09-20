import hashlib,io,json,os,tempfile,unittest
from unittest.mock import patch
from server.app import App
class SetupTests(unittest.TestCase):
 def test_one_time_setup(self):
  with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'BOOTSTRAP_TOKEN_HASH':hashlib.sha256(b'private-test-token').hexdigest()}):
   app=App(tmp+'/db','http://localhost:8080')
   def req(token):
    body=json.dumps({'token':token,'email':'owner@example.com','password':'Owner-password-123'}).encode();result={}
    response=b''.join(app({'PATH_INFO':'/api/setup','REQUEST_METHOD':'POST','HTTP_ORIGIN':'http://localhost:8080','CONTENT_TYPE':'application/json','CONTENT_LENGTH':str(len(body)),'wsgi.input':io.BytesIO(body)},lambda s,h:result.update(status=int(s.split()[0]))))
    return result['status']
   self.assertEqual(req('wrong'),403);self.assertEqual(req('private-test-token'),200);self.assertEqual(req('private-test-token'),400)
