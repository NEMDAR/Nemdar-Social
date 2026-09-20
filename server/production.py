import os
from waitress import serve
from server.app import App
if __name__=='__main__':
 serve(App(),host='0.0.0.0',port=int(os.environ.get('PORT','8080')),threads=4,max_request_body_size=15*1024*1024,channel_timeout=30)
