# Category 1 flows

Rendered wireframes: [Cat 1 flows](https://regionaal-archief-zuid-utrecht.github.io/vestibulum/example_flows_cat1.html).

## Flow A — direct consent (baseline)

1. Anonymous user opens a dossier page that contains cat 1 files. The page is displayed as usual, including previews that are already allowed, and shows a message such as: "Sommige bestanden zijn mogelijk auteursrechtelijk beperkt. U kunt voor persoonlijk gebruik een werkkopie aanvragen [Vraag aan]."
2. On "Vraag aan", the application performs a normal resolver call for the dossier/document context:

   ```
   GET resolver.razu.nl/resolve?uri=<document-uri>
   Cookie: context=<signed context token>
   ```

   The attribute record identifies the document as cat 1 and returns its dossier and `terms_ref`. The resolver answers `Deny/consent_required` with the category, dossier URI and applicable terms text or canonical versioned `terms_ref`.
3. The application shows the consent form using the terms supplied by the resolver response. It contains:
   - the applicable terms;
   - a clear statement that access to the documents is temporary (order of a few hours) and dossier-scoped, and that no consent record is registered;
   - "Ik ga akkoord" and "Annuleren" actions;
   - the ALTCHA widget;
   - a hidden honeypot field;
   - a CSRF token.

   "Annuleren" closes the form and returns to the normal dossier view.
4. On "I agree", the browser posts directly to the session component:

   ```
   POST sessie.razu.nl/consent
   Cookie: context=<signed context token>

   { "dossier": "...",
     "terms_ref": "...",
     "accept": true,
     "altcha": "...",
     "csrf": "<form csrf token>",
     "website": "" }
   ```

   `website` is the honeypot field and must remain empty. No `terms_version` or terms text is posted.
5. The session component verifies:
   - signature, `exp`, `iss` and `aud` of the context token;
   - `accept === true`;
   - `terms_ref` is in scope for the dossier and still identifies the current version;
   - the ALTCHA solution;
   - honeypot and CSRF token;
   - IP/session rate limits.

   If anything fails, no consent is issued; if `terms_ref` is stale or inconsistent, the application must show a fresh `consent_required` response with the current terms.
6. If valid, the session component stamps the current `terms_version` itself, signs a context token `{consented, dossier, terms_version, exp}`, places it in the `HttpOnly` context cookie and returns `303 See Other` to the dossier downloads page. No consent, account or user record is persisted server-side.
7. The downloads page:
   - repeats the agreed terms;
   - states that access to the documents is temporary and shows the token expiry;
   - lists all cat 1 files of the dossier as downloads;
   - does not pre-render presigned URLs.
8. Every download click performs a fresh resolver call with the context cookie:

   ```
   GET resolver.razu.nl/resolve?uri=<document-uri>
   Cookie: context=<context token with consented claim>
   ```

   The resolver verifies the token and dossier scope itself. On Permit it returns a short-lived presigned S3 URL (`Content-Disposition: attachment`). If the token expired or consent is absent, it returns `consent_required` and the application shows the consent form again.

## Flow B — e-mail verification route

Use this variant when mailbox verification is wanted as an extra barrier (for example conditionally, on suspected automation). It keeps the architecture token-only: e-mail proves mailbox possession, not an account, and the submitted address is not turned into a registration. The user agrees to the terms before the verification link is sent.

1. Same dossier page and `consent_required` response as Flow A. The form can offer "Verify by e-mail", or the application can require this variant conditionally.
2. The application shows a combined consent and e-mail form containing:
   - the applicable terms;
   - a clear statement that access to the documents is temporary and dossier-scoped, and that no consent record is registered;
   - an e-mail address field;
   - a statement that the address is used only to send the verification message and is not retained as a consent or user record;
   - "Annuleren" and "Ik ga akkoord" actions;
   - the ALTCHA widget, a hidden honeypot field and a CSRF token.

   "Annuleren" closes the form and returns to the normal dossier view. On "Ik ga akkoord", the browser posts the consent and e-mail address directly to the session component:

   ```
   POST sessie.razu.nl/consent/email/request
   Cookie: context=<signed context token>

   { "dossier": "...",
     "terms_ref": "...",
     "email": "...",
     "accept": true,
     "altcha": "...",
     "csrf": "<form csrf token>",
     "website": "" }
   ```
3. The session component validates the existing context token, ALTCHA, honeypot, CSRF, IP/session rate limits, explicit `accept`, and that `terms_ref` is in scope for the dossier and still current. It does not persist the address.
4. If valid, the session component creates a short-lived signed `email_challenge` token (for example 10–15 minutes) containing only:
   - `purpose: "cat1-email-consent-confirm"`
   - `dossier`
   - `terms_ref`
   - `context_token_hash` (binds the challenge to the browser session that requested it)
   - `exp`

   It sends a fixed-template e-mail containing a landing-page URL with the challenge in the fragment:

   ```
   https://viewer.razu.nl/e-mail-verification#challenge=<email_challenge>
   ```

   The fragment is not sent to the web server and therefore does not end up in request logs, referer headers or trivial mail-scanner prefetches. The e-mail never contains a context token, a document URL that bypasses the resolver, or a presigned URL.
5. The user opens the landing page. The page reads the fragment client-side, shows the dossier and already-accepted terms for context, and requires an explicit "Verify e-mail address" action. A mail scanner or URL prefetch therefore cannot accidentally activate the consent.
6. On "Verify e-mail address", the browser posts the fragment value to the session component:

   ```
   POST sessie.razu.nl/consent/email/confirm
   Cookie: context=<same signed context token>

   { "challenge": "<email_challenge>",
     "csrf": "<form csrf token>",
     "website": "" }
   ```

   The session component verifies:
   - challenge signature, purpose and expiry;
   - `context_token_hash` against the current context cookie;
   - `dossier` and `terms_ref` consistency;
   - `terms_ref` is still the current version;
   - honeypot, CSRF and rate limits.

   If anything fails, the user is returned to the consent flow. If the terms changed between request and confirmation, the stale `terms_ref` is rejected and the current terms must be shown again.
7. If valid, the session component stamps the current `terms_version` itself, signs the normal context token `{consented, dossier, terms_version, exp}` into the context cookie and returns `303 See Other` to the dossier downloads page.
8. The downloads page and per-click resolver behaviour are exactly the same as Flow A.

### Design consequences and limits

- **No extra register needed.** The challenge is self-contained and signed; the session service does not need an e-mail, consent, session or used-code database.
- **Same-browser binding is recommended.** `context_token_hash` makes the e-mail link useless in another browser or on another device. That limits forwarding and link leakage, at the UX cost that the user must open the mail link in the browser where the request started. If cross-device opening is required, this binding can be omitted, but the link then becomes a bearer capability until it expires.
- **Do not e-mail access.** E-mail carries only the challenge link. Never put the final context token or a presigned S3 URL in the message.
- **Do not retain the address.** Prefer no raw e-mail address in application logs; use only operational mail-provider logs with an agreed retention. Per-recipient throttling would require an ephemeral hash counter and should likewise be an explicit decision, because the normal rate limits are per IP/session.
