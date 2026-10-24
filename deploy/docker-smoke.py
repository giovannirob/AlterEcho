"""Container smoke test: HTTP, explicit demo and persisted history. No AI calls."""
import json
import os
import sys
import time
from urllib.request import Request,urlopen

base=os.environ.get('ALTERECHO_TEST_URL','http://127.0.0.1:8765')+'/api/v1'
headers={'Authorization':'Bearer fixture-token-with-at-least-32-characters','Content-Type':'application/json'}
def request(path,body=None):
    data=json.dumps(body).encode() if body is not None else None
    with urlopen(Request(base+path,data=data,headers=headers),timeout=5) as response:return json.load(response)
for attempt in range(60):
    try:
        request('/health');break
    except OSError:time.sleep(1)
else:raise SystemExit('Container did not become healthy')
with urlopen(base.removesuffix('/api/v1')+'/',timeout=5) as response:
    assert b'<html' in response.read(), 'Static Web UI missing from runtime'
if '--check-persisted' in sys.argv:
    conversations=request('/conversations')
    assert any(c['message_count']==2 and c['status']=='completed' for c in conversations),conversations
else:
    cid=request('/conversations',{'demo':True,'configuration':{'max_turns':2}})['id']
    for attempt in range(100):
        conversation=request('/conversations/'+cid)
        if not conversation['active']:break
        time.sleep(.1)
    assert conversation['status']=='completed' and len(conversation['messages'])==2,conversation
print('Container API and demo persistence: OK')
