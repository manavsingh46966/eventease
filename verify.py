"""Verification script for EventEase full stack."""
import asyncio
import httpx
import json

async def run_tests():
    print("=" * 65)
    print("EVENT_EASE SYSTEM VERIFICATION")
    print("=" * 65)

    async with httpx.AsyncClient(verify=False) as client:
        # 1. Frontend check
        print("\n[1] Testing Frontend via Load Balancer (http://127.0.0.1:8080/):")
        r = await client.get("http://127.0.0.1:8080/")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        assert "EventEase" in r.text, "EventEase not found in HTML"
        print("    -> Frontend HTML served successfully (Status 200 OK)")

        # 2. Round-Robin Load Balancing check
        print("\n[2] Testing Round-Robin Load Balancing (http://127.0.0.1:8080/api/info):")
        instances = []
        for i in range(4):
            res = await client.get("http://127.0.0.1:8080/api/info")
            data = res.json()
            served_by = data.get("served_by")
            header_served = res.headers.get("x-served-by")
            instances.append(served_by)
            print(f"    Req #{i+1}: {served_by} (Header X-Served-By: {header_served})")

        assert len(set(instances)) > 1, f"Expected alternation, got {instances}"
        print(f"    -> Load balancer correctly alternated between instances: {set(instances)}")

        # 3. Database & Events API check
        print("\n[3] Testing Database and Events API (http://127.0.0.1:8080/api/events):")
        r_events = await client.get("http://127.0.0.1:8080/api/events")
        events = r_events.json()
        assert len(events) >= 3, f"Expected >= 3 events, got {len(events)}"
        print(f"    -> Database returned {len(events)} seeded events:")
        for e in events:
            print(f"       * Event #{e['id']}: {e['title']} | Date: {e['date']} | Seats: {e['seats_left']}/{e['total_seats']}")

        # 4. HTTPS / TLS Termination check
        print("\n[4] Testing HTTPS / TLS Endpoint (https://127.0.0.1:8443/api/info):")
        r_https = await client.get("https://127.0.0.1:8443/api/info")
        assert r_https.status_code == 200, f"Expected 200, got {r_https.status_code}"
        print(f"    -> HTTPS Status: {r_https.status_code} OK")
        print(f"    -> Served over TLS by: {r_https.json().get('served_by')}")
        print(f"    -> Strict-Transport-Security: {r_https.headers.get('strict-transport-security')}")
        print(f"    -> Content-Security-Policy: {r_https.headers.get('content-security-policy')[:45]}...")

        # 5. Rate Limiting check (Concurrent Burst)
        print("\n[5] Testing Rate Limiting (Concurrent Burst Test on Load Balancer):")
        tasks = [client.get("http://127.0.0.1:8080/lb-status") for _ in range(45)]
        responses = await asyncio.gather(*tasks)
        statuses = [resp.status_code for resp in responses]
        count_200 = statuses.count(200)
        count_429 = statuses.count(429)
        print(f"    -> Sent 45 concurrent requests: {count_200} allowed (200), {count_429} rejected with 429 Too Many Requests")
        assert count_429 > 0, "Expected at least one 429 response"
        print("    -> Edge Rate Limiting verified and actively protecting the stack!")

        # Cooldown for rate limiter before next test
        print("    -> Cooling down 2.2s for token bucket refill...")
        await asyncio.sleep(2.2)

        # 6. Admin Authentication check
        print("\n[6] Testing Admin Authentication (/api/admin/events):")
        r_unauth = await client.post("http://127.0.0.1:8080/api/admin/events", json={})
        assert r_unauth.status_code == 401, f"Expected 401, got {r_unauth.status_code}"
        print("    -> Unauthorized admin request correctly rejected with 401 Unauthorized")

        r_auth = await client.get("http://127.0.0.1:8080/api/admin/events/1/registrations", headers={"X-Admin-Key": "secret"})
        assert r_auth.status_code == 200, f"Expected 200, got {r_auth.status_code}"
        print("    -> Authorized admin request with valid X-Admin-Key succeeded with 200 OK")

    print("\n" + "=" * 65)
    print("ALL 6 ARCHITECTURAL COMPONENTS ARE VERIFIED AND RUNNING!")
    print("=" * 65)

if __name__ == "__main__":
    asyncio.run(run_tests())
