"""Provision a persistent local key only for a new, empty vault."""
import os
from pathlib import Path
from server.facebook import key

def initialize(store):
 if os.environ.get('VAULT_KEY'):
  key();return
 path=Path(store.path).parent/'vault.key'
 if not path.exists():
  with store.db() as db:
   if db.execute('SELECT 1 FROM vault LIMIT 1').fetchone() or db.execute('SELECT 1 FROM page_connections LIMIT 1').fetchone():
    raise RuntimeError('Existing encrypted data requires its original vault key; refusing replacement')
  try:
   fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
  except FileExistsError:pass
  else:
   with os.fdopen(fd,'w') as file:file.write(os.urandom(32).hex());file.flush();os.fsync(file.fileno())
 value=path.read_text().strip()
 os.environ['VAULT_KEY']=value
 key()
