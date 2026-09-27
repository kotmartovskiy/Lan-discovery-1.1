import requests, json
s = requests.Session()
r = s.get('http://127.0.0.1:8080/login')
token = r.text.split('name="csrf_token" value="')[1].split('"')[0]
s.post('http://127.0.0.1:8080/login', data={'username':'admin','password':'1234','csrf_token':token})

r = s.get('http://127.0.0.1:8080/api/status', timeout=15)
d = json.loads(r.text)
for k, v in d.items():
    print(f"  {k}: {v}")
