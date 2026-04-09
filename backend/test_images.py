"""Quick test: verify image_url is populated for meals and Pollinations URLs work."""
import httpx

BASE = "http://localhost:8000"

def main():
    # 1. Check meals have image_url
    print("=== CHECKING MEAL IMAGE URLs ===\n")
    r = httpx.get(f"{BASE}/api/meals?limit=5")
    meals = r.json()
    
    all_have_urls = True
    for m in meals:
        url = m.get("image_url")
        has_url = bool(url and len(url) > 10)
        icon = "✅" if has_url else "❌"
        print(f"  {icon} {m['name']}")
        if has_url:
            print(f"     URL: {url[:120]}...")
        else:
            print(f"     URL: MISSING!")
            all_have_urls = False
    
    print()
    
    # 2. Test the dedicated image endpoint with first meal
    if meals:
        meal_id = meals[0]["id"]
        print(f"=== TESTING IMAGE ENDPOINT: /api/meals/{meal_id}/image ===\n")
        r2 = httpx.get(f"{BASE}/api/meals/{meal_id}/image")
        if r2.status_code == 200:
            data = r2.json()
            print(f"  ✅ Status: {r2.status_code}")
            print(f"  Meal: {data.get('meal_name')}")
            print(f"  URL:  {data.get('image_url', '')[:120]}...")
        else:
            print(f"  ❌ Status: {r2.status_code} — {r2.text[:200]}")
    
    print()
    
    # 3. Test that Pollinations URL actually resolves (HEAD request)
    if meals and meals[0].get("image_url"):
        test_url = meals[0]["image_url"]
        print(f"=== TESTING POLLINATIONS.AI CONNECTIVITY ===\n")
        try:
            r3 = httpx.head(test_url, follow_redirects=True, timeout=15)
            ct = r3.headers.get("content-type", "unknown")
            print(f"  ✅ Pollinations responded: {r3.status_code}, content-type: {ct}")
        except Exception as e:
            print(f"  ⚠️  Pollinations timeout/error: {e}")
            print(f"     (This is expected if blocked by firewall — images load client-side)")
    
    print()
    
    # 4. Check diet plan meals also include image_url
    print("=== CHECKING DIET PLAN MEAL IMAGE URLs ===\n")
    # Login first
    lr = httpx.post(f"{BASE}/api/auth/login", json={
        "email": "phase_a_test@almadiet.com",
        "password": "test123456",
    })
    if lr.status_code == 200:
        token = lr.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        plans = httpx.get(f"{BASE}/api/diet/plans", headers=headers).json()
        if plans:
            plan = plans[0]
            for category in ["breakfast_meals", "lunch_meals", "dinner_meals", "snack_meals"]:
                meals_in_cat = plan.get(category, [])
                for m in meals_in_cat[:2]:
                    url = m.get("image_url")
                    icon = "✅" if url else "❌"
                    print(f"  {icon} [{category[:9]}] {m.get('name', '?')}: {'HAS URL' if url else 'MISSING'}")
        else:
            print("  ⚠️  No diet plans found")
    else:
        print(f"  ❌ Login failed: {lr.status_code}")
    
    print("\n" + "=" * 50)
    if all_have_urls:
        print("  🎉 All meals have image URLs!")
    else:
        print("  ⚠️  Some meals are missing image URLs")
    print("=" * 50)


if __name__ == "__main__":
    main()
