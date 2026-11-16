#!/usr/bin/env python3
"""
Minimale demo van het consent-mechanisme (cat 1) + PEP-resolver.
Consent geldt PER DOSSIER: één instemming dekt alle cat-1-documenten
binnen dat dossier; een ander dossier (of een los document) vereist
opnieuw instemmen.
Alleen Python stdlib. Draait op http://localhost:8000
"""
import base64, hashlib, hmac, json, secrets, time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs, quote

SECRET = b"demo-server-geheim"        # prod: uit secret manager
COOKIE_NAME = "edepot_consent"
CONSENT_TTL = 24 * 3600               # cookie ~24u
PRESIGN_TTL = 300                     # delivery-URL ~5 min
POW_DIFFICULTY = 3                    # ALTCHA: aantal leading-zero hex-tekens

DOCS = {
    "tekening-001": {"title": "Bouwtekening Stationsgebied (blad 1)", "cat": 1,
                     "dossier": "dossier-bouw-1",
                     "body": b"FAKE-PDF: bouwtekening Stationsgebied blad 1..."},
    "tekening-002": {"title": "Bouwtekening Stationsgebied (blad 2)", "cat": 1,
                     "dossier": "dossier-bouw-1",
                     "body": b"FAKE-PDF: bouwtekening Stationsgebied blad 2..."},
    "tekening-003": {"title": "Bouwtekening Stationsgebied (blad 3)", "cat": 1,
                     "dossier": "dossier-bouw-1",
                     "body": b"FAKE-PDF: bouwtekening Stationsgebied blad 3..."},
    "tekening-010": {"title": "Bouwtekening De Uithof (ander dossier)", "cat": 1,
                     "dossier": "dossier-bouw-2",
                     "body": b"FAKE-PDF: bouwtekening De Uithof..."},
    "losse-tekening": {"title": "Losse bouwtekening (geen dossier)", "cat": 1,
                     "dossier": None,
                     "body": b"FAKE-PDF: losse tekening..."},
    "krant-1953":   {"title": "Utrechts Nieuwsblad, 2 feb 1953", "cat": 0,
                     "body": b"FAKE-KRANT-INHOUD..."},
    "dossier-x":    {"title": "Bouwdossier (cat 3, geen login in demo)", "cat": 3,
                     "dossier": "dossier-openbaar-1",
                     "body": b"GEHEIM"},
    # beleidsrecord in dezelfde index: de voorwaarden zijn data,
    # geen code. Bij een wijziging: version ophogen → alle bestaande
    # consent-cookies worden automatisch ongeldig.
    "terms:default": {
        "version": "2026-11",
        "text": ("Ik verklaar dat ik het materiaal dat ik via deze "
                 "voorziening download alleen voor persoonlijk gebruik zal "
                 "gebruiken en niet zal delen met anderen."),
    },
}

def terms_record():
    """De geldende voorwaarden komen uit de index (beleidsrecord),
    niet uit de viewer of code."""
    return DOCS["terms:default"]

def is_document(rec) -> bool:
    return isinstance(rec, dict) and "cat" in rec

# ---------- ALTCHA-achtig proof-of-work (demo-simulatie) ----------
# Server geeft een challenge; de client moet een nonce vinden zodat
# sha256(challenge + nonce) met POW_DIFFICULTY nullen begint.
# Onzichtbaar voor mensen (~1s CPU), kostbaar voor bots.

def pow_challenge() -> str:
    return secrets.token_hex(8)

def pow_verify(challenge: str, nonce: str) -> bool:
    if not challenge or not nonce.isdigit():
        return False
    h = hashlib.sha256(f"{challenge}{nonce}".encode()).hexdigest()
    return h.startswith("0" * POW_DIFFICULTY)

# ---------- crypto helpers (in prod: JWT-bibliotheek) ----------

def b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

def b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))

def sign(data: bytes) -> str:
    return b64e(hmac.new(SECRET, data, hashlib.sha256).digest())

def make_cookie(scopes, terms_version: str) -> str:
    """scopes: bv. {"dossier:dossier-bouw-1", "doc:losse-tekening"}"""
    payload = b64e(json.dumps({
        "consented": sorted(scopes),
        "terms_version": terms_version,
        "pow": True,
        "iat": int(time.time()),
        "exp": int(time.time()) + CONSENT_TTL,
    }).encode())
    return f"{payload}.{sign(payload.encode())}"

def read_cookie(value: str | None):
    """Retourneert {"scopes": set, "terms_version": str}, of None bij
    ongeldige/verlopen cookie."""
    if not value or "." not in value:
        return None
    payload, sig = value.rsplit(".", 1)
    if not hmac.compare_digest(sig, sign(payload.encode())):
        return None
    try:
        data = json.loads(b64d(payload))
        if data.get("exp", 0) <= time.time():
            return None
        return {"scopes": set(data.get("consented", [])),
                "terms_version": data.get("terms_version")}
    except Exception:
        return None

def needed_scope(doc, doc_id: str) -> str:
    """De scope die voor dit document vereist is: dossier of — als het
    document in geen dossier zit — het document zelf."""
    return f"dossier:{doc['dossier']}" if doc.get("dossier") else f"doc:{doc_id}"

def scope_omschrijving(scope: str) -> str:
    kind, _, ref = scope.partition(":")
    if kind == "dossier":
        n = sum(1 for d in DOCS.values()
                if is_document(d) and d["cat"] == 1 and d.get("dossier") == ref)
        return f"alle cat-1-documenten in dossier '{ref}' ({n} documenten)"
    titel = DOCS.get(ref, {}).get("title", ref)
    return f"het document '{titel}'"

def presign(doc_id: str) -> str:
    """simuleert een S3 presigned URL"""
    exp = int(time.time()) + PRESIGN_TTL
    sig = sign(f"{doc_id}:{exp}".encode())
    return f"/file/{doc_id}?exp={exp}&sig={sig}"

# ---------- HTTP ----------

class H(BaseHTTPRequestHandler):
    def _send(self, code, body=b"", ctype="text/html; charset=utf-8", headers=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body if isinstance(body, bytes) else body.encode())

    def _json(self, code, obj):
        self._send(code, json.dumps(obj), "application/json")

    def _get_cookie(self, name):
        for part in self.headers.get("Cookie", "").split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                if k == name:
                    return v
        return None

    # --- de 'domme' viewer: HTML + piepklein JS dat aan de PEP vraagt wat te doen ---
    def do_GET(self):
        u = urlparse(self.path)
        path = u.path
        if path == "/":
            rows = "".join(
                f'<li><a href="/doc/{d}">{v["title"]}</a> '
                f'<small>[cat {v["cat"]}]</small></li>'
                for d, v in DOCS.items() if is_document(v))
            return self._send(200, f"<h1>E-depot demo</h1><ul>{rows}</ul>")

        if path.startswith("/doc/"):
            doc_id = path.rsplit("/", 1)[1]
            html = f"""<!doctype html><title>{doc_id}</title>
<h1>{doc_id}</h1><div id="app"> laden… </div>
<script>
async function solvePow(challenge, difficulty) {{
  const enc = new TextEncoder();
  const zeros = '0'.repeat(difficulty);
  for (let n = 0; n < 20000000; n++) {{
    const buf = await crypto.subtle.digest('SHA-256', enc.encode(challenge + n));
    const hex = [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2,'0')).join('');
    if (hex.startsWith(zeros)) return n;
  }}
  throw new Error('pow-timeout');
}}
fetch('/resolve/{doc_id}').then(async r => {{
  const j = await r.json().catch(() => ({{}}));
  if (r.ok && j.url) {{
    document.getElementById('app').innerHTML =
      '<p>Toegang verleend.</p><a href="'+j.url+'">Open document</a>';
  }} else if (j.action === 'consent') {{
    const app = document.getElementById('app');
    app.innerHTML =
      '<h2>Voorwaarden</h2><div id="terms"></div><p>' + j.scope_text + '</p>' +
      '<div id="powbox" style="border:1px solid #ccc;border-radius:6px;padding:8px 12px;display:inline-block;margin:8px 0"><span id="powicon">…</span> <span id="powstatus">Even een moment…</span></div>' +
      '<form method="post" id="cform" action="'+j.consent_url+'&tv='+j.terms_version+'">' +
      '<input type="hidden" name="challenge" value="'+j.pow_challenge+'">' +
      '<input type="hidden" name="nonce" id="nonce">' +
      '<button id="cbtn" disabled>Ik stem in</button></form>';
    document.getElementById('terms').textContent = j.terms;
    solvePow(j.pow_challenge, j.pow_difficulty).then(n => {{
      document.getElementById('nonce').value = n;
      document.getElementById('powicon').textContent = '✓';
      document.getElementById('powstatus').textContent = 'Geverifieerd';
      document.getElementById('powbox').style.borderColor = 'green';
      document.getElementById('powstatus').style.color = 'green';
      document.getElementById('cbtn').disabled = false;
    }}).catch(() => {{
      document.getElementById('powicon').textContent = '✗';
      document.getElementById('powstatus').textContent = 'Proof-of-work mislukt';
      document.getElementById('powstatus').style.color = 'red';
    }});
  }} else {{
    document.getElementById('app').textContent = 'Geen toegang (' + j.error + ')';
  }}
}});
</script>"""
            return self._send(200, html)

        if path == "/resolve" or path.startswith("/resolve/"):
            return self._resolve(path.rsplit("/", 1)[1])

        if path == "/consent":
            qs = parse_qs(u.query)
            ret = qs.get("return", ["/"])[0]
            scope = qs.get("scope", [""])[0]
            challenge = pow_challenge()
            return self._send(200, f"""<!doctype html><title>Toestemming</title>
<h2>Voorwaarden</h2>
<p>{terms_record()["text"]}</p>
<p><i>Versie {terms_record()["version"]}</i> — deze instemming geldt voor:
<b>{scope_omschrijving(scope)}</b>.</p>
<div id="powbox" style="border:1px solid #ccc;border-radius:6px;padding:8px 12px;display:inline-block;margin:8px 0"><span id="powicon">…</span> <span id="powstatus">Even een moment…</span></div>
<form method="post" id="cform" action="/consent?return={ret}&scope={quote(scope, safe='')}">
<input type="hidden" name="tv" value="{terms_record()["version"]}">
<input type="hidden" name="challenge" value="{challenge}">
<input type="hidden" name="nonce" id="nonce">
<button id="cbtn" disabled>Ik stem in</button></form>
<script>
async function solvePow(challenge, difficulty) {{
  const enc = new TextEncoder();
  const zeros = '0'.repeat(difficulty);
  for (let n = 0; n < 20000000; n++) {{
    const buf = await crypto.subtle.digest('SHA-256', enc.encode(challenge + n));
    const hex = [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2,'0')).join('');
    if (hex.startsWith(zeros)) return n;
  }}
  throw new Error('pow-timeout');
}}
solvePow('{challenge}', {POW_DIFFICULTY}).then(n => {{
  document.getElementById('nonce').value = n;
  document.getElementById('powicon').textContent = '✓';
  document.getElementById('powstatus').textContent = 'Geverifieerd';
  document.getElementById('powbox').style.borderColor = 'green';
  document.getElementById('powstatus').style.color = 'green';
  document.getElementById('cbtn').disabled = false;
}}).catch(() => {{
  document.getElementById('powicon').textContent = '✗';
  document.getElementById('powstatus').textContent = 'Proof-of-work mislukt';
  document.getElementById('powstatus').style.color = 'red';
}});
</script>""")

        if path.startswith("/file/"):
            return self._file(u)

        self._send(404, b"niet gevonden")

    def do_POST(self):
        u = urlparse(self.path)
        if u.path == "/consent":
            # parameters kunnen in query én in form-body zitten
            qs = parse_qs(u.query)
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                for k, v in parse_qs(self.rfile.read(length).decode()).items():
                    qs.setdefault(k, v)
            # ALTCHA: server-side verificatie van de proof-of-work
            if not pow_verify(qs.get("challenge", [""])[0],
                              qs.get("nonce", [""])[0]):
                return self._send(403,
                    "<h2>Proof-of-work mislukt</h2>"
                    "<p>De verificatie is niet geslaagd — probeer het "
                    "opnieuw.</p>")
            ret = qs.get("return", ["/"])[0]
            scope = qs.get("scope", [""])[0]

            # bestaande scopes behouden (meerdere dossiers cumulatief),
            # nieuwe scope toevoegen; terms-versie van de getoonde tekst
            # wordt mee vastgelegd in de cookie
            existing = read_cookie(self._get_cookie(COOKIE_NAME))
            scopes = existing["scopes"] if existing else set()
            if scope:
                scopes.add(scope)
            tv = qs.get("tv", [terms_record()["version"]])[0]
            cookie = make_cookie(scopes, tv)

            self.send_response(303)
            self.send_header("Location", ret)
            self.send_header("Set-Cookie",
                f"{COOKIE_NAME}={cookie}; Path=/; HttpOnly; SameSite=Lax; "
                f"Max-Age={CONSENT_TTL}")
            self.end_headers()
            return
        self._send(404, b"niet gevonden")

    # --- PEP: de enige plek die beslist ---
    def _resolve(self, doc_id):
        doc = DOCS.get(doc_id)
        if not doc or not is_document(doc):
            return self._json(404, {"error": "unknown_document"})
        cat = doc["cat"]

        if cat == 0:
            return self._json(200, {"url": presign(doc_id)})

        if cat == 1:
            scope = needed_scope(doc, doc_id)
            cookie = read_cookie(self._get_cookie(COOKIE_NAME))
            # consent geldt alleen als de scope erin zit EN de cookie de
            # huidige terms-versie dekt (wijziging → opnieuw instemmen)
            if (cookie and cookie["terms_version"] == terms_record()["version"]
                    and scope in cookie["scopes"]):
                return self._json(200, {"url": presign(doc_id)})
            # PEP geeft instructie, geen doodlopende 403 — inclusief de
            # condities-tekst en -versie die op dat moment gelden
            return self._json(403, {
                "error": "consent_required",
                "action": "consent",
                "scope": scope,
                "scope_text": ("Deze instemming geldt voor: "
                               + scope_omschrijving(scope) + "."),
                "terms": terms_record()["text"],
                "terms_version": terms_record()["version"],
                "pow_challenge": pow_challenge(),
                "pow_difficulty": POW_DIFFICULTY,
                "consent_url": ("/consent?return=" + quote(f"/doc/{doc_id}", safe="")
                                + "&scope=" + quote(scope, safe="")),
            })

        # cat 3: in een echte setup login/grant-check; hier gewoon weigeren
        return self._json(403, {"error": "login_required"})

    # --- simuleert S3: alleen geldige presigned URL's ---
    def _file(self, u):
        parts = u.path.strip("/").split("/")      # file/<id>
        doc_id = parts[1] if len(parts) > 1 else ""
        qs = parse_qs(u.query)
        exp, sig = qs.get("exp", ["0"])[0], qs.get("sig", [""])[0]
        valid = (is_document(DOCS.get(doc_id)) and int(exp) > time.time()
                 and hmac.compare_digest(sig, sign(f"{doc_id}:{exp}".encode())))
        if not valid:
            return self._send(403, b"AccessDenied (S3 zou dit geven)")
        return self._send(200, DOCS[doc_id]["body"],
                          "application/octet-stream",
                          {"Content-Disposition": f'attachment; filename="{doc_id}.bin"'})

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} {fmt % args}")

if __name__ == "__main__":
    print("Demo op http://localhost:8000")
    # 0.0.0.0 zodat Docker port-forwarding en lokale runs allebei werken
    HTTPServer(("0.0.0.0", 8000), H).serve_forever()
