"""
AlmaDiet — Comprehensive API Endpoint Test Script
Tests all endpoints end-to-end against the running server.
"""
import asyncio
import httpx
import json
import sys

BASE = "http://localhost:8000"
PASS = []
FAIL = []

def report(name, status, detail=""):
    icon = "✅" if status else "❌"
    print(f"  {icon} {name}" + (f" — {detail}" if detail else ""))
    (PASS if status else FAIL).append(name)


async def run_tests():
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:

        # ━━━━ 1. ROOT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        print("\n🔹 ROOT")
        r = await c.get("/")
        report("GET /", r.status_code == 200, f"{r.status_code}")

        r = await c.get("/health")
        report("GET /health", r.status_code == 200, f"{r.json()}")

        # ━━━━ 2. AUTH ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        print("\n🔹 AUTH")
        # Register
        r = await c.post("/api/auth/register", json={
            "email": "phase_a_test@almadiet.com",
            "password": "test123456",
            "name": "Phase A Test",
            "region": "kerala",
            "language": "ml",
            "age": 26,
            "height_cm": 160,
            "pre_pregnancy_weight_kg": 55,
        })
        if r.status_code == 201:
            token = r.json()["access_token"]
            user_id = r.json()["user"]["id"]
            report("POST /api/auth/register", True, f"user_id={user_id[:8]}...")
        elif r.status_code == 400 and "already" in r.text.lower():
            # User exists, login instead
            r = await c.post("/api/auth/login", json={
                "email": "phase_a_test@almadiet.com",
                "password": "test123456",
            })
            token = r.json()["access_token"]
            user_id = r.json()["user"]["id"]
            report("POST /api/auth/register", True, "user exists, logged in")
        else:
            report("POST /api/auth/register", False, f"{r.status_code}: {r.text[:100]}")
            print("   ⛔ Cannot continue without auth")
            return

        headers = {"Authorization": f"Bearer {token}"}

        # Login
        r = await c.post("/api/auth/login", json={
            "email": "phase_a_test@almadiet.com",
            "password": "test123456",
        })
        report("POST /api/auth/login", r.status_code == 200, f"{r.status_code}")

        # Get profile
        r = await c.get("/api/auth/me", headers=headers)
        report("GET /api/auth/me", r.status_code == 200, f"name={r.json().get('name')}")

        # Update profile
        r = await c.put("/api/auth/me", headers=headers, json={"phone": "9876543210"})
        report("PUT /api/auth/me", r.status_code == 200, f"phone={r.json().get('phone')}")

        # ━━━━ 3. HEALTH ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        print("\n🔹 HEALTH RECORDS")
        r = await c.post("/api/health/record", headers=headers, json={
            "trimester": 2,
            "week_number": 20,
            "current_weight_kg": 62.5,
            "bmi": 24.4,
            "blood_pressure_sys": 118,
            "blood_pressure_dia": 76,
            "hemoglobin": 10.8,
            "blood_sugar_fasting": 88,
            "allergies": ["peanuts"],
            "medical_conditions": [],
            "is_vegetarian": False,
            "dietary_preference": "nonveg",
            "notes": "Feeling good, mild fatigue",
        })
        report("POST /api/health/record", r.status_code == 201, f"{r.status_code}")
        if r.status_code == 201:
            health_record_id = r.json()["id"]
        else:
            report("POST /api/health/record", False, f"FAILED: {r.text[:200]}")
            health_record_id = None

        # List records
        r = await c.get("/api/health/records", headers=headers)
        report("GET /api/health/records", r.status_code == 200, f"count={len(r.json())}")

        # Analyze
        if health_record_id:
            r = await c.get(f"/api/health/analyze/{health_record_id}", headers=headers)
            if r.status_code == 200:
                analysis = r.json()
                report("GET /api/health/analyze/{id}", True,
                       f"BMI={analysis.get('bmi_status')}, BP={analysis.get('bp_status')}, Hb={analysis.get('hemoglobin_status')}")
                if analysis.get("corrections"):
                    print(f"     📋 Corrections: {analysis['corrections'][:2]}")
                if analysis.get("alerts"):
                    print(f"     ⚠️  Alerts: {analysis['alerts'][:2]}")
            else:
                report("GET /api/health/analyze/{id}", False, f"{r.status_code}: {r.text[:200]}")

        # ━━━━ 4. DIET PLAN ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        print("\n🔹 DIET PLANS")
        if health_record_id:
            r = await c.post("/api/diet/generate", headers=headers, json={
                "health_record_id": health_record_id,
            })
            if r.status_code == 201:
                plan = r.json()
                diet_plan_id = plan["id"]
                n_bfast = len(plan.get("breakfast_meals", []))
                n_lunch = len(plan.get("lunch_meals", []))
                n_dinner = len(plan.get("dinner_meals", []))
                n_snack = len(plan.get("snack_meals", []))
                report("POST /api/diet/generate", True,
                       f"B={n_bfast} L={n_lunch} D={n_dinner} S={n_snack}, "
                       f"target_cal={plan.get('target_calories')}")
                if plan.get("dietary_alerts"):
                    print(f"     ⚠️  Alerts: {plan['dietary_alerts']}")
                # Print first breakfast meal name
                if plan.get("breakfast_meals"):
                    print(f"     🍳 First breakfast: {plan['breakfast_meals'][0].get('name')}")
            else:
                report("POST /api/diet/generate", False, f"{r.status_code}: {r.text[:300]}")
                diet_plan_id = None
        else:
            report("POST /api/diet/generate", False, "skipped — no health record")
            diet_plan_id = None

        # List plans
        r = await c.get("/api/diet/plans", headers=headers)
        report("GET /api/diet/plans", r.status_code == 200, f"count={len(r.json())}")

        # Get single plan
        if diet_plan_id:
            r = await c.get(f"/api/diet/plan/{diet_plan_id}", headers=headers)
            report("GET /api/diet/plan/{id}", r.status_code == 200, f"{r.status_code}")

        # Submit feedback
        if diet_plan_id:
            r = await c.post("/api/diet/feedback", headers=headers, json={
                "diet_plan_id": diet_plan_id,
                "feedback": "Meals look great but I prefer less spicy options",
                "rating": 4,
            })
            report("POST /api/diet/feedback", r.status_code == 200, f"rating=4")

        # ━━━━ 5. EMERGENCY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        print("\n🔹 EMERGENCY")
        r = await c.post("/api/emergency/report", headers=headers, json={
            "emergency_type": "GDM",
            "description": "Blood sugar spiked to 140 after meal",
        })
        if r.status_code == 201:
            emergency = r.json()
            emergency_id = emergency["id"]
            report("POST /api/emergency/report", True,
                   f"type={emergency.get('emergency_type')}")
            if emergency.get("modified_diet_restrictions"):
                print(f"     🚫 Restrictions: {json.dumps(emergency['modified_diet_restrictions'], indent=2)[:200]}")
        else:
            report("POST /api/emergency/report", False, f"{r.status_code}: {r.text[:200]}")
            emergency_id = None

        # List emergencies
        r = await c.get("/api/emergency/list", headers=headers)
        report("GET /api/emergency/list", r.status_code == 200, f"count={len(r.json())}")

        # Resolve
        if emergency_id:
            r = await c.post("/api/emergency/resolve", headers=headers, json={
                "emergency_id": emergency_id,
            })
            report("POST /api/emergency/resolve", r.status_code == 200, f"resolved={r.json().get('is_active') == False}")

        # ━━━━ 6. MEALS (Filters) ━━━━━━━━━━━━━━━━━━━━━━━━━
        print("\n🔹 MEAL FILTERS")
        # By trimester
        r = await c.get("/api/meals?trimester=2&limit=5")
        report("GET /api/meals?trimester=2",
               r.status_code == 200 and len(r.json()) > 0,
               f"count={len(r.json())}")

        # By meal type
        r = await c.get("/api/meals?meal_type=Breakfast&limit=5")
        report("GET /api/meals?meal_type=Breakfast",
               r.status_code == 200 and len(r.json()) > 0,
               f"count={len(r.json())}")

        # By region
        r = await c.get("/api/meals?region=Tamil+Nadu&limit=5")
        report("GET /api/meals?meal_type=Tamil Nadu",
               r.status_code == 200 and len(r.json()) > 0,
               f"count={len(r.json())}")

        # Vegetarian
        r = await c.get("/api/meals?is_vegetarian=true&limit=5")
        report("GET /api/meals?is_vegetarian=true",
               r.status_code == 200 and len(r.json()) > 0,
               f"count={len(r.json())}")

        # Single meal by ID
        meals_r = await c.get("/api/meals?limit=1")
        if meals_r.status_code == 200 and meals_r.json():
            meal_id = meals_r.json()[0]["id"]
            r = await c.get(f"/api/meals/{meal_id}")
            report("GET /api/meals/{id}", r.status_code == 200,
                   f"name={r.json().get('name')}")

    # ━━━━ SUMMARY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n" + "=" * 60)
    print(f"  🎯 RESULTS: {len(PASS)} passed, {len(FAIL)} failed")
    print("=" * 60)
    if FAIL:
        print(f"\n  ❌ Failed: {', '.join(FAIL)}")
    else:
        print(f"\n  🎉 All {len(PASS)} endpoints working perfectly!")


if __name__ == "__main__":
    asyncio.run(run_tests())
