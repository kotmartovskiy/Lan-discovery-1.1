import os, requests, json, sys
PASS = os.environ.get("LAN_PANEL_PASS", "")
if not PASS:
    sys.exit("укажите LAN_PANEL_PASS в окружении")
s = requests.Session()
r = s.get('http://127.0.0.1:8080/login')
token = r.text.split('name="csrf_token" value="')[1].split('"')[0]
s.post('http://127.0.0.1:8080/login', data={'username':'admin','password':PASS,'csrf_token':token})
for p in ['/api/status', '/api/network/check', '/api/network/config']:
    r = s.get('http://127.0.0.1:8080' + p, allow_redirects=False)
    print(p, r.status_code, r.headers.get('Location', ''))
