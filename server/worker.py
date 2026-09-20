"""Run separately from the web process. Provider registry intentionally empty until configured."""
import os,signal,time
from server.core import Store
from server.dispatch import Dispatcher
running=True
def stop(*_):
 global running
 running=False
def main():
 signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
 store=Store(os.environ.get('DATABASE_PATH','data/workspace.db'));dispatcher=Dispatcher(store)
 print('Dispatch worker started; no live platform adapters configured.',flush=True)
 while running:
  dispatcher.recover()
  if not dispatcher.run_one():time.sleep(5)
if __name__=='__main__':main()
