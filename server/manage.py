import argparse,getpass,os,sqlite3
from pathlib import Path
from server.core import Store

def main():
 p=argparse.ArgumentParser();p.add_argument('command',choices=['init','backup']);p.add_argument('--email');p.add_argument('--output');a=p.parse_args()
 path=os.environ.get('DATABASE_PATH',str(Path(__file__).resolve().parents[1]/'data/workspace.db'));store=Store(path)
 if a.command=='init':
  email=a.email or input('Admin email: ');password=getpass.getpass('Password (12+ characters): ')
  if password!=getpass.getpass('Confirm password: '):raise SystemExit('Passwords do not match')
  store.setup(email,password);print('Administrator created. Start the server and log in.')
 else:
  if not a.output:raise SystemExit('--output is required')
  if Path(a.output).exists():raise SystemExit('Backup destination already exists')
  with store.db() as source,sqlite3.connect(a.output) as target:source.backup(target)
  os.chmod(a.output,0o600);print('Consistent database backup saved.')
if __name__=='__main__':main()
