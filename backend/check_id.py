import httpx
r = httpx.post('http://localhost:8000/api/auth/login', json={'email':'phase_a_test@almadiet.com','password':'test123456'})
t = r.json()['access_token']
plans = httpx.get('http://localhost:8000/api/diet/plans', headers={'Authorization':f'Bearer {t}'}).json()
m = plans[0]['breakfast_meals'][0]
print(f"Keys: {list(m.keys())}")
print(f"id = '{m.get('id')}'")
print(f"meal_id = '{m.get('meal_id')}'")
print(f"id type: {type(m.get('id'))}")
