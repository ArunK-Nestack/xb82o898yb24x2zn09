"""Run: python test_assessment_detector.py  (no network, no OpenAI).

Guards that the new cybersecurity-secure-api type is detected from the record-ownership shape and
does not steal the OTP build (which also uses bcrypt and 429)."""
from services.assessment_detector import detect_assessment_type


def evidence(readme="", sources=None, files=None, config=None):
    return {
        "readmeText": readme,
        "sourceFiles": sources or {},
        "fileList": files or [],
        "configFiles": config or {},
    }


SECURE_API = evidence(
    readme="# Secure Records API\nMulti-tenant records. Each record has an owner_id; GET /records/:id "
    "returns 403 if you are not the owner. Admin role is assigned server-side only; a user cannot set "
    "role. Passwords hashed with bcrypt. Login lockout returns 429. Object-level access control.",
    sources={
        "app/routes.py": "if record.owner_id != current_user.id and current_user.role != 'admin': abort(403)\n"
        "db.execute('SELECT * FROM records WHERE id = ?', (rid,))",
        "app/auth.py": "bcrypt.hashpw(pw, salt)  # /records owner check",
    },
    files=["app/routes.py", "app/auth.py"],
)

# Follows the PDF's routes but with a terse README and user_id instead of owner_id. bcrypt, brute
# force and compare_digest used to hand this to robust-otp 45 vs 30.
SECURE_API_TERSE = evidence(
    readme="# My submission\nPOST /register, POST /login, POST /records, GET /records/:id.\n"
    "Passwords use bcrypt. 5 failed logins -> 429 to stop brute force. Tokens compared with hmac.compare_digest.",
    sources={
        "app.py": "@app.post('/records')\n@app.get('/records/<rid>')\n"
        "if rec['user_id'] != g.user['id']: abort(404)\nbcrypt.checkpw(pw, h)\nhmac.compare_digest(sig, expected)",
    },
    files=["app.py", "README.md"],
)

# Node build of the brief: userId comparison, timingSafeEqual, signed tokens, login attempt counter.
SECURE_API_NODE = evidence(
    readme="Run with npm start. Lockout after 5 failed attempts returns 429 (brute-force protection).",
    sources={
        "src/routes.js": "router.post('/register', register)\nrouter.post('/login', login)\n"
        "router.post('/records', auth, create)\nrouter.get('/records/:id', auth, (req, res) => {\n"
        "  if (rec.userId !== req.user.id && req.user.role !== 'admin') return res.status(403).end() })",
        "src/auth.js": "const ok = await bcrypt.compare(pw, user.hash)\ncrypto.timingSafeEqual(sig, expected)\n"
        "user.loginAttempts += 1 // signature verified on every request",
    },
    files=["src/routes.js", "src/auth.js", "package.json"],
)

OTP = evidence(
    readme="# Abuse-resistant OTP\nSend OTP and verify OTP with brute-force lockout after 5 attempts, "
    "returns 429. bcrypt hashed OTP, constant-time compare_digest. CSPRNG via secrets.token_bytes.",
    sources={"auth.py": "hmac.compare_digest(a, b)\nsend otp / verify otp"},
)

WEBHOOK = evidence(
    readme="# Webhook delivery engine\nHMAC-SHA256 X-Signature header, retry schedule, dead event after 5 delivery attempts.",
    sources={"delivery.py": "next_attempt_at = now + backoff(attempt)\nPOST /events webhook_url"},
)

CASES = [
    (SECURE_API, "cybersecurity-secure-api"),
    (SECURE_API_TERSE, "cybersecurity-secure-api"),
    (SECURE_API_NODE, "cybersecurity-secure-api"),
    (OTP, "robust-otp"),
    (WEBHOOK, "webhook"),
]

failed = 0
for ev, expected in CASES:
    got = detect_assessment_type(ev)
    ok = got == expected
    failed += not ok
    print(f"{'ok  ' if ok else 'FAIL'} expected {expected:26} got {got}")
raise SystemExit(1 if failed else 0)
