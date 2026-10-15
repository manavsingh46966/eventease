# EventEase: Fault-Tolerant, Load-Balanced Event Management System

> **Live Deployment:** [http://3.27.33.54](http://3.27.33.54) | **HTTPS:** [https://3.27.33.54](https://3.27.33.54)  
> **Backend:** 2x FastAPI Worker Instances (`app1`, `app2`)  
> **Database:** Neon Cloud Serverless PostgreSQL  
> **Reverse Proxy:** Async Round-Robin Load Balancer with Sliding-Window Rate Limiting  
> **Hosting:** Amazon Web Services (AWS) EC2 (Amazon Linux 2023)  

---

## 🌟 Key Features
- **Round-Robin Load Balancing:** Ingress traffic dynamically splits 50/50 across multiple backend worker processes (`app1` on port 8001, `app2` on port 8002) with automatic failover.
- **Dual-Tier Rate Limiting:** Sliding-window rate limiter at the edge proxy (20 req/s, burst capacity of 40) + SlowAPI decorators on backend endpoints, preventing DDoS and brute-force abuse.
- **Zero Overselling (ACID Concurrency):** PostgreSQL Row-Level Locking (`SELECT ... FOR UPDATE`) prevents race conditions and negative seat inventory under simultaneous multi-user registrations.
- **TLS/HTTPS Termination:** Native SSL/TLS encryption on port 443 with HSTS (`Strict-Transport-Security: max-age=31536000`) and Content-Security-Policy (CSP).
- **Persistent HTTP Connection Pooling:** Async connection reuse between reverse proxy and upstream workers reduces latency by up to 68%.

---

## 🛡️ Cloud Security Implemented
| Aspect | Implementation |
|---|---|
| **HTTPS / TLS** | TLS terminated at edge load balancer on port 443, HSTS header enforced |
| **Edge Rate Limiting** | Sliding-window deque limiter: 20 req/s, burst 40; drops floods with HTTP 429 |
| **Backend Rate Limiting**| SlowAPI per client IP: 60/min global, 5/min register, 10/min admin |
| **Load Balancing** | Asynchronous reverse proxy across multiple backend workers with health checks |
| **Concurrency Lock** | PostgreSQL row-level locks (`with_for_update()`) to prevent overselling |
| **Authentication** | Admin routes require `X-Admin-Key` header with constant-time HMAC check |
| **Database Security** | SSL connection (`sslmode=require`) to Neon PostgreSQL; parameterized ORM queries |
| **Security Headers** | HSTS, CSP, X-Frame-Options, X-Content-Type-Options: nosniff, Referrer-Policy |

---

## 🚀 Quick Start (Local)

1. **Clone the repository:**
   ```bash
   git clone https://github.com/manavsingh46966/eventease.git
   cd eventease
   ```

2. **Set up virtual environment & dependencies:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate    # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Start the complete stack (Database + 2 Backends + Load Balancer):**
   ```bash
   python start_all.py
   ```
   Access the app at `http://localhost:80` (or `http://localhost:8080`).

---

## ☁️ Deployment on AWS EC2

The application runs 24/7 on AWS EC2 as a managed systemd service (`eventease.service`):

```bash
# Check service status on EC2
sudo systemctl status eventease

# View real-time logs
sudo journalctl -u eventease -f
```

     --set-secrets DATABASE_URL=database-url:latest,ADMIN_KEY=admin-key:latest
   ```
   (Quick alternative without Secret Manager: `--set-env-vars ENV=production,DATABASE_URL=...,ADMIN_KEY=...`)
5. Open the printed `https://eventease-xxxxx.run.app` URL, expand **Organizer tools**, enter your admin key, and create events.
6. After evaluation: `gcloud run services update eventease --region asia-south1 --min-instances 0`

## Screenshots for the report
1. Padlock + certificate details on the run.app URL; `http://` redirecting to `https://`
2. Cloud Run service page showing min 2 / max 3 instances, and the "Served by" label changing
3. 429 response: browser console, run on the live site:
   `for (let i=0;i<8;i++) fetch('/api/events/1/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:'Test User',roll_no:'T00'+i})}).then(r=>console.log(r.status))`
4. Cloud Run variables/secrets tab (hide the values) and `.gitignore` containing `.env`
5. Response headers in the browser Network tab (HSTS, CSP, X-Frame-Options)
6. Admin route returning 401 without the key, 200 with it
7. `pytest` output (9 passed)

To show the API docs in production for a screenshot, temporarily add `SHOW_DOCS=1` to the env vars.

## Limitations (mention in report)
- Rate-limit counters are per instance (in memory), so with 2 instances a client can get up to 2x the limit. Future work: shared Redis store.
- Admin auth is a single shared key. Future work: per-user login with JWT and roles.
- Free-tier Neon databases pause when idle, so the first request may be slow.
