import os, requests, json, sys
PASS = os.environ.get("LAN_PANEL_PASS", "")
if not PASS:
    sys.exit("укажите LAN_PANEL_PASS в окружении")
s = requests.Session()
r = s.get('http://127.0.0.1:8080/login')
token = r.text.split('name="csrf_token" value="')[1].split('"')[0]
s.post('http://127.0.0.1:8080/login', data={'username':'admin','password':PASS,'csrf_token':token})

for path in ['/api/status', '/api/network/check', '/api/system/health']:
    r = s.get(f'http://127.0.0.1:8080{path}', timeout=15)
    print(f'{path}: {r.status_code} ({len(r.text)} bytes)')
    if r.status_code == 200:
        try:
            d = json.loads(r.text)
            print(f'  Keys: {list(d.keys())[:5]}')
        except:
            print(f'  Not JSON: {r.text[:100]}')
    else:
        print(f'  Response: {r.text[:100]}')
