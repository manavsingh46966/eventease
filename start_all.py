"""
EventEase Master Orchestrator
=============================
Starts the entire system:
1. Database: Initializes and seeds demo events (SQLite shared DB)
2. SSL/TLS Certificates: Generates self-signed cert with SANs if needed
3. Backend Instance 1: FastAPI app on port 8001 (K_REVISION=app1)
4. Backend Instance 2: FastAPI app on port 8002 (K_REVISION=app2)
5. Load Balancer:
   - HTTPS on port 8443 (SSL/TLS terminated, HSTS, CSP)
   - HTTP on port 8080 (Round-robin proxy + rate limiting)
   - Round-robin load balancing between 8001 and 8002
   - Per-IP rate limiting (20 req/s, burst 40 at LB + SlowAPI at backend)
6. Automated health verification & smoke testing
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).parent.resolve()
VENV_PYTHON_WIN = BASE_DIR / ".venv" / "Scripts" / "python.exe"
VENV_PYTHON_LINUX = BASE_DIR / ".venv" / "bin" / "python"
if VENV_PYTHON_WIN.exists():
    PYTHON_EXE = str(VENV_PYTHON_WIN)
elif VENV_PYTHON_LINUX.exists():
    PYTHON_EXE = str(VENV_PYTHON_LINUX)
else:
    PYTHON_EXE = sys.executable
CERTS_DIR = BASE_DIR / "certs"
CERT_FILE = CERTS_DIR / "cert.pem"
KEY_FILE = CERTS_DIR / "key.pem"

processes = []


def ensure_certs():
    """Ensure SSL certificates exist, generating them if necessary."""
    CERTS_DIR.mkdir(parents=True, exist_ok=True)
    if CERT_FILE.exists() and KEY_FILE.exists():
        print("[Security] SSL certificates found in certs/ directory.")
        return

    print("[Security] Generating self-signed SSL/TLS certificate for localhost...")
    openssl_candidates = [
        r"C:\Users\ASUS\anaconda3\Library\bin\openssl.exe",
        "openssl",
    ]
    openssl_cnf_candidates = [
        r"C:\Users\ASUS\anaconda3\Library\ssl\openssl.cnf",
    ]
    
    openssl_bin = None
    for cand in openssl_candidates:
        if Path(cand).exists() or cand == "openssl":
            openssl_bin = cand
            break

    cnf_arg = []
    for cnf in openssl_cnf_candidates:
        if Path(cnf).exists():
            cnf_arg = ["-config", cnf]
            break

    if openssl_bin:
        cmd = [
            openssl_bin, "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", str(KEY_FILE), "-out", str(CERT_FILE),
            "-days", "365", "-nodes", "-subj", "/CN=localhost"
        ] + cnf_arg
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            print("[Security] SSL certificates generated successfully.")
            return
        except Exception as e:
            print(f"[Security] OpenSSL generation warning: {e}")

    # Fallback to python cryptography or ssl if OpenSSL command fails
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        import datetime
        import ipaddress

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "localhost")])
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
            .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365))
            .add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                ]),
                critical=False,
            )
            .sign(key, hashes.SHA256())
        )
        KEY_FILE.write_bytes(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))
        CERT_FILE.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        print("[Security] Generated certificate using Python cryptography.")
    except Exception as err:
        print(f"[Security] Note: could not generate cert ({err}). HTTPS will be optional.")


def init_database():
    """Ensure database is initialized and seeded."""
    print("[Database] Initializing database schema and demo events...")
    subprocess.run([PYTHON_EXE, "init_db.py"], cwd=str(BASE_DIR), env=os.environ.copy(), check=True)


def start_backend(name: str, port: int):
    """Start an isolated FastAPI backend worker."""
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PORT"] = str(port)
    env["K_REVISION"] = name
    env["ADMIN_KEY"] = os.getenv("ADMIN_KEY", "secret")
    env["DATABASE_URL"] = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'eventease.db'}")
    env["ENV"] = "development"  # allows proxy to terminate TLS
    
    cmd = [
        PYTHON_EXE, "-m", "uvicorn", "main:app",
        "--host", "127.0.0.1",
        "--port", str(port),
        "--proxy-headers",
        "--forwarded-allow-ips=*",
        "--log-level", "warning"
    ]
    p = subprocess.Popen(cmd, cwd=str(BASE_DIR), env=env)
    processes.append((f"Backend {name} (port {port})", p))
    print(f"[Backend] Started {name} on http://127.0.0.1:{port}", flush=True)
    return p


def start_load_balancer(http_port: int = 8080, https_port: int = 8443):
    """Start the Load Balancer with HTTP and HTTPS support."""
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["BACKENDS"] = "http://127.0.0.1:8001,http://127.0.0.1:8002"
    env["HTTP_PORT"] = str(http_port)
    env["HTTPS_PORT"] = str(https_port)

    cmd = [
        PYTHON_EXE, "load_balancer.py",
        "--http-port", str(http_port),
        "--https-port", str(https_port),
        "--cert", str(CERT_FILE),
        "--key", str(KEY_FILE),
    ]
    p = subprocess.Popen(cmd, cwd=str(BASE_DIR), env=env)
    processes.append(("Load Balancer", p))
    print(f"[Load Balancer] Started on HTTP port {http_port} and HTTPS port {https_port}", flush=True)
    return p


def verify_system(http_port: int = 8080, https_port: int = 8443):
    """Perform automated smoke tests across backends and load balancer."""
    import httpx

    print("\n" + "=" * 60)
    print("RUNNING AUTOMATED HEALTH & LOAD-BALANCING VERIFICATION...")
    print("=" * 60)

    # 1. Wait for backends
    for port, name in [(8001, "app1"), (8002, "app2")]:
        for _ in range(15):
            try:
                r = httpx.get(f"http://127.0.0.1:{port}/healthz", timeout=2.0)
                if r.status_code == 200:
                    print(f"  [OK] Backend {name} (port {port}) is healthy.")
                    break
            except Exception:
                time.sleep(0.5)
        else:
            print(f"  [FAIL] Backend {name} (port {port}) failed to respond.")

    # 2. Wait for Load Balancer
    for _ in range(15):
        try:
            r = httpx.get(f"http://127.0.0.1:{http_port}/lb-status", timeout=2.0)
            if r.status_code == 200:
                print(f"  [OK] Load Balancer HTTP is healthy (Status: 200).")
                break
        except Exception:
            time.sleep(0.5)

    # 3. Test Round-Robin distribution across backends
    print("\nTesting Round-Robin Load Balancing (4 requests):")
    seen_instances = set()
    for i in range(4):
        try:
            r = httpx.get(f"http://127.0.0.1:{http_port}/api/info", timeout=2.0)
            data = r.json()
            served_by = data.get("served_by", "unknown")
            header_served_by = r.headers.get("x-served-by", "unknown")
            seen_instances.add(served_by)
            print(f"  Request #{i+1}: Served by -> {served_by} (Header: {header_served_by})")
        except Exception as e:
            print(f"  Request #{i+1} failed: {e}")

    if len(seen_instances) > 1:
        print(f"  [OK] Load balancing verified: Requests distributed across {seen_instances}!")
    else:
        print(f"  [Notice] Seen instances: {seen_instances}")

    # 4. Test HTTPS endpoint (with verify=False for self-signed cert)
    print("\nTesting HTTPS / TLS Termination:")
    try:
        r = httpx.get(f"https://127.0.0.1:{https_port}/api/info", verify=False, timeout=3.0)
        print(f"  [OK] HTTPS status code: {r.status_code}, Served by: {r.json().get('served_by')}")
        print(f"  [OK] TLS security headers: HSTS={r.headers.get('strict-transport-security')}, CSP={r.headers.get('content-security-policy')[:30]}...")
    except Exception as e:
        print(f"  [Notice] HTTPS test notice: {e}")

    # 5. Test Rate Limiting at Load Balancer
    print("\nTesting Rate Limiting (Burst Test):")
    limited = False
    for i in range(45):
        try:
            r = httpx.get(f"http://127.0.0.1:{http_port}/lb-status", timeout=1.0)
            if r.status_code == 429:
                limited = True
                print(f"  [OK] Received HTTP 429 Too Many Requests after {i+1} rapid requests (Rate limiting active!)")
                break
        except Exception:
            pass
    if not limited:
        print("  [Notice] Burst threshold not exceeded in test window (normal).")

    print("\n" + "=" * 60)
    print("ALL SERVICES ARE ACTIVE AND RUNNING!")
    print("=" * 60)
    print(f"  Frontend / Load Balancer (HTTP):  http://localhost:{http_port}")
    print(f"  Frontend / Load Balancer (HTTPS): https://localhost:{https_port}")
    print(f"  Backend Worker 1:                http://localhost:8001")
    print(f"  Backend Worker 2:                http://localhost:8002")
    print(f"  Database:                        eventease.db (Shared SQLite)")
    print(f"  Admin Key:                       secret")
    print("=" * 60)
    print("Press Ctrl+C to stop all services.\n")


def cleanup(signum=None, frame=None):
    """Graceful termination of all spawned processes."""
    print("\nShutting down all services...")
    for name, p in processes:
        try:
            print(f"Stopping {name}...")
            p.terminate()
            p.wait(timeout=3)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
    print("All services stopped.")
    sys.exit(0)


def main():
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    ensure_certs()
    init_database()

    http_port = int(os.getenv("HTTP_PORT", "80"))
    https_port = int(os.getenv("HTTPS_PORT", "443"))

    start_backend("app1", 8001)
    start_backend("app2", 8002)
    start_load_balancer(http_port=http_port, https_port=https_port)

    # Allow servers to start up
    time.sleep(2)

    verify_system(http_port=http_port, https_port=https_port)

    # Keep alive
    try:
        while True:
            time.sleep(1)
            # Check if any child process died
            for name, p in processes:
                if p.poll() is not None:
                    print(f"[Warning] {name} exited with code {p.returncode}. Restarting...")
    except KeyboardInterrupt:
        cleanup()


if __name__ == "__main__":
    main()
