#!/usr/bin/env python3
"""
Demo van de PEP-architectuur zoals beschreven in
architectuur-toegangsbeperkingen.md — afdwinging van alle vier de
categorieën, met alle rollen uit het model:

- Indexer = PDP: de DOCS-tabel simuleert de ES-index met de afgeleide
  velden (access_category, consent_scope via 'dossier', access_org)
  zoals de indexer die één keer berekend heeft.
- Resolver = PEP voor bytes (/resolve): beslist cat + context →
  publieke URL / presigned URL / 403 met instructie.
- ES-proxy = PEP voor zoeken (/search): snippets worden afgeschermd als
  de context ontbreekt; hits worden nooit gedropt.
- Context uit bewijs, nooit uit claims:
    * signed cookie (consent-scopes, terms_version, granted-scopes)
    * 'edge': alleen requests via /edge/* krijgen de studiezaal-context
      (simuleert dat de edge het client-IP zet — de browser kan dat
      niet faken)
    * /login simuleert OIDC-login bij de eigen IdP van een organisatie
    * /grant simuleert de beheer-uitgifte van een verleende toegang
- S3: /file accepteert alleen geldige presigned URL's.
- Viewer (/doc/*): bewust dom — rendert wat de PEP teruggeeft.
- ALTCHA-achtig proof-of-work op het consent-endpoint.

Alleen Python stdlib. Draait op http://localhost:8000
"""
import base64, hashlib, hmac, json, secrets, time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs, quote

SECRET = b"demo-server-geheim"        # prod: uit secret manager
COOKIE_NAME = "edepot_context"
COOKIE_TTL = 24 * 3600                # cookie ~24u
PRESIGN_TTL = 300                     # delivery-URL ~5 min
POW_DIFFICULTY = 3                    # ALTCHA: aantal leading-zero hex-tekens

# ---------------------------------------------------------------
# "ES-index": documentrecords zoals de indexer (PDP) ze afleidt.
# consent_scope wordt in de demo uit 'dossier' bepaald; in de echte
# index is het een afgeleid veld. access_org = archiefvormer, nodig
# voor org-scoped grants. Restricted metadata-velden staan er
# simpelweg NIET in — dat is structurele afdwinging.
# ---------------------------------------------------------------
DOCS = {
    # --- cat 0: publiek ---
    "kaart-1880":   {"title": "Kadastrale kaart Utrecht 1880", "cat": 0,
                     "org": "gemeente-utrecht",
                     "full_text": "kadaster kaart utrecht 1880 grondslag",
                     "body": b"FAKE-SCAN: kadastrale kaart 1880..."},

    # --- cat 1: persoonlijke kopie, consent per dossier ---
    "tekening-001": {"title": "Bouwtekening Stationsgebied (blad 1)", "cat": 1,
                     "dossier": "dossier-bouw-1", "org": "gemeente-houten",
                     "full_text": "bouwtekening stationsgebied houten",
                     "body": b"FAKE-PDF: bouwtekening Stationsgebied blad 1..."},
    "tekening-002": {"title": "Bouwtekening Stationsgebied (blad 2)", "cat": 1,
                     "dossier": "dossier-bouw-1", "org": "gemeente-houten",
                     "full_text": "bouwtekening stationsgebied houten",
                     "body": b"FAKE-PDF: bouwtekening Stationsgebied blad 2..."},
    # zelfde dossier, maar cat 2: consent voor het dossier dekt dit NIET;
    # een grant op het dossier (cat-3-route) of de studiezaal wel.
    "vergunning-001": {"title": "Bouwvergunning met persoonsgegevens", "cat": 2,
                     "dossier": "dossier-bouw-1", "org": "gemeente-houten",
                     "full_text": "bouwvergunning persoonsgegevens naam",
                     "body": b"GEHEIM: vergunningaanvraag met BSN..."},
    "tekening-010": {"title": "Bouwtekening De Uithof (ander dossier)", "cat": 1,
                     "dossier": "dossier-bouw-2", "org": "gemeente-nieuwegein",
                     "full_text": "bouwtekening uithof",
                     "body": b"FAKE-PDF: bouwtekening De Uithof..."},
    "losse-tekening": {"title": "Losse bouwtekening (geen dossier)", "cat": 1,
                     "org": "gemeente-houten",
                     "full_text": "losse tekening",
                     "body": b"FAKE-PDF: losse tekening..."},

    # --- cat 2: studiezaal ---
    "krant-1943":   {"title": "Utrechts Nieuwsblad, 1943", "cat": 2,
                     "org": "gemeente-utrecht",
                     "full_text": "krant utrecht 1943 oorlog",
                     "body": b"FAKE-SCAN: krant 1943..."},

    # --- cat 3: alleen via verleende toegang ---
    "aanzeg-007":   {"title": "Aanzegging openbaarheidsbeperkt", "cat": 3,
                     "dossier": "dossier-openbaar-1", "org": "gemeente-houten",
                     "full_text": "aanzegging besloten",
                     "body": b"GEHEIM: aanzegging openbaarheidsbeperkt..."},

    # beleidsrecord in dezelfde index: de voorwaarden zijn data,
    # geen code. Versiebump → alle bestaande consent-cookies vervallen.
    "terms:default": {
        "version": "2026-11",
        "text": ("Ik verklaar dat ik het materiaal dat ik via deze "
                 "voorziening download alleen voor persoonlijk gebruik zal "
                 "gebruiken en niet zal delen met anderen."),
    },
}

# Organisaties die via hun eigen IdP inloggen (OIDC-simulatie).
ORGS = {
    "org:gemeente-houten": "Medewerker gemeente Houten",
    "org:gemeente-nieuwegein": "Medewerker gemeente Nieuwegein",
    "org:brandweer": "Medewerker Veiligheidsregio (brandweer)",
}

def terms_record():
    return DOCS["terms:default"]

def is_document(rec) -> bool:
    return isinstance(rec, dict) and "cat" in rec

def needed_scope(doc, doc_id: str) -> str:
    """consent_scope: 'dossier:<id>' of 'doc:<id>' als er geen dossier is."""
    return f"dossier:{doc['dossier']}" if doc.get("dossier") else f"doc:{doc_id}"

def grant_scopes_for(doc, doc_id: str):
    """Scopes waarvoor een grant dit document dekt — de grant ís de
    autorisatie voor de scope, ongeacht de basiscategorie."""
    s = {f"doc:{doc_id}", f"org:{doc['org']}", "org:*"}
    if doc.get("dossier"):
        s.add(f"dossier:{doc['dossier']}")
    return s

# ---------- ALTCHA-achtig proof-of-work ----------

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

def make_cookie(consented, granted, terms_version, identity=None) -> str:
    payload = b64e(json.dumps({
        "consented": sorted(consented),
        "granted": sorted(granted),
        "terms_version": terms_version,
        "identity": identity,
        "pow": True,
        "iat": int(time.time()),
        "exp": int(time.time()) + COOKIE_TTL,
    }).encode())
    return f"{payload}.{sign(payload.encode())}"

def read_cookie(value: str | None):
    if not value or "." not in value:
        return None
    payload, sig = value.rsplit(".", 1)
    if not hmac.compare_digest(sig, sign(payload.encode())):
        return None
    try:
        data = json.loads(b64d(payload))
        if data.get("exp", 0) <= time.time():
            return None
        return {"consented": set(data.get("consented", [])),
                "granted": set(data.get("granted", [])),
                "terms_version": data.get("terms_version"),
                "identity": data.get("identity")}
    except Exception:
        return None

def presign(doc_id: str) -> str:
    """simuleert een S3 presigned URL"""
    exp = int(time.time()) + PRESIGN_TTL
    sig = sign(f"{doc_id}:{exp}".encode())
    return f"/file/{doc_id}?exp={exp}&sig={sig}"

def scope_omschrijving(scope: str) -> str:
    kind, _, ref = scope.partition(":")
    if kind == "dossier":
        n = sum(1 for d in DOCS.values()
                if is_document(d) and d["cat"] == 1 and d.get("dossier") == ref)
        return f"alle cat-1-documenten in dossier '{ref}' ({n} documenten)"
    titel = DOCS.get(ref, {}).get("title", ref)
    return f"het document '{titel}'"

POW_JS = """
async function solvePow(challenge, difficulty) {
  const enc = new TextEncoder();
  const zeros = '0'.repeat(difficulty);
  for (let n = 0; n < 20000000; n++) {
    const buf = await crypto.subtle.digest('SHA-256', enc.encode(challenge + n));
    const hex = [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2,'0')).join('');
    if (hex.startsWith(zeros)) return n;
  }
  throw new Error('pow-timeout');
}
function powWidget(boxId, btnId, nonceId) {
  return function(n) {
    document.getElementById(nonceId).value = n;
    const box = document.getElementById(boxId);
    box.querySelector('.icon').textContent = '\\u2713';
    box.querySelector('.status').textContent = 'Geverifieerd';
    box.style.borderColor = 'green';
    box.querySelector('.status').style.color = 'green';
    if (btnId) document.getElementById(btnId).disabled = false;
  };
}
"""

POW_BOX = ('<div id="{box}" style="border:1px solid #ccc;border-radius:6px;'
           'padding:8px 12px;display:inline-block;margin:8px 0">'
           '<span class="icon">&#8230;</span> '
           '<span class="status">Even een moment&#8230;</span></div>')

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

    def _route(self):
        """Parseert pad; /edge/* simuleert de edge van de studiezaal:
        alleen díe route kan studiezaal-context 'stempelen'."""
        u = urlparse(self.path)
        path = u.path
        self.via_edge = path == "/edge" or path.startswith("/edge/")
        if self.via_edge:
            path = path[len("/edge"):] or "/"
        return u, path

    def _context(self):
        """Context uit bewijs: edge-stempel (IP) + signed cookie."""
        ck = read_cookie(self._get_cookie(COOKIE_NAME))
        return {
            "studyroom": self.via_edge,
            "consented": ck["consented"] if ck else set(),
            "granted": ck["granted"] if ck else set(),
            "terms_version": ck["terms_version"] if ck else None,
            "identity": ck["identity"] if ck else None,
        }

    # --- beslissingslogica, gedeeld door resolver en ES-proxy ---
    def _decision(self, doc_id, doc, ctx):
        """Geeft ('ok', None) of ('deny', instructie) terug."""
        grants = ctx["granted"]
        # Een grant is scope-specifiek en dekt ook cat-1/2-documenten in
        # zijn scope — de toegang loopt dan 'via categorie 3'.
        if grants & grant_scopes_for(doc, doc_id):
            return "ok", None
        cat = doc["cat"]
        if cat == 0:
            return "ok", None
        if cat == 1:
            scope = needed_scope(doc, doc_id)
            if (ctx["terms_version"] == terms_record()["version"]
                    and scope in ctx["consented"]):
                return "ok", None
            return "deny", {
                "error": "consent_required", "action": "consent",
                "scope": scope,
                "scope_text": ("Deze instemming geldt voor: "
                               + scope_omschrijving(scope) + "."),
                "terms": terms_record()["text"],
                "terms_version": terms_record()["version"],
                "pow_challenge": pow_challenge(),
                "pow_difficulty": POW_DIFFICULTY,
                "consent_url": ("/consent?return=" + quote(f"/doc/{doc_id}", safe="")
                                + "&scope=" + quote(scope, safe="")),
            }
        if cat == 2:
            if ctx["studyroom"]:
                return "ok", None
            return "deny", {
                "error": "studyroom_required", "action": "studyroom",
                "message": ("Dit document is alleen te raadplegen op een "
                            "terminal in de RAZU-studiezaal."),
            }
        # cat 3
        return "deny", {
            "error": "login_required", "action": "login",
            "message": ("Dit document is alleen toegankelijk voor "
                        "gebruikers met een verleende toegang."),
            "login_url": "/login?return=" + quote(f"/doc/{doc_id}", safe=""),
        }

    def _can_access(self, doc_id, doc, ctx):
        return self._decision(doc_id, doc, ctx)[0] == "ok"

    # ---------------------------------------------------------------
    def do_GET(self):
        u, path = self._route()
        edge = "/edge" if self.via_edge else ""

        if path == "/":
            return self._home()

        if path.startswith("/doc/"):
            doc_id = path.rsplit("/", 1)[1]
            return self._doc_page(doc_id, edge)

        if path.startswith("/resolve/"):
            return self._resolve(path.rsplit("/", 1)[1])

        if path == "/search":
            return self._search(parse_qs(u.query).get("q", [""])[0])

        if path == "/consent":
            qs = parse_qs(u.query)
            return self._consent_page(
                qs.get("return", ["/"])[0], qs.get("scope", [""])[0], edge)

        if path == "/login":
            ret = parse_qs(u.query).get("return", ["/"])[0]
            return self._login_page(ret, edge)

        if path == "/grant":
            ret = parse_qs(u.query).get("return", ["/"])[0]
            return self._grant_page(ret, edge)

        if path == "/logout":
            self.send_response(303)
            self.send_header("Location", edge + "/" if edge else "/")
            self.send_header("Set-Cookie",
                f"{COOKIE_NAME}=; Path=/; HttpOnly; Max-Age=0")
            self.end_headers()
            return

        if path.startswith("/file/"):
            return self._file(u)

        self._send(404, b"niet gevonden")

    def do_POST(self):
        u, path = self._route()
        edge = "/edge" if self.via_edge else ""
        qs = parse_qs(u.query)
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            for k, v in parse_qs(self.rfile.read(length).decode()).items():
                qs.setdefault(k, v)

        if path == "/consent":
            if not pow_verify(qs.get("challenge", [""])[0],
                              qs.get("nonce", [""])[0]):
                return self._send(403,
                    "<h2>Proof-of-work mislukt</h2>"
                    "<p>De verificatie is niet geslaagd — probeer het "
                    "opnieuw.</p>")
            ck = read_cookie(self._get_cookie(COOKIE_NAME)) or {}
            consented = set(ck.get("consented") or set())
            granted = set(ck.get("granted") or set())
            scope = qs.get("scope", [""])[0]
            if scope:
                consented.add(scope)
            tv = qs.get("tv", [terms_record()["version"]])[0]
            return self._set_cookie_redirect(
                make_cookie(consented, granted, tv, ck.get("identity")),
                qs.get("return", ["/"])[0])

        if path == "/login":
            # OIDC-simulatie: de eigen IdP levert een claim; die wordt
            # als signed cookie gezet — de browser kan niets claimen.
            claim = qs.get("org", [""])[0]
            if claim not in ORGS:
                return self._send(400, "onbekende organisatie")
            ck = read_cookie(self._get_cookie(COOKIE_NAME)) or {}
            granted = {claim}
            return self._set_cookie_redirect(
                make_cookie(set(ck.get("consented") or set()), granted,
                            terms_record()["version"], ORGS[claim]),
                qs.get("return", ["/"])[0])

        if path == "/grant":
            # Beheer-simulatie: de archivaris verleent toegang aan een
            # scope (doc:/dossier:). De grant komt in de signed cookie.
            scope = qs.get("scope", [""])[0]
            ck = read_cookie(self._get_cookie(COOKIE_NAME)) or {}
            granted = set(ck.get("granted") or set())
            if scope:
                granted.add(scope)
            return self._set_cookie_redirect(
                make_cookie(set(ck.get("consented") or set()), granted,
                            terms_record()["version"], "via beheer"),
                qs.get("return", ["/"])[0])

        self._send(404, b"niet gevonden")

    def _set_cookie_redirect(self, cookie, ret):
        self.send_response(303)
        self.send_header("Location", ret)
        self.send_header("Set-Cookie",
            f"{COOKIE_NAME}={cookie}; Path=/; HttpOnly; SameSite=Lax; "
            f"Max-Age={COOKIE_TTL}")
        self.end_headers()

    # ---------- pagina's (viewer: bewust dom) ----------

    def _home(self):
        ctx = self._context()
        edge = "/edge" if self.via_edge else ""
        rows = "".join(
            f'<li><a href="{edge}/doc/{d}">{v["title"]}</a> '
            f'<small>[cat {v["cat"]}'
            f'{", dossier " + v["dossier"] if v.get("dossier") else ""}'
            f', org {v["org"]}]</small></li>'
            for d, v in DOCS.items() if is_document(v))
        ctx_html = (
            f"<b>Huidige context:</b> "
            f"studiezaal: {'ja' if ctx['studyroom'] else 'nee'} · "
            f"ingelogd als: {ctx['identity'] or '-'} · "
            f"consented: {sorted(ctx['consented']) or '-'} · "
            f"granted: {sorted(ctx['granted']) or '-'}")
        return self._send(200, f"""<!doctype html><title>E-depot demo</title>
<h1>E-depot demo {'<small>(studiezaal-weergave)</small>' if self.via_edge else ''}</h1>
<p>{ctx_html}</p>
<ul>{rows}</ul>
<p><a href="/search">Zoeken</a> ·
<a href="{edge}/login?return={edge}/">Inloggen (organisatie)</a> ·
<a href="{edge}/grant?return={edge}/">Toegang verlenen (beheer)</a> ·
<a href="{edge}/logout">Uitloggen/cookie wissen</a></p>
<p><a href="/"><b>Normale weergave</b></a> ·
<a href="/edge/"><b>Studiezaal-weergave</b></a>
<small> — /edge simuleert dat de edge het studiezaal-IP stempelt;
de browser kan dit niet faken.</small></p>""")

    def _doc_page(self, doc_id, edge):
        html = f"""<!doctype html><title>{doc_id}</title>
<h1>{doc_id}</h1><div id="app">laden&#8230;</div>
<p><a href="{edge or ''}/">&#8592; overzicht</a></p>
<script>
{POW_JS}
const EDGE = {json.dumps(edge)};
fetch(EDGE + '/resolve/{doc_id}').then(async r => {{
  const j = await r.json().catch(() => ({{}}));
  const app = document.getElementById('app');
  if (r.ok && j.url) {{
    app.innerHTML =
      '<p>Toegang verleend.</p><a href="'+EDGE+j.url+'">Open document</a>';
  }} else if (j.action === 'consent') {{
    app.innerHTML =
      '<h2>Voorwaarden</h2><div id="terms"></div><p>' + j.scope_text + '</p>' +
      '{POW_BOX.format(box="powbox")}' +
      '<form method="post" action="'+EDGE+j.consent_url+'&tv='+j.terms_version+'">' +
      '<input type="hidden" name="challenge" value="'+j.pow_challenge+'">' +
      '<input type="hidden" name="nonce" id="nonce">' +
      '<button id="cbtn" disabled>Ik stem in</button></form>';
    document.getElementById('terms').textContent = j.terms;
    solvePow(j.pow_challenge, j.pow_difficulty)
      .then(powWidget('powbox', 'cbtn', 'nonce'))
      .catch(() => {{
        const s = document.querySelector('#powbox .status');
        document.querySelector('#powbox .icon').textContent = '\\u2717';
        s.textContent = 'Proof-of-work mislukt'; s.style.color = 'red';
      }});
  }} else if (j.action === 'studyroom') {{
    app.innerHTML = '<p>' + j.message + '</p>' +
      (EDGE ? '' : '<p><a href="/edge/doc/{doc_id}">Open via de studiezaal-weergave</a></p>');
  }} else if (j.action === 'login') {{
    app.innerHTML = '<p>' + j.message + '</p>' +
      '<p><a href="'+EDGE+j.login_url+'">Inloggen / toegang aanvragen</a></p>';
  }} else {{
    app.textContent = 'Geen toegang (' + (j.error || '?') + ')';
  }}
}});
</script>"""
        return self._send(200, html)

    def _consent_page(self, ret, scope, edge):
        challenge = pow_challenge()
        return self._send(200, f"""<!doctype html><title>Toestemming</title>
<h2>Voorwaarden</h2>
<p>{terms_record()["text"]}</p>
<p><i>Versie {terms_record()["version"]}</i> — deze instemming geldt voor:
<b>{scope_omschrijving(scope)}</b>.</p>
{POW_BOX.format(box="powbox")}
<form method="post" action="{edge}/consent?return={quote(ret, safe='')}&scope={quote(scope, safe='')}">
<input type="hidden" name="tv" value="{terms_record()["version"]}">
<input type="hidden" name="challenge" value="{challenge}">
<input type="hidden" name="nonce" id="nonce">
<button id="cbtn" disabled>Ik stem in</button></form>
<script>{POW_JS}
solvePow('{challenge}', {POW_DIFFICULTY})
  .then(powWidget('powbox', 'cbtn', 'nonce'))
  .catch(() => {{
    const s = document.querySelector('#powbox .status');
    document.querySelector('#powbox .icon').textContent = '\\u2717';
    s.textContent = 'Proof-of-work mislukt'; s.style.color = 'red';
  }});
</script>""")

    def _login_page(self, ret, edge):
        opts = "".join(
            f'<form method="post" action="{edge}/login?'
            f'return={quote(ret, safe="")}&org={quote(org, safe="")}">'
            f'<button>{name}</button></form><br>'
            for org, name in ORGS.items())
        return self._send(200, f"""<!doctype html><title>Inloggen</title>
<h2>Inloggen via de eigen IdP (OIDC-simulatie)</h2>
<p>Kies een identiteit — in productie komt de claim van de
identiteitsprovider van de organisatie.</p>
{opts}""")

    def _grant_page(self, ret, edge):
        scopes = []
        for d, v in DOCS.items():
            if not is_document(v):
                continue
            scopes.append((f"doc:{d}", f"document: {v['title']}"))
            if v.get("dossier"):
                scopes.append((f"dossier:{v['dossier']}",
                               f"dossier: {v['dossier']}"))
        scopes = sorted(set(scopes))
        opts = "".join(
            f'<form method="post" action="{edge}/grant?'
            f'return={quote(ret, safe="")}&scope={quote(s, safe="")}">'
            f'<button>Verleen: {label}</button></form>'
            for s, label in scopes)
        return self._send(200, f"""<!doctype html><title>Toegang verlenen</title>
<h2>Verleende toegang uitgeven (beheer-simulatie)</h2>
<p>De grant is scope-specifiek en dekt alle documenten in die scope —
ook documenten met basiscategorie 1 of 2.</p>
{opts}""")

    # ---------- PEP resolver ----------
    def _resolve(self, doc_id):
        doc = DOCS.get(doc_id)
        if not is_document(doc):
            return self._json(404, {"error": "unknown_document"})
        verdict, instr = self._decision(doc_id, doc, self._context())
        if verdict == "ok":
            kind = "public" if doc["cat"] == 0 else "presigned"
            return self._json(200, {"url": presign(doc_id), "via": kind})
        return self._json(403, instr)

    # ---------- ES-proxy: zoeken/snippets ----------
    def _search(self, q):
        ctx = self._context()
        edge = "/edge" if self.via_edge else ""
        hits = []
        if q:
            for d, v in DOCS.items():
                if is_document(v) and q.lower() in v["full_text"].lower():
                    ok = self._can_access(d, v, ctx)
                    snippet = (v["full_text"][:80] if ok
                               else "[fragment afgeschermd — cat "
                                    f"{v['cat']}]")
                    hits.append((d, v, ok, snippet))
        hit_rows = "".join(
            f'<li><a href="{edge}/doc/{d}">{v["title"]}</a> '
            f'<small>[cat {v["cat"]}]</small> — <i>{snip}</i></li>'
            for d, v, ok, snip in hits)
        return self._send(200, f"""<!doctype html><title>Zoeken</title>
<h1>Zoeken (ES-proxy)</h1>
<form><input name="q" value="{q}"><button>Zoek</button></form>
<p><small>Snippets van documenten waar de context voor ontbreekt worden
afgeschermd; de hit zelf wordt nooit gedropt.</small></p>
<ul>{hit_rows}</ul>
<p><a href="{edge or ''}/">&#8592; overzicht</a></p>""")

    # ---------- S3-simulatie ----------
    def _file(self, u):
        parts = u.path.strip("/").split("/")
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
    print("Demo op http://localhost:8000 (studiezaal: /edge/)")
    HTTPServer(("0.0.0.0", 8000), H).serve_forever()
