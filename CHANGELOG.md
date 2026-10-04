## Unreleased — the risk page showed a daily-loss cap of 0 for an account whose cap was 2000, and could not save at all

> Found by pressing Save and reading what the form sent, rather than what it displayed. The kill
> switch on the same page is correct, which is the useful part of this: the control that matters
> most held up.

### Fixed

Three defects on one form, compounding.

1. **The response envelope was never unwrapped** (`apps/web/app/risk/page.tsx`).
   `GET /risk/settings` answers `{ settings: [ {...} ] }` — a list under a key — and the page read
   `s.max_daily_loss` off that envelope, which is always `undefined`. None of the three population
   guards fired, `limits` kept its zero defaults, and the page displayed **a daily-loss cap of 0**
   for an account whose stored cap was **2000**.

   Third instance of this exact class, after `/engine/orders` returning `{ orders: [...] }` and
   `/forward-test` returning `{ items: [...] }`. Two of those are now covered by tests; this is the
   third.

2. **The drawdown field was sent under a name the API does not have.** The page posted
   `max_drawdown`; the request model declares `max_drawdown_pct`. Pydantic ignores unknown fields,
   so this did not error — it fell through to the model's own default of `0.0`, and
   `risk/rules.py:463` treats `<= 0` as unlimited. **Every save silently reset the drawdown limit to
   "no limit"**, with no error and no visible change.

3. **The backend's reason was thrown away.** A rejected save answered
   *"Daily loss cap cannot be disabled. Minimum is your tier default of ₹100000."* and the page
   replaced it with "Failed to update limits". Since the form could not be saved at all — it always
   posted the zero it had been showing — the user got a dead form and no indication why.

Together: the form **displayed the wrong value for a safety limit**, **could not be saved**, and
would have **silently removed the drawdown cap** if a save had ever succeeded.

Verified live before and after:

    before: inputs ["0","0","10"]      body {"max_daily_loss":0,"max_drawdown":0}
    after:  inputs ["2000","0","10"]    body {"max_daily_loss":2000,"max_drawdown_pct":0}

### The backend is why this was a display bug and not data loss

`risk_service.update_settings` rejects a zero daily-loss cap outright, so pressing Save never
overwrote the stored 2000. Worth stating plainly, because the frontend was one keystroke away from
erasing a risk limit and the only thing standing in the way was a server-side check.

### Verified, not broken

4. **The kill switch is correct.** `POST /risk/kill-switch/enable` issued, the state persisted —
   `GET /risk/kill-switch` returned `{"kill_switch_enabled": true}` — and disabling returned 200.
   It is admin-gated and the page hides it for non-admins, which is also correct. Restored to
   disabled afterwards; a scenario arms nothing.

### Added

5. **An eighth interaction scenario** asserting the limit shown equals the limit stored. It reads
   only, and deliberately does not touch the kill switch — that control is global, and a scenario
   that armed it and failed midway would halt trading for everyone. Mutation-validated: reverting
   the unwrap makes it report *"form shows 0, stored value is 2000"*.

### Reference

- **Press the button and read what it sends.** The display was wrong and the write was broken; the
  page looked plausible throughout.
- **A silently-ignored field name is worse than a rejected one.** `max_drawdown` did not error — it
  reset a safety limit to unlimited.
- **Keep the server's reason.** It was the most informative string in the whole exchange.
- **The envelope bug has now appeared three times.** Worth a lint rule or a shared unwrap helper
  before a fourth does.
- 8/8 interaction scenarios, crawl 51/51, session 7/7, tsc 0, lint 0, 53 lib tests.

## Unreleased — 21 of 27 brokers could not be connected through the UI, including all four OAuth brokers

> Found by filling in the broker connect form and pressing Connect. The button did nothing, and it
> did nothing *quietly*, which is why an existing green test suite had not caught it.

### Fixed

1. **`handleSave` validated a field most brokers do not have** (`apps/web/app/brokers/page.tsx`).
   The check was

       if (!form.broker || !form.api_key.trim() || !form.secret_key.trim()) { ...reject... }

   but the field renderer binds the identifier to `form.client_id` or `form.client_code` depending
   on what the broker's metadata declares:

       value={field.key === 'client_id' ? form.client_id : form.api_key}

   So for every broker that does not declare `api_key`, `form.api_key` stayed empty, the check
   tripped, and Connect reported "API key + secret are required" **without ever issuing a request**.
   From the browser that is indistinguishable from a dead button.

   Counted against `apps/api/brokers/registry.py`: **19 of 27 brokers declare no `api_key`**, and
   `fivepaisa` and `oanda` declare no `secret_key`. So **21 of 27 could not be connected at all**,
   and the set included **every OAuth broker — fyers, zerodha, dhan, upstox**. The only brokers
   that worked were angelone, binance, bybit, okx, delta and alpaca.

   The backend was never the obstacle: `routes/v1_brokers.py:96` already reads
   `req.api_key or req.client_id or req.client_code or ""`.

   The check now takes whichever identifier field the broker declares, and requires a secret only
   when the broker declares one. Verified live: `POST /brokers/credentials` is issued for dhan,
   zerodha and fyers, where before none of them sent anything.

2. **The dialog made a promise that was not true.** It read *"We encrypt and store only the access
   token — never your password or PIN"*, while the fields actually collect a **client secret** for
   Dhan, Fyers and Zerodha. Now: the credentials are encrypted before storage, and the trading PIN
   or password is never asked for or stored. The original wording would have been read as "this is
   only a read-only token" by someone deciding whether to paste a secret.

3. **Added a seventh interaction scenario** (`apps/web/scripts/browser/interact.js`) that connects a
   `client_id` broker and asserts the POST is issued with the identifier under a key the backend
   understands. Mutation-validated: restoring the single-field gate makes it fail with *"no POST
   issued — the form rejected the value"*.

   Writing it surfaced two ways the test itself could lie, both recorded in the scenario. Clicking
   in the same tick as filling a controlled input reads pre-render state and does nothing — the
   exact failure under test, so the two must not be confused. And matching the inputs by
   placeholder text reported a Fyers failure that was the probe's: the labels are per-broker
   ("Client ID", "API Key", "App ID"), so the selector now falls back to position.

### Recorded, not fixed

4. **`groww`, `kotakneo` and `mt5` render no credential inputs at all.** The field renderer returns
   `null` for any key outside `{client_code, client_id, api_key, secret_key}`, and those three
   declare `phone`/`otp`, `consumer_key`/`mobile_number`/`ucc`/`totp`/`mpin` and
   `mt5_broker`/`mt5_server`/`login`/`password` respectively. Their dialogs open empty.

   Not fixed here because the fix is a data-model decision rather than a correction: those values
   have to go somewhere, and the form state and the save payload are both fixed-shape. Worth saying
   plainly that this is a real gap and not an oversight in the measurement — they are broken today,
   for a different reason than the 21 above.

5. **`additional_params_fields` binds every field to `form.totp_secret`.** A broker declaring two
   additional params would have both inputs writing the same state. No broker currently does, so
   nothing is broken today; the loop is one line away from being wrong.

### Reference

- **A quiet failure looks like a dead button.** No request, no error in the console, one validation
  message. Only clicking it found this.
- **Validate against what the form can produce.** The backend already accepted three identifier
  keys; the frontend demanded a fourth.
- **Two files disagreeing about a field name is a bug in whichever one is stricter.**
- **A test can lie about which side is broken.** The Fyers failure was the probe's placeholder
  matching, and the "nothing happened" was the same-tick click. Both had to be ruled out before the
  finding could be trusted.
- 7/7 interaction scenarios, mutation-validated. tsc 0, lint 0, 53 lib tests.

## Unreleased — a local deploy rehearsal, which found that deploy.sh runs no migrations and that a local production build talks to production

> Asked to rehearse the deploy locally before touching the VPS. The rehearsal passed, and the two
> things it turned up are both things that would have been discovered the expensive way.

### The rehearsal

    pg_dump backup            -> 16.7 MB, 66 tables + 66 data blocks
    DROP SCHEMA + replay      -> 35 migrations, 44 tables, schema correct
    next build                -> compiled, 59/59 static pages
    next start + harnesses    -> session 7/7, crawl 51/51, write flows 6/6,
                                 contract audit 0 verb / 0 field mismatches

Every check that passes against `next dev` also passes against the real production build. That is
worth stating plainly, because the timezone and hydration bugs found earlier in this work were of
exactly the kind dev mode hides.

### Findings

1. **`infra/production/deploy.sh` applies no migrations.** There is no `psql`, no `alembic`, no
   schema step, and the API image's `CMD` is a bare `uvicorn main:app`. So deploying does not
   migrate: the schema has to be applied out of band, by hand, separately from the deploy.

   This is not a style complaint — it is the whole ordering hazard. `03000` drops a unique index
   that the *deployed* code may still be using for `on_conflict`, and `06000` changes a column type
   and drops a foreign key. Both are safe only at a specific moment relative to the code, and
   nothing in the deploy script either enforces or records that moment.

2. **A local production build silently targets the production API.** `apps/web/.env.production` is
   tracked in git and sets `NEXT_PUBLIC_API_URL=https://api.ai.trademetrix.tech/api/v1`. Next.js
   gives `.env.production` precedence over `.env` when building for production, and inlines
   `NEXT_PUBLIC_*` at build time. So `npm run build` on a laptop produces a correct-for-production
   artifact, with no warning.

   Hit while rehearsing: sign-in failed with `Failed to fetch`, which looks exactly like a code bug.
   It was the browser talking to an API that is currently unreachable. Verified the shell
   environment overrides the file, and added `npm run build:local`, which bakes the local API.

   The tracked file is right for production — `deploy.sh` requires an untracked `apps/web/.env`, but
   `.env.production` comes from the repo, so the Docker build bakes the correct URLs. The risk is
   two files declaring the same variable with different values and no build-time check.

3. **The migration replay emitted 7 duplicate-object errors and was still correct.** Every one was
   an `already exists` on an object that something else had already created after the schema was
   dropped. The result is right — 44 tables, `orders.expiry_date` present,
   `squareoff_config.days` an array, `strategy_runs.strategy_id` text — so these are noise, not
   failure. Recorded because a replay that reports failures and produces a correct schema is exactly
   the kind of thing that gets misread in the wrong direction.

4. **The API in `ENV=production` — now done, and one uncertainty resolved.**
   The rehearsal gap is closed. Run with the compose file's own production environment
   (`ENV=production`, `LOG_LEVEL=INFO`, and `CORS_ORIGINS` pointed at the local web origin),
   everything that passed in development still passes:

       session 7/7   crawl 51/51   write flows 6/6   audit 0 verb / 0 field mismatches

   The open question was the cookie. `middleware/csrf.py` sets `secure=True, samesite=none` when
   `env == "production"`, and that pair is invalid over plain HTTP — a `Secure` cookie on `http://`
   is dropped, and when this exact mismatch bit before, the symptom was *every* POST, PUT and
   DELETE answering 403 with `document.cookie` empty, so all writes looked impossible and only
   reads appeared to work.

   Measured rather than assumed: browsers treat `127.0.0.1` as a secure context, so the cookie is
   accepted, and all six write flows pass against it. The production cookie path is therefore
   rehearsable locally with no HTTPS terminator. `COOKIE_DOMAIN` must be left empty for this — the
   compose file sets it to `.trademetrix.tech`, which would stop the cookie being set at all on a
   local host.

   What is still *not* rehearsed: the reverse proxy. `Caddyfile` handles TLS and the
   `ai.` → `api.` subdomain hop in production, and nothing local reproduces that.

### Reference

- **Rehearse the deploy, do not reason about it.** Two of the three findings here were invisible
  until something was actually built and run.
- **`NEXT_PUBLIC_*` is baked at build time.** A local production build is a production artifact.
- **A deploy script that does not migrate is half a deploy.** The schema step has to be explicit,
  and ordered against the code.
- **A build with no errors is not a build wired to the right place.**

## Unreleased — a kill switch you can arm but never disarm, and three fabrications in the tool that was supposed to catch it

> Found by asking a simple question of an unclicked page: what happens here if the button is
> pressed? Then by asking the audit tool a question it had never been asked.

### Fixed

1. **Live trading could be turned on and not turned off through the product**
   (`apps/web/lib/api.ts:507`). `disableLive` declared no HTTP method, so it defaulted to GET, while
   the API offers POST only:

       GET  /api/v1/risk/live/disable  ->  405 Method Not Allowed
       POST /api/v1/risk/live/disable  ->  200 "LIVE trading disabled"

   And no page calls it — `enableLive` has a control in `/trade`, `disableLive` has none anywhere.
   So this was a dead declaration *and* a broken one: enabling worked, disabling did not exist.

   The declaration now sends POST. Verified live, and mutation-validated: removing the method brings
   the finding straight back.

2. **The contract audit could not see an untyped declaration.** `find_declarations` matches
   `request<` and so sees only the 139 typed calls; 58 untyped ones were invisible, which is exactly
   where `disableLive` was. Whether a declaration names a response type and which verb it uses are
   unrelated questions and only the first is optional.

3. **Added a verb cross-check to the audit** (`--spec`). Comparing response *fields* needs a live
   response, so a declaration with the wrong verb never gets a signature and lands in "never
   exercised", where it reads as untested rather than broken. The verb check needs no crawl history
   at all and runs before anything else.

### The tool fabricated twice while being extended, and both attempts were caught by checking

   - A 400-character lookahead for `method:` reported **twelve plain `request('/path')` reads** as
     "client would send POST". Each one was borrowing the *next* declaration's method. A lookahead
     is not a call boundary; the argument list is.
   - Paths were compared as strings. The spec's `/brokers/{broker}/exchange-code` normalises to
     `/brokers/*/exchange-code` while the client writes the literal `/brokers/fyers/exchange-code`,
     so a route that answers `400 No Fyers credentials found` — present, reachable, correct — was
     listed as "not in spec".

   After both fixes: **1 verb mismatch** (the real one) and 5 unknown paths, of which three are the
   known `/admin/pnl`-style tabs and two are dead simulator declarations no page calls.

   One test-harness finding too: the shape tests passed while `check_methods` still used
   `routes.get(path)`, because the helpers were tested directly and the wiring was not. Pinned now.

### Not fixed — your call

4. **There is still no UI to disable live trading.** The declaration was a bug and is fixed, but
   adding a control is new surface, and the feature freeze says bugs only. It is also the more
   serious half of the finding: a user who enables live trading currently has no way to turn it off
   from the product. Say the word and it is a small change.

5. **`/marketdata/simulator/start` and `/stop` are declared but do not exist**, and no page calls
   them. Dead declarations, recorded rather than deleted per the no-deletions rule.

### Reference

- **A control with no counterpart is a design smell and here it was a bug.** `enableLive` had a
  button, `disableLive` did not, and the mismatch hid a 405.
- **Test the wiring, not just the helpers.** Every helper passed while the caller bypassed it.
- **A lookahead is not a scope.** Both fabrications in this file came from reading text past the end
  of the thing being read.
- **Match paths by shape.** A literal in the client and a parameter in the spec are the same route.
- 28 tests for the tool. API **1350 passed / 1 xpassed**; ruff clean; web tsc 0, lint 0, 53 lib
  tests; audit 0 verb mismatches, 0 field mismatches.

## Unreleased — change-password validated nothing: an account could be downgraded below the policy signup enforces

> Found by clicking a write path that had never been clicked. Every earlier fix this session came
> from reading code or diffing schemas; this one came from filling in the form.

### Fixed

1. **`POST /api/v1/auth/change-password` applied no password policy at all**
   (`apps/api/routes/v1_auth.py`). `ChangePasswordRequest` validated nothing, and the value went
   straight to the Supabase admin API — which does not apply GoTrue's signup policy either. Signup
   refuses anything under 8 characters or missing an uppercase letter, a digit or a symbol. So the
   endpoint was a way to **downgrade**: an account created under the eight-character rule could be
   moved to a six-character one. Measured, end to end:

       change-password new_password="sixchr6"   -> 200 "Password changed successfully"
       signin            password="sixchr6"     -> 200, token issued

   It now applies `_validate_password`, the same function signup uses.

2. **A rejected password was reported as a server fault with the reason thrown away.** The blanket
   `if admin_resp.status_code != 200: raise 500` turned GoTrue's answer into something unrelated:

       GoTrue -> 422 {"error_code":"weak_password","msg":"Password should be at least 6 characters."}
       here   -> 500 "Failed to update password"

   A caller error was logged as an outage and the user was told nothing useful. `_upstream_status`
   now maps 4xx to 400 and only 5xx to 502, and `_upstream_detail` keeps GoTrue's `msg` while
   falling back safely on anything that is not that shape — an HTML error page from a proxy cannot
   leak into a response body.

3. **The UI advertised a password the server rejects** (`apps/web/app/settings/page.tsx`,
   `apps/web/app/account/page.tsx`). Four places said "Min. 6 characters" and enforced only length,
   while signup demands 8 plus three character classes. The minimum now reads 8 in both pages. The
   server stays the authority — a password that passes the length check but lacks a symbol is
   answered with that specific reason, which is more useful than a client-side guess.

   The current password is still verified **before** the new one is judged. That ordering is
   deliberate and is now pinned by a test: reporting "your new password is too weak" to a caller who
   has not proved they own the account would confirm the current password was accepted.

24 new tests, mutation-validated: removing the policy check fails 5, reverting the error mapping
fails 2. Verified live as well as in the suite — six characters now returns 422, the password is
left untouched, and a compliant one still succeeds.

### Verified, not fixed

4. **`routes/v1_otp.py`'s `register_with_otp` and `send_otp` are unreachable.** Both it and
   `routes/v1_auth.py` declare `prefix="/auth"`, both define the same paths, and `auth_router` is
   included first, so FastAPI never reaches the OTP module's copies. Measured: registering with a
   password that has no uppercase letter returns *"Password must contain at least one uppercase
   letter"*, which is a message that exists only in `v1_auth.py`. The shadowed copy carries the
   weaker policy — `password_min_length`, six characters and no complexity — so the live route is
   sound, but a future change to router order would silently weaken it. Recorded rather than deleted,
   per the no-deletions rule.

### Reference

- **A form nobody submits is an endpoint nobody tests.** This endpoint had a passing test suite and a
  validation gap, because nothing drove it with a real password.
- **An admin API does not inherit the user-facing policy.** GoTrue enforces its minimum on signup and
  not on the admin update path, so "the identity provider will catch it" is not a control.
- **One policy, one function.** There were three: `_validate_password`, `_validate_otp_signup_password`,
  and a pydantic validator, with the frontend holding two more numbers.
- **Check the router, not just the function.** Both OTP handlers read as live; only one is.

## Unreleased — production measured for the first time, which corrected the record and found a silent total failure in auto square-off

> The production database was reachable over IPv6 the whole time; only SSH was blocked. Reading it
> turned "production not verified" from an assumption into a measurement — and the measurement
> contradicted three things I had been asserting.

### Corrected

1. **"Six migrations are pending in production" was wrong. Two are.**
   Measured, not inferred:

   | migration | production | verdict |
   |---|---|---|
   | `01000` profiles.phone | `text` | already present |
   | `02000` 8 runtime tables | 8/8 | already present |
   | `04000` orders option columns | 5/5 | already present |
   | `05000` oms_* tables | 3/3 | already present |
   | `03000` stale unique index | still there | **needed** |
   | `06000` strategy_id uuid→TEXT | still `uuid` | **needed** |

   The reason is structural, and it reframes today's migrations: **production was not built from
   `supabase/migrations/`.** The schema was pushed directly. So the order-path P0 (`PGRST204`) was
   never a production bug — which is why production holds 82 orders while a fresh environment could
   not record one. What today's migrations actually did was make the *repository* reproduce
   production, so that CI, a new developer, and a fresh deploy all get a working schema.

2. **"The write fails on a text column" was wrong, twice.**
   I wrote that `set_config` would be *rejected*. Measured, the write **succeeds** and PostgREST
   coerces the list to the string `'[0,1,2,3,4]'`. I then asserted it was *substring matching*;
   measured, `0 not in '[0,1,2,3,4]'` raises `TypeError`. Both were asserted without running it.
   The real behaviour is the third option and the worst one — see below.

### Fixed

3. **`squareoff_config.days` was `TEXT`, and auto square-off was silently dead** (my own bug, from
   `20261003_02000`). `squareoff_service.set_config` is typed `days: list[int]` and writes the list
   straight through. On a text column the write succeeds and the value is stored as a string. The
   scheduler's only consumer is then:

       if current_dow not in days:        # squareoff_service.py:183

   which raises `TypeError`. That test sits inside the loop's own `try`, whose handler logs
   `Squareoff loop error: %s` and `asyncio.sleep(30)`s — abandoning the `for row in configs` loop it
   was in. So **one coerced row stops square-off for every user, every thirty seconds, indefinitely,
   with a single log line as the only evidence.**

   Measured end to end: `days TEXT DEFAULT '1,2,3,4,5'` → write succeeds, stored as
   `'[0,1,2,3,4]'` → membership check raises → whole batch abandoned.

   `20261003_07000` corrects the column to `integer[]` with default `{0,1,2,3,4}`. Both halves of the
   old definition were wrong: the type, and the default. A 1-based `'1,2,3,4,5'` does not merely
   differ from `[0,1,2,3,4]` — index 5 is Sunday, and the intent is Saturday. The conversion handles
   `1,2,3,4,5`, `{0,1,2,3,4}`, `6`, `''` and `{1, 2, 3}`; it is idempotent; and it is a verified
   **no-op on production**, which already has `integer[]` and 0 rows.

   `02000` also claimed this table was mirrored from `alembic/versions/003_create_strategy_and_user_tables.py`.
   That file does not declare `squareoff_config` — it stops at `user_strategies` — so there was
   nothing to mirror from, and production is the only authority that measured the column.

   `coerce_days` normalises at the read boundary as well, so a string row degrades to correct
   behaviour rather than to silence. 18 tests, mutation-validated: neutering `coerce_days` fails 16.

4. **`delete_strategy` relied on a cascade that migration `06000` removes**
   (`application/services/strategy_catalog_service.py`). Production carries
   `strategy_runs_strategy_id_fkey ... ON DELETE CASCADE`, the method deleted only the `strategies`
   row, and nothing else in the tree deletes from `strategy_runs`. `06000` has to drop that key to
   make `strategy_id` TEXT, so applying it would have traded an unrecordable Builder run for
   unbounded orphan run rows. Runs are now deleted explicitly, first. 3 tests, mutation-validated.

### Added

5. **`apps/api/scripts/audit_production_schema.py`** — a re-runnable diff of a live database against
   the repo-migration baseline, narrowed to the tables the API actually queries. Table usage is read
   from the **AST**, so a table named only in a comment or docstring does not count.

   Why that shape: two earlier versions of this analysis produced confident nonsense and both
   failures dictated the design. Grepping the tree for column *names* reported 165 "missing columns"
   including `orders.FILLED`, `strategy_runs.GRAPH` and `profiles.encrypted_access_token` — enum
   values and other tables' columns, leaked by a chain walker that ran 3000 characters past the end
   of its own statement. Column-level inference from source is unsound and this script does not
   attempt it. Grepping for `on_conflict="user_id,broker"` found one hit and nearly blocked a safe
   migration; the hit was a comment explaining why the key had been widened. An AST cannot see
   comments.

   What it reports on production: 47 tables against a 44-table baseline, 61 columns live-only, 27
   baseline-only, 22 type mismatches — of which exactly **7 columns across 3 queried tables** are
   missing in production, and all 7 are already handled by the code:

   - `subscriptions.plan` — `core/capabilities.py` reads `row.get("plan") or row.get("tier")`, and
     production has `tier`.
   - `user_strategies.{entry_time,overall_sl_type,overall_sl_value,overall_target_type,overall_target_value}`
     — `strategy_service.py` deliberately excludes these from the payload and stores them in the
     `config` jsonb, which production has. The docstring at `core/models.py:545` says so outright.
   - `notification_prefs.updated_at` — only ever reached through `select("*")` or `select("channels")`.

   Also fixed in the script itself: an earlier draft wrote 11 bogus `[None, None]` entries keyed by
   table name, inflating the type count from 22 to 33 and burying the real findings.

### Held, deliberately

6. **`03000` and `06000` were not applied to production**, and that is the point of this section.
   `03000` is provably safe against *this* tree — the AST confirms **zero** live
   `on_conflict="user_id,broker"` call sites, and the five dynamic ones resolve to `['oms_order_id']`
   on `oms_bracket_orders` / `oms_oco_orders`. But safety depends on which code is *deployed*, and
   the VPS answers on no port at all: 22, 80, 443, 8000, 8080, 3000 are all closed or filtered, so the
   deployed version cannot be determined. Applying a migration whose safety rests on an unverifiable
   fact is a gamble, so both wait for the deploy window. A validated 67.5 MB backup is on disk.

### Reference

- **Production was reachable; only SSH was not.** An IPv6-only Postgres host answers `psql` fine from
  the workstation while every TCP port on the VPS refuses. "Cannot reach production" was too broad a
  statement for most of this session.
- **Back up before touching production, and check the client version.** `pg_dump` 16.14 refused a
  17.6 server and wrote **0 bytes** — a backup that is silently empty is not a backup. The 17 client
  had to run through a local IPv6 TCP proxy, because Docker Desktop's VM has no IPv6 route and
  `--network host` does not give it the host's loopback either.
- **A schema comparison is only as good as its access method.** Every fabricated finding in this work
  came from parsing or grepping source; every real one came from querying the database.
- **Measure the failure before describing it.** "It fails", "it silently mismatches" and "it raises"
  are three different bugs with three different fixes. I asserted all three before running any of
  them.

## Unreleased — read coverage doubled (33 → 68 declarations), which found two real bugs, and a test that failed on the calendar rather than on code

> Probing the read endpoints no page visit reaches took the contract audit from **33 declarations
> checked to 68**, with **0 mismatches** among the 33 newly covered. It also found two real defects
> and one test that had been failing for a reason that had nothing to do with the code.

### Fixed

1. **The forward-test detail endpoint was declared with fields it never returns**
   (`apps/web/lib/api.ts`, `apps/web/app/forward-test/page.tsx`). `ForwardTestStatus` named
   `started_at` and `stopped_at`. Measured, the two endpoints disagree:

       GET /forward-tests/      (list)   19 keys, including started_at, stopped_at
       GET /forward-tests/{id}  (detail) 11 keys — no started_at, no stopped_at

   The card read both off the **detail** response, so the "Started:" and "Stopped:" lines rendered
   **permanently nothing** — both were behind a `&&` guard, so there was no `undefined` and no crash
   to notice. The values were never missing: they are on the list row the card already holds, and
   the card now reads them from there. The declared type names only what is served.

   This is the last surface that had been "not auditable" since this work began. It became auditable
   the moment a real forward test existed, and immediately paid for itself.

2. **`resolve_named_type` read the raw, unmasked file** (`apps/web/scripts/audit_api_contracts.py`).
   Any prose inside a named type's body was harvested as **fields**. Adding a comment explaining (1)
   produced a fresh, wholly fabricated finding:

       NOT present : DETAIL, LIST, Started, Stopped, measured

   Five "missing fields" that are words from my own comment — a comment describing a finding turning
   itself into the finding. Now masked like the declaration scanner already was. Mutation-validated:
   removing the mask brings the fabricated five straight back.

3. **A test that failed on the calendar, not on a regression**
   (`apps/api/tests/test_intraday_window_widening.py`). `test_a_non_empty_result_is_still_cached`
   mocked a fetch returning candles for a literal `datetime(2026, 10, 1)` while asking for `days=1`.
   `load()` computes its window from the real clock — and with intraday widening that window is about
   **two days** wide — then discards any result that does not cover it:

       if len(candles) < 2 or not self._covers_range(candles, fetch_start, end_dt):

   So the test was correct only while "today" sat near 1 October. It began failing on the 3rd, with
   **no code change at all**, and `first` came back `[]`.

   The session is now derived from `end_dt` — the end of the window the loader actually asked for.
   Proven date-independent rather than asserted: shifting the **window** 400 days into the future
   leaves all 19 tests in the file green. (Shifting the *session* 400 days makes it fail, which is
   correct and is not the same claim.)

   A permanently-red test is worse than a red suite, because every later run then has to be
   re-checked against it to be sure it is not something new.

### Verified, not fixed

4. **`?tab=pnl` and `?tab=strategy-perf` still have no backend.** `/admin/pnl` and
   `/admin/strategy-performance` 404; no equivalent exists, and `/analytics/pnl` is a different shape
   from the declared `PnLData`. Unimplemented features, not wiring mistakes. Recorded, not invented,
   not deleted.

### Reference

- **Audit the reads.** They are free to drive, they cannot change state, and 45 of the 90 declarations
  the audit could not check were GETs. Coverage went 33 → 68 and the writes remain excluded.
- **A comment inside a type body must not become a field.** The declaration scanner masked comments;
  the named-type resolver did not. Same class, two code paths, one fixed.
- **`_covers_range` makes a mocked fetch date-sensitive.** A test that pins "now" with a literal and
  asks for `days=1` is asserting against the wall clock.
- **Prove date-independence by moving the window, not the data.** Both were tried; only the first
  is the claim worth making.

## Unreleased — the referral endpoint 500'd for every user, and three admin tabs had no backend at all

> Found by probing the **read** endpoints no page visit reaches. The writes stay excluded — a probe
> body is not a safe input for an endpoint that places an order — but reads are free to drive, and
> they are where the audit had the least to say: 45 of the 90 declarations it could not check were
> plain GETs.

### Fixed

1. **`GET /referrals/stats` returned 500 for every caller** (`apps/api/routes/v1_referrals.py`).

       ValidationError: 1 validation error for ReferralStatsResponse
       referral_code
         Input should be a valid string [type=string_type, input_value=None, input_type=NoneType]

   The line was `profile.data[0].get("referral_code", "")`. **`dict.get(key, default)` supplies the
   default only when the key is absent.** A SQL `NULL` arrives with the key *present* and the value
   `None`, so the default never applied and `None` reached a `str` field.

   `profiles.referral_code` is NULL until `/referrals/code` is called and nothing else populates it —
   measured at **1 of 1** rows on a clean database. So this was a 500 for effectively every user, and
   a 500 rather than an empty string, so nothing degraded. `/referrals/code` next door gets this
   right with a truthiness check, because there a missing code is *meant* to trigger generation.

   An empty string is the honest value: this endpoint reports, it does not mint, and generating a
   code as a side effect of reading stats would be the wrong verb. A test asserts no write happens.

2. **The Referral System tab called two endpoints that have never existed** (`app/dashboard/referrals-tab.tsx`).
   It requested `/admin/referrals` and `/admin/referrals/stats`. **The admin router has no such
   routes** — not in the code, not in the OpenAPI spec. Both 404'd, `useApi` returned nothing, and
   the tab rendered empty. Repointed to `/referrals/list` and `/referrals/stats`, both measured
   before use; `/referrals/list` answers `{ referrals: [...] }`, an exact match for the declared
   shape.

   The status filter moved client-side, because `/referrals/list` takes no query parameters and
   returns every row regardless — so filtering there costs nothing and is the only place it can
   happen.

3. **The tab rendered a confident `0%` for a metric nothing computes.** Its declared type named five
   fields; the endpoint serves four, two of which are not among them. `conversion_rate` was rendered
   with `?? 0`, so the tab showed **0% conversion** for a metric that does not exist — a fabricated
   number, the same class as the order-fill and P&L% bugs fixed earlier this session.

   `conversion_rate` is genuinely derivable from two served values, and is now computed from them —
   and yields `—` rather than `0%` when `total_referrals` is 0, because "nobody has been referred" is
   not a conversion rate of zero. `users_with_referral_codes` is not derivable from a user's own
   referral rows; its tile says so. The declared type now names only what is served.

### Verified, not fixed

4. **Two more admin tabs have no backend and are not repointed.**
   `?tab=pnl` calls `/admin/pnl` and `?tab=strategy-perf` calls `/admin/strategy-performance`. Both
   404. `/analytics/pnl` is **not** a substitute — it answers `{pnl: {daily}, period, broker}` against
   a declared `PnLData` of `{summary, daily_pnl[], users[]}`, so repointing would produce a page
   reading `undefined` throughout, which is the bug rather than the fix. **No equivalent endpoint
   exists for either.** These are unimplemented features, not wiring mistakes, and the feature freeze
   says fix defects rather than add capability — so they are recorded rather than invented or
   deleted. Both tabs render empty and have done since they were written.

### Added

- `apps/web/scripts/browser/probe_gets.js` — drives the read endpoints no crawl reaches, from the
  audit's own "never exercised" list, and merges the signatures back so the contract audit can check
  them. It refuses to run unauthenticated, because an unauthenticated probe would record 401 bodies
  as verified shapes, and it reports every endpoint it could **not** reach separately, so a probe that
  failed to connect never reads as a pass. **16** read endpoints newly observed; the 4 that 404'd are
  the finding above.
- `apps/api/tests/test_referral_stats_null_code.py` — 7 tests, mutation-validated: restoring
  `.get(key, "")` fails 3.

### Verification

- API **1278 passed, 1 xpassed**; ruff clean. Web 53 lib tests, `tsc` 0, lint 0.
- Crawl **51/51**, interactions **6/6**, session **7/7**.
- Live: the Referral System tab now calls `/referrals/list` and `/referrals/stats`, **both 200**, and
  renders its tiles from real values with no bad values on the page.

### Reference

- **`dict.get(key, default)` does not cover `None`.** It is the single most misleading convenience in
  Python: the default fires on a missing key, not on a null value, and a nullable database column is
  the exact case it misses. There are 14 such call sites in this codebase; the ones that flow into a
  typed response are the dangerous ones, and this was the only one demonstrably 500ing.
- **A 404 behind a `useApi` reads exactly like an empty result.** Three admin tabs, one referral tab,
  and `/portal` all looked healthy while loading nothing.
- **A declared type naming fields nothing serves will render as zeroes.** `?? 0` on an absent metric
  is a fabricated number with a percentage sign on it.
- **Probe reads, never writes.** Driving the audit's own unaudited list is only safe for GETs; the
  writes stay excluded rather than sampled.

## Unreleased — write flows are now exercised through the UI, and three ways the harness could pass for the wrong reason were removed

> The four existing interaction scenarios all checked a **guard** — a control that must stay
> disabled. None of them performed a real write. That is why `/portal` could load a 404 for its
> entire life and every scenario still passed: clicking is the only thing that distinguishes a
> working control from a plausible-looking one.

### Added

1. **Two write-flow scenarios**, both performed through the browser and confirmed after a reload:
   - `strategies` — create through the dialog, confirm the row survives a full reload (so it came
     from the API, not optimistic state), then delete it and confirm it is gone.
   - `marketdata` — add a watchlist symbol, confirm the exact symbol is still listed after a reload,
     then remove it.

   Reload-between-steps is the point. A row that appears in local state proves nothing; a row that
   survives `page.reload()` came back from the database.

   Interactions now **6/6**, and both new scenarios clean up after themselves — verified by running
   three times and confirming zero leftover rows and zero leftover alerts.

### Fixed — in the new scenarios, before they could report anything false

Four defects, all in the tests, all found by checking a surprising result rather than by trusting a
green run:

- **The watchlist assertion passed for the wrong reason.** The modal row is `{name}`, `{symbol}`,
  `{type badge}` on three lines; the scenario took the *last* line, which is the badge — so it
  asserted the page contained the word `"stock"`. A market-data page contains "stock" everywhere, so
  the check passed regardless of whether anything was added. Now it reads the symbol line, rejects
  anything without a `:`/`_`/`-` in it as too vague to assert on, and requires an element whose text
  is *exactly* that symbol.
- **The delete never ran, which read as "delete is broken".** `handleDelete` puts a native
  `window.confirm` in front of every delete; headless Chrome auto-dismisses dialogs unless a handler
  is registered, so the confirm always returned false. `DELETE /strategies/{id}` returns **204** and
  does delete the row — checked directly against the API before touching the test.
- **The row selector never matched.** A ``-anchored RegExp was built with hand-escaped
  metacharacters; the escaping came out as a literal backslash, the pattern matched nothing, and the
  click silently did not fire. Replaced with `String.includes`, which is sufficient for a name the
  page just printed and cannot be mis-escaped.
- **The wrong card would have been deleted.** Ancestors also contain the strategy name *and* a Delete
  button, and the comparator sorted outermost-first, so it would have clicked the first card's
  Delete rather than the probe's. Now ordered by DOM depth. Four identical probe strategies had
  already accumulated from earlier failed runs, which is how the problem was visible.

Two labels were also wrong before any of this mattered: the create control is **"+ New Strategy"**,
not "Create Strategy" (the latter is conditional and was not rendered), and the watchlist remove
control is `<button title="Remove from watchlist">x</button>` — its accessible label is the `title`,
not its text.

### Reference

- **A passing assertion is worth nothing until you check what it asserted.** `document.body.innerText
  includes "stock"` is a true statement about a market-data page. Three of the four defects above
  produced a *pass* or a plausible failure rather than an error.
- **Drive real writes through the UI, not the API.** An API 204 says the endpoint works. It says
  nothing about whether the button that calls it is reachable, or whether a `confirm` in front of it
  swallows the click.
- **Headless Chrome auto-dismisses dialogs.** Any flow behind a `window.confirm` needs an explicit
  `page.on('dialog', …)` handler or it will look broken forever.
- **Assert on an exact element, not a substring of the document.** One call caught a symbol add, one
  would have caught nothing.
- **Clean up after every scenario, and check that cleanup works.** The delete cleanup silently did
  nothing for four runs and left a row behind each time; "removal control found" is now part of the
  note so a broken cleanup is visible.
- Never hand-escape a regex in generated test code. Use `includes` for literal strings.

## Unreleased — auditing as an admin found a fabricated bug in my own audit tool

> Every previous contract-audit run was done as a **non-admin**, so the entire admin surface was
> invisible to it: 46 endpoints observed against 49 as admin, 32 declarations against 36. The run
> that finally included admin data did not find a product bug. It found three defects in the tool
> that has been reporting on this codebase — the last of which had been **silently discarding
> findings** for some time.

### Fixed — in the audit tool

1. **It compared verbs against each other.** `observed` was keyed by **path only**, so `GET
   /admin/admins` (`{admins: [...]}`), `POST /admin/admins` (`{message}`), `PATCH` and `DELETE` all
   collapsed into one entry and the union of their keys was compared against **every** declaration
   for that path. That produced a confident, named, entirely fictional finding:

       MISMATCH  /admin/admins
       declared at : lib/api.ts:575
       as          : { message: string }
       NOT present : message
       present but undeclared: email, full_name, id, is_admin, role

   Nothing was wrong. `api.admin.admins.list()` is declared `{admins: [...]}` and the page correctly
   reads `res.admins`; the `{message: string}` declarations are on `create`/`updateRole`/`remove`,
   which are different verbs. Verified against the live API before concluding anything: `POST
   /admin/admins` → `{"detail": "User not found"}`, `GET /admin/admins` → `{"admins": [...]}`.

   Both sides are now keyed by **(method, path)**.

2. **It was dropping every declared-type finding.** The findings were collected into `report` and
   then printed by `if report: pass`. So the audit could report `mismatching declarations : 1` and
   never say which — a count you cannot act on. Found because the count appeared with no name
   attached; had it been 0, the dead branch would have stayed dead indefinitely.

3. **The crawler never recorded the HTTP method** — every signature had `method: None`, so fix 1 was
   impossible even in principle. The crawler now records `r.request().method()`, and keys signatures
   by method as well as path so two verbs on one path are not deduped into one entry.

### Fixed — in the tooling, from what the above exposed

4. **A coverage gap that was invisible.** With method-aware keys, 90 declarations have no observed
   response for their method — mostly writes, because a page visit does not create an admin or
   cancel an order. The audit reported only a lower "compared" count, which is indistinguishable from
   having nothing to check. **Every unexercised declaration is now named**, with its method and file
   and line. Current honest position: **33 declarations checked, 90 not.**

5. **`/onboarding` failed the crawl for behaving correctly.** The page exists to be skipped once
   onboarding is complete, so `redirected to /dashboard` was reported as a defect — the same shape
   as the `adminRedirected` allowance the crawler already had. Recognised explicitly, with the
   target path listed, so any *other* redirect on that route still fails.

### Verified, not fixed

6. **The `/portal` failure mode is an isolated instance.** The bug fixed in the previous entry was a
   fetch swallowed to `null` behind a guard that skipped a whole render section. That pattern was
   searched for across the app: **20** swallowed fetches (`catch(() => null)`, `catch(() => [])`,
   `catch(() => {})`), and every underlying endpoint was called. All user-reachable ones return
   200 — `/alerts/notification-prefs`, `/alerts/`, `/notifications/telegram/status` — and the three
   admin ones (`/admin/stats`, `/brokers/metadata`, `/admin/users/with-brokers`) return 200 with
   real data once the test user is promoted. So `/portal` was the only place it bit. Recording that
   as a negative result, because "we looked and it is one place" is worth as much as a fix.

7. **The one route the crawler cannot reach works.** 56 page routes exist, 51 are crawled, 4 are
   deliberately skipped; the only remainder is `/strategies/[key]`, a dynamic route the crawler has
   no id for. Opened it against a real builtin key (`trend_rider`): renders, `h1` "Trend Rider", no
   bad values, no page or console errors. So the last uncovered route is covered.

### Reference

- **A tool that names a bug it invented costs more than no tool.** The `/admin/admins` mismatch was
  specific, cited a file and line, and was entirely fictional. Every finding from these harnesses gets
  checked against the live API before it is acted on — that check is what caught this one.
- **Key a comparison by everything that can change the answer.** Path alone is not an identity when
  the same path answers four different shapes.
- **`if report: pass` is worse than a missing feature.** It looks like a placeholder someone meant to
  finish, and it was swallowing every finding in that category.
- **My first fix for (1) was itself wrong.** Reading the method from a fixed 200-character window
  after the path bled into the *next* statement, so `telegramStatus` — a plain GET — was classified
  POST by the following line's `{ method: 'POST' }`, and 26 declarations matched instead of 33. Caught
  by noticing one surprising entry in the output rather than trusting the total. Fixed by walking to
  the closing paren of the `request(...)` call, which is the same "a regex will happily span
  statements" trap the file's own comments warn about.
- **An absent method means GET**, because `request` is declared `const { method = 'GET' }`. Reading
  that default rather than leaving the method unknown is not a guess — and leaving it unknown made
  the audit silently compare nothing, where "0 declarations compared" reads exactly like a pass.
- **The audit had only ever run as a non-admin.** Promoting the test user took coverage from 46 to 50
  endpoints and 32 to 36 declarations. Role-dependent surfaces need auditing in that role.

### Verification

- Web: 53 lib tests, `tsc --noEmit` 0, lint 0. API **1271 passed, 1 xpassed**, ruff clean.
- Crawl **51/51** as admin (the `/onboarding` false positive gone). Interactions 4/4, session 7/7.
- Contract audit as admin: 50 endpoints, **33 declarations compared, 0 mismatches**, 22 casts audited,
  **90 named as never exercised**.
- The keying fix is mutation-checked: reverting to path-only brings the fictional
  `MISMATCH /admin/admins — NOT present: message` straight back.

## Unreleased — the Client Portal's Plan tab had never rendered, and three browser harnesses could pass while signed out

> The crawler reports `51/51 routes clean`, which sounds like the whole UI works. Two things it does
> not mean: a route that renders the **sign-in form** instead of its content is not a failure by any
> existing check, and neither harness nor crawler **verified that it was signed in at all**.

### Fixed

1. **`/portal`'s Plan tab, strategy list and broker connections had never rendered for anyone.**
   `app/portal/page.tsx` loaded its data from `api.portal.me()` → `GET /portal/me`. **The backend has
   no `/portal/*` route at all** — not one, across all 115 non-admin endpoints. So the call 404'd,
   the page's `.catch()` returned `null`, and the `if (portal)` block that populates `plan`,
   `strategies` and `brokers` was skipped on every load. The page then rendered its Overview tab from
   `api.engine.*` calls that do work, which is why it looked healthy.

   Rewired to three endpoints that exist and were measured before use:
   `GET /auth/me/capabilities` for the plan, `GET /strategies/list-builtin` (19 rows, carrying the
   four fields the strategy cards render) for the catalogue, and the credentials fetch the page was
   **already making** for broker connections. `api.portal.me()` is deleted rather than left as a
   404 someone might trust.

   `/auth/me/capabilities` returns its fields **flat**, not nested under a `capabilities` key. The
   nested object the page renders is assembled at the call site instead of being assumed to exist in
   the response — assuming it is exactly the class of bug this file already contains three times.
   `tier_label` is served by no endpoint, so it is the tier written out via a local map; inventing a
   product name on screen would be worse than showing the raw tier. `api.strategies.listBuiltin()`
   gained a type parameter, since an untyped `request(...)` is `unknown` and every read of it is an
   unchecked assumption.

2. **The crawler treated a signed-out crawl as a valid one.** After the local database was rebuilt
   the default demo user no longer existed, and the crawl produced **49 failures out of 51** — every
   route 401ing on unrelated endpoints, with the one real signal ("these credentials are wrong")
   buried in the noise. The cause was that sign-in was inferred from a URL:

       const signedIn = !page.url().includes('/auth')

   The form redirects away from `/auth` even when the API rejects the credentials, so this reported
   success for a user that does not exist. All three harnesses now confirm the session with
   `GET /auth/me` using the cookie the browser just received, and exit non-zero with an actionable
   message instead of producing 49 failures.

3. **`verify_session_survives_reload.js` was pointed at `localhost`.** Cookies are host-scoped and the
   API mints its session for the host it is called from, so a suite running against `localhost`
   cannot read a session made for `127.0.0.1` — the documented gotcha, in the one file whose entire
   job is to prove the session survives a reload.

4. **New: a page that renders the sign-in form is now a crawl failure.** It is not an error in any
   sense the crawler checked — no page error, no console error, no 4xx, no `NaN` — so a route whose
   body was entirely replaced by the auth gate passed as green. Measured across the 47 crawled routes
   before the check was added: **0 auth-gated**. So this is insurance against a future regression
   hiding, not a fix for something currently broken, and it is written up that way.

   `/portal` and `/portal/brokers` are in the crawler's `SKIP` set for a legitimate reason:
   `PortalPage` restores from `sessionStorage['tm_portal_email']` rather than the API cookie, so the
   Client Portal has its own OTP login and an app session does not carry over. That is a design, not a
   bug — it was worth confirming rather than assuming, because a signed-in app user landing on the
   portal's OTP screen looks exactly like a broken page.

### Verification

- Web: 53 lib tests, `tsc --noEmit` 0, lint 0. API **1271 passed, 1 xpassed**, ruff clean.
- Contract audit: 46 endpoints, **32** declarations (was 31 — the new `myCapabilities` type), **0
  mismatches**, 0 fields read but not served.
- Crawl **51/51** with the auth-gate guard in place, sign-in verified. Interactions **4/4**, session
  **7/7** (was 6 — the new `/auth/me` check), interactive audit 0 unlabelled inputs.
- Each harness mutation-checked in the negative direction: with a nonexistent user, the crawler,
  `interact.js` and `verify_session_survives_reload.js` now all abort with exit 2 and the 401 status,
  instead of a crawl of failures.

### Reference

- **A harness that cannot fail on the most common setup is worse than no harness.** All three
  browser scripts shared one assumption: the URL changed, therefore we are signed in. That held until
  the account they hardcode stopped existing, and the failure mode was 49 plausible-looking route
  failures rather than one obvious "not authenticated". Verify the precondition before the thing you
  are measuring.
- **A guard can be narrower than its first draft suggests.** The auth-gate check first fired on 49 of
  51 routes, which looked like the guard over-matching. It was the credentials: the guard was right
  and the crawl was anonymous. Diagnose the number before softening the check.
- **"The page renders" is not "the page works."** `/portal` rendered cleanly for its entire life with
  its primary data source returning 404 and its three sections permanently empty.
- **A `SKIP` entry is a claim about a page, not an absence of one.** `/portal` was skipped for a good
  reason, and reading the gate code first kept that from being "fixed" into a regression.
- `verify_session_survives_reload.js` had `BASE` hard-coded to `localhost` while every other script
  used `127.0.0.1`; it is now hard-coded to `127.0.0.1` on purpose, so the point cannot be configured
  away by an env var.
- **`api.strategies.listBuiltin()` was untyped**, so the new call site read `unknown`. A declared type
  that cannot be checked is worse than `any` in this codebase — it reads as verified.

## Unreleased — a clean rebuild from the repo alone, and a strategy id that was being replaced with a random uuid

> Two things this session. First a verification: **drop the whole `public` schema, replay all 33
> migrations, and re-run the order path.** Then a bug that verification walked into, which had been
> sitting in the code as a documented "P3 schema debt" since August.

### Verified

1. **The repo builds a working database on its own.** `DROP SCHEMA public CASCADE` then all 33
   migrations in filename order: **33 clean, 0 failed.** The result is **44 tables and 1 view** —
   exactly what the hand-built local database had, with nothing missing. The pre-existing uuid row in
   `strategy_runs` survived the rebuild as text.

   Against that from-scratch database: signup 201, signin 200, and three paper orders through
   `POST /engine/trade` all `FILLED` at real prices (22424.19 / 2075.21 / 1035.10) with `validity=DAY`
   recorded, three auto-brackets persisted, zero `Failed to persist paper order`, and the trade-ledger
   dedupe guard firing three times on the real path. **The order path no longer depends on anything
   that was applied by hand.**

   The exercise also surfaced a genuine gap: **50 of 115 non-admin write endpoints** were probed with
   bodies derived from the OpenAPI schema, and 6 returned 5xx. Four turned out to be correct behaviour
   under deliberately invalid input (a Razorpay plan id missing from local config is genuinely a 500),
   and two exposed real defects, both fixed below. 14 endpoints were excluded on purpose — anything
   that could move money, stop trading or destroy data — and the exclusion list is recorded rather
   than assumed.

### Fixed

2. **A Builder strategy could never have a run, and the failure was disguised as success**
   (`supabase/migrations/20261003_06000_strategy_runs_strategy_id_text.sql`,
   `apps/api/strategy_runtime/manager.py`, `apps/api/application/services/engine_service.py`).

   Three tables use two id vocabularies, and `strategy_runs` was wired to only one:

       strategies.id           uuid    legacy catalogue
       builder_strategies.id   text    Strategy Builder — uuid.uuid4().hex[:12]
       strategy_runs.strategy_id uuid  NOT NULL, FK → strategies(id) ON DELETE CASCADE

   `uuid.UUID('3838c1dcdc97')` raises `ValueError`, so **no Builder run could ever be recorded** and
   `POST /engine/start` answered `INTERNAL_ERROR` for a perfectly valid id.

   The quiet part is worse than the crash. `strategy_runtime/manager.py` worked around it:

       try:
           sid_str = str(uuid.UUID(record.spec.strategy_id))
       except (ValueError, TypeError):
           sid_str = str(uuid.uuid4())

   That coercion fails for *every* Builder run — the normal path, not the edge case — so a **random
   uuid was substituted** and the run row was written against a strategy that never existed. The
   status update then filtered on `.eq("strategy_id", sid_str)`, matched the row it had just written,
   and behaved as though all were well. Nothing was logged. The run was unattributable: there is no
   way afterwards to tell which strategy produced it. A fabricated identifier that satisfies its own
   lookup is the most expensive kind of wrong record, because no check can catch it.

   `strategy_id` is now TEXT and the foreign key is dropped. Both vocabularies fit; no reader needs a
   cast (nothing compares this column to `strategies.id`, and there is no PostgREST embed joining
   them); `user_id` stays uuid with its working FK. The runtime now passes the id through verbatim.

   **The FK is gone, so `create_run` verifies the strategy exists** — against `strategies` *and*
   `builder_strategies` — before recording. Dropping the key also dropped the only thing rejecting a
   run for a strategy that does not exist, and without this check `POST /engine/start` answers
   `{"status": "running"}` for any string at all, which is a phantom strategy in the runtime
   dashboard. A lookup that cannot complete is treated as not-found, so a database blip refuses the
   run instead of admitting an unverified id.

   `create_run` also no longer ends in `result.data[0]["id"]`: an insert that returned no row raised
   `IndexError`, surfacing as an `INTERNAL_ERROR` that never mentioned the run was not recorded.

3. **The `ON DELETE CASCADE` that went with the FK is a behaviour change, and it is the right one.**
   `strategy_catalog_service.delete_strategy` deletes from `strategies`, which until now also removed
   that strategy's run rows. Runs now survive. A run is a record of trading that actually happened and
   a catalogue tidy-up should not erase it — but this is a change, not a no-op, so it is stated here
   rather than left to be found. Restoring cascade properly means an explicit user-scoped delete in
   `delete_strategy`, not a foreign key that cannot represent a two-table relationship.

### Added

- `apps/api/tests/test_strategy_run_id_vocabulary.py` — 13 tests, three mutation groups validated:
  restoring the random-uuid substitution fails 1, restoring `result.data[0]` fails 3, removing the
  existence check fails 3.
- The substitution test asserts against the **source text**, and says why: a random uuid still
  produces a working run row, so a behavioural test passes against the bug. Only reading the code
  catches a substitution that succeeds.

### Reference

- **A workaround for a schema bug is worse than the bug.** Here the uuid column was the fault, and
  the "fix" substituted a fabricated id that satisfied every downstream check. When a workaround is
  found in this codebase, ask what it is hiding rather than what it is protecting.
- **Two id vocabularies in one schema is the root cause, not the column type.** Making it TEXT fixed
  the symptom; the reason it was uuid at all is that it was FK'd to one of two places strategies live.
- **Dropping a constraint transfers its job to code.** The FK enforced existence; the FK removal
  silently stopped it, and the phantom run only appeared because I looked. A migration that removes a
  constraint must ask what was relying on it.
- **An empty response hides; a rebuilt one exposes.** Dropping the schema and replaying found a bug
  that a hand-built database had been concealing for weeks.
- `tests/test_engine.py::test_engine_start_invalid_broker` is marked `xfail(reason="requires real
  Supabase")` and now **XPASSes locally** because local Supabase is up. CI does not start a Supabase
  service (`SUPABASE_URL` falls back to `localhost:54321` with nothing listening), so the marker must
  stay — removing it turns CI red. `xfail_strict` is not set, so an XPASS does not fail the suite.
- **When writing a test for a substituted value, find out what the mock is actually handed.** Patching
  `async_safe_single` means the argument is the built query *chain*, not the table object, and a
  `MagicMock` chain does not know which table it came from.

## Unreleased — the order audit trail exists, and with it two frontend bugs that were unreachable until now

> Fixing the order path (previous entry) made `GET /engine/orders` return rows for the first time and
> positions able to close for the first time. Both states were previously unreachable, and both were
> hiding defects that had been sitting in the code the whole time. This is the clearest instance yet
> of the pattern in this repo: **an empty response reads exactly like a working one.**

### Fixed

1. **`NaN` in the P&L% column of every closed position** (`apps/web/app/positions/page.tsx`,
   `apps/web/lib/positions.ts`). The percentage was computed inline, in three places, as

       p.average_buy_price ? (pnl / (Math.abs(p.quantity) * p.average_buy_price) * 100) : 0

   A closed position has `quantity = 0` and keeps its average price, so `Math.abs(0) * 2075.21` is
   `0`, and `0 / 0` is `NaN`, which `.toFixed(2)` renders as the string `"NaN"`. The guard tested
   `average_buy_price` and never the denominator. The CSV export had the same expression, so the
   downloaded file carried `NaN` too.

   Unreachable until now: nothing could close a position, because no order could be recorded. The
   observed row was `NSE:TCS-EQ  quantity=0  average_buy_price=2075.21  unrealised_pnl=0`.

   The same expression was **also** wrong for shorts, more quietly: a short has
   `average_buy_price = 0`, so every short position reported a confident `0.00%` rather than the
   obviously-broken `NaN`. Now `positionPnlPct()` in `lib/positions.ts`, using the side-correct basis
   (`average_sell_price` for a short, matching `positionPnl` and the backtest engine) and returning
   `null` — not `0` — when there is no basis, so the cell shows `—`.

2. **An intermittent hydration mismatch in `/live`** (`apps/web/lib/use-mounted-clock.ts`). The header
   rendered `new Date().toLocaleTimeString(...)` **in the render body**. The server renders the tree,
   ships that HTML, then the browser re-renders to hydrate; when a minute boundary fell between the
   two passes the server wrote `03:38 am` and the browser computed `03:39 am`, and React reported
   "Text content did not match server-rendered HTML". Intermittent by construction — the crawl is
   clean most runs and fails whenever it happens to straddle a minute change, which is how something
   like this survives a long time looking fine. `useMountedClock()` returns `null` until after mount,
   so both passes agree on empty.

   Verified structurally rather than by luck: the SSR HTML for `/live` now contains `--:--` and **no**
   clock time at all, so the server cannot emit a non-deterministic value.

3. **Every broker timestamp was formatted in the server's timezone** (11 call sites across 9 files).
   `toLocaleTimeString()` with no `timeZone` formats in the *runtime's* zone: UTC on the server, IST
   in an Indian user's browser. Same input, two different strings, hydration mismatch — and it cannot
   reproduce on a laptop where both halves run in the same zone, so it is invisible to local testing
   and would fire in production. Every broker timestamp is now pinned to `Asia/Kolkata`, which is also
   simply correct for an Indian broker terminal. `app/strategies/page.tsx:344` also had a
   `|| Date.now()` fallback, which is a render-time clock in its own right; it is guarded instead.

4. **17 form controls had a visible but unassociated `<label>`** (`/backtest` 12, `/terminal` 5). The
   label rendered directly above the control with no `htmlFor`/`id` pair, so nothing announced it.
   Added the association — the canonical mechanism, and zero visual change.

### Fixed — in the audit tool itself

5. **`audit_interactive.js` called correctly-labelled controls unlabelled.** Its accessible-name
   function checked `innerText`, `aria-label`, `title`, `placeholder` and `aria-labelledby`, and never
   `<label for>` or a wrapping `<label>` — the canonical HTML mechanism, and the one assistive
   technology actually uses. It reported all 17 controls in item 4 as defective.

   This is the failure mode this tool already had once: an earlier version omitted `placeholder` and
   produced fifteen false "no label" findings, fixed by adding `placeholder`. A detector that reports
   correct code as broken trains you to ignore it, and a detector you ignore finds nothing — so this
   was worth fixing properly rather than by suppressing the finding. It now resolves `label[for]` via
   `CSS.escape` and falls back to `el.closest('label')`.

   Mutation-validated both directions: 0 findings on the correct markup, and 1 finding when a single
   `htmlFor` was removed.

### Added

- `apps/web/lib/use-mounted-clock.ts` — `useMountedClock()` and `IST_TIME`, with the reasoning for why
  a clock cannot appear in a first render and why `timeZone` must be pinned.
- `apps/web/lib/positions-pnl-pct.test.ts` — 11 tests, mutation-validated (restoring the original
  expression fails 5).
- Note on the `size <= 0` guard in `positionPnlPct`: it is **not** load-bearing on its own — the
  trailing `Number.isFinite` check would also reject the `NaN`. It is kept because it states the
  reason (a closed position has no exposure) more clearly than relying on catching `NaN`, and the
  mutation that removes it alone correctly fails nothing.

### Verification

- API **1258 passed, 1 xfailed**; ruff clean. Web **53** lib tests (was 42), `tsc --noEmit` 0, lint 0.
- Contract audit: 46 endpoints observed, 31 declarations, **0 mismatches**, 0 fields read but not
  served — and this is the first run in which `/engine/orders` had rows to compare against, so that
  endpoint is no longer unchecked.
- Browser: crawl **51/51** clean (three consecutive runs), interactions **4/4**, session **6/6**,
  interactive audit **0** unlabelled inputs. `/positions` and `/orders` probe: **0** `NaN` occurrences
  after hydration, was 1 each.

### Reference

- **A guard on one operand is not a guard on the other.** `p.average_buy_price ? pnl / (|qty| * avg) : 0`
  checks the numerator's companion and divides by an unchecked denominator. Any division needs both
  sides checked.
- **A fixture suite written only against reachable states passes against code that breaks when a new
  state arrives.** Every position fixture in `lib/positions.test.ts` was an *open* position, because
  that was all that could exist. The closed-position case was never written, so it was never wrong.
- **Flaky detection needs a structural check, not more runs.** Three clean crawls do not prove a
  minute-boundary race is gone; "the SSR HTML contains no clock time" does.
- **Timezone bugs hide in local testing by construction.** Server and browser share a zone on a
  developer machine, so the mismatch can only appear in production. Pin `timeZone` on anything
  rendered from a broker timestamp.
- **A CSS assertion beats a text assertion for a client-component page**: the `.next` dev server
  compiles on demand, so the first hit can carry stale HTML. Check `app/page.tsx` (source) rather than
  a rendered chunk when confirming a component was removed.

## Unreleased — orders could never be recorded, paper fills were invented, and the OMS retried resting orders into false rejections

> Six defects on one path: place an order → it is recorded, priced honestly, and told to the user
> accurately. Every link in that chain was broken, and every one failed silently.
>
> The starting symptom was a paper order returning `REJECTED` with `message: ""` and `reason: ""`,
> writing no `orders` row at all. Chasing that empty reason turned up a P0 that makes the platform's
> order audit trail — the record of what it actually sent a broker — impossible to produce, and four
> separate fabrications of market data behind it.

### Fixed

1. **P0 — no order was ever recorded** (`supabase/migrations/20261003_04000_orders_option_columns.sql`).
   `core.models.NormalizedOrder` carries `expiry_date`, `instrument_type`, `option_type`,
   `strike_price` and `validity`. `execution/manager._insert_order_atomic` dumps the whole model and
   inserts it, so every insert sent all five — and PostgREST rejected the entire row:

       PGRST204  Could not find the 'expiry_date' column of 'orders' in the schema cache

   No other field was missing, so this was not partial drift: the table predates those model fields
   and nothing ever reconciled the two. `_insert_order_atomic` catches the exception, logs at ERROR
   and returns `None`; the caller reads `None` as "no existing order" and answers

       ExecutionResult(success=False, message="Order insert failed — unknown error",
                        error_code="INSERT_FAILED")

   which is what the user sees. So **not a wrong order — no order**. `GET /engine/orders` was
   permanently empty, `risk.helpers.compute_daily_pnl_fifo` always read zero, and the audit trail
   did not exist. `validity` was the subtle one: the insert loop only drops that field when it is
   *falsy*, and `"DAY"` is truthy, so the column was genuinely required. Migration replays clean from
   a pre-migration table and is idempotent (verified twice).

2. **A paper fill could be invented** (`apps/api/paper/fill_engine.py`). `_get_fill_price` had a
   branch that fabricated an option premium whenever nothing could price the symbol: a hardcoded
   underlying (`81000.0` for SENSEX, `24500.0` otherwise), a distance-from-strike formula, a
   `hash(symbol) % 7` jitter, an 8.0 floor — and then `market_cache.put_quote` with the result, so
   an invented number became the cached "quote" that every later reader of that symbol inherited.
   Removed. A distance formula is not a quote: it is a second opinion about volatility and theta
   computed without either, and `hash(sym)` made it differ between processes. An option with no
   resolvable price now stays PENDING, which is what a cash order already did.

3. **A fill of one lot at zero rupees was reported FILLED** (`apps/api/paper/fill_engine.py`).
   `_build_fill` guarded `quantity <= 0` but never the price, and every fill path funnels through
   it — while `PaperBroker.place_order` only parks an order as PENDING when `filled_quantity <= 0`.
   So a zero-*price* fill sailed past that check and was written to `orders` as FILLED with
   `average_price = 0`; the position layer then refused to apply it ("Skipping trade with zero fill
   price"). The audit trail claimed a fill that never happened, at no price. Now guarded on price
   too, which sends the order down the PENDING path it was always meant to take.

4. **Every paper fill was recorded twice** (`apps/api/execution_engine/trades.py`). One record came
   from the paper broker under its own `client_order_id` (`paper_1_…`), one from the execution
   manager under the engine's (`e39181429f…`), both carrying the same `broker_order_id`:

       client=paper_1_179097  broker_oid=paper_1_179097  NSE:NIFTY50-INDEX  BUY 5 @22424.19
       client=e39181429f7dd6  broker_oid=paper_1_179097  NSE:NIFTY50-INDEX  BUY 5 @22424.19

   `GET /paper/trades` listed every trade twice and `totals()`/`turnover()` double-counted them.
   `TradeLedger.add` now declines a repeat, keyed on `(broker_order_id, quantity, price)` — order id
   alone would discard the several fills a partially-filled order legitimately produces, and losing
   quantity understates a position, which is worse than a duplicate. Records with no
   `broker_order_id` are always kept: there is nothing to compare them on, and dropping an
   unidentified real trade loses data.

5. **Paper order persistence could never work** (`apps/api/paper/paper_broker.py`).
   `_persist_order` upserted with `on_conflict="user_id,client_order_id"`, but `orders` carries that
   pair as a **partial** unique index (`WHERE client_order_id <> ''`), and Postgres infers a
   conflict target from a partial index only if the statement reproduces the predicate —
   supabase-py cannot send one. Every call failed with 42P10, swallowed at ERROR level:

       Failed to persist paper order: there is no unique or exclusion constraint matching the
       ON CONFLICT specification

   The index cannot simply be made non-partial: `NormalizedOrder.id` defaults to `""` and falsy
   fields are stripped, so many rows carry an empty `client_order_id` and the primary key is absent
   from the payload too. Replaced with an explicit delete-then-insert keyed on the same columns —
   the pattern `core/telegram.py` already uses for this PostgREST limitation. Verified by restart:
   paper positions now survive a process restart, which they previously did not.

6. **OBSERVED ONCE, ROOT CAUSE NOT PINNED — not reproducing.** While migrating the schema, a batch
   of three paper orders came back `REJECTED / "Validation failed"` while `orders` held PENDING rows
   for the *same* client order ids, and the OMS log showed one `oms_order_id` re-enqueued four times
   (`attempt 1, 2, 3`). From the second attempt `validate_order`'s `_check_duplicate` finds the
   order's own row and rejects it, so the user is told REJECTED while the order rests PENDING.

   This could not be reproduced on a clean slate. `oms/manager.py:504` shows a successful-but-resting
   order takes the PENDING branch and is **not** re-enqueued — the retry path at line 511 is only
   reached when `exec_result.success` is False. Measured directly on the PENDING path: **0 retries,
   0 validation failures**, and the audit row reads `PENDING filled=0 @0`, not a fabricated
   `FILLED @0`. The observed batch was placed while `orders` still held rows from earlier probe
   scripts, so the most likely explanation is that residue rather than a live defect — but "most
   likely" is not a diagnosis and it is recorded here as unexplained rather than closed.

   One thing is worth preserving regardless, because it constrains any future fix: the duplicate
   check runs **before** `_insert_order_atomic`, so it is what currently stops a retry re-sending to
   the broker. `idx_orders_client_order_id` plus `ExecutionManager._check_existing_order` already
   implement the correct idempotent path (`DUPLICATE_REQUEST`, returning the existing order) that
   validation pre-empts. Deleting the check would re-open a double-send risk, which is why nothing
   here touches it.

7. **Paper fills had no price source outside a broker token** (`apps/api/paper/paper_broker.py`).
   `_ensure_quote` tried only the in-process cache and Fyers, so every paper-only tenant — and any
   tenant whose token had expired — got `filled_price=0`, which (3) then turned into a fake fill.
   Added the Yahoo fallback `GET /marketdata/quote` already uses to fill whatever the broker did not
   price. Yahoo prices are real market data, not a substitute, and this is the same broker-first
   trade that route already makes; if neither source has a price the order still goes out unfilled.

### Added

- `supabase/migrations/20261003_05000_oms_persistence_tables.sql` — `oms_orders`,
  `oms_bracket_orders`, `oms_oco_orders`. `oms/persistence.py` upserts all three on every order and
  logs a WARNING when it fails, so the queue keeps running and the API answers 200 while nothing is
  persisted:

      Failed to persist OMS order 47951fc0…: PGRST205 Could not find the table 'public.oms_orders'

  `oms_orders` is what makes in-flight orders survive a restart (`_recover_active_orders` reads it on
  boot), so its absence means a restart silently forgets what was already sent to a broker — the one
  moment where re-sending is genuinely dangerous. The module's docstring says to "run in Supabase SQL
  Editor" and gives a 4-column sketch, but `OmniOrder.model_dump` sends **37** and PostgREST rejects
  the whole upsert if any one is missing; columns are derived from the models, not the sketch. No FK
  on `user_id`, which may hold `paper:<uuid>` or `backtest:<hex>`.

- `apps/api/tests/test_trade_ledger_dedupe.py` (10), `test_paper_fill_no_fabricated_price.py` (9),
  `test_paper_order_persistence.py` (7). Every one mutation-validated: removing the dedupe guard
  fails 3 tests, restoring the fabricated 80.0 floor fails 5, and restoring the impossible upsert
  fails 5.

### Verification

- API **1258 passed, 1 xfailed** (was 1232); ruff clean. Web 42 lib tests, `tsc --noEmit` 0, lint 0.
- Live through the product's own `POST /api/v1/engine/trade`: two paper orders → `FILLED` at real
  Yahoo prices (22424.19 / 2075.21), **2** trade records (was 4), positions updated and preserved
  across a restart, `Failed to persist paper order` count 0, `Ignoring duplicate trade record` logged
  twice — the guards firing on the real path, not just in tests.

### Reference

- **A model field with no column takes the whole row down, not just itself.** PostgREST rejects an
  insert if *any* key is unknown, so one stale field in a `model_dump`-and-insert made every order
  vanish rather than partially persist. Diff every field the insert actually sends against
  `information_schema` — and remember conditional pop lists: `validity` is dropped only when falsy,
  so `"DAY"` is sent and the column is required.
- **Postgres cannot use a partial unique index as an `ON CONFLICT` target** without the predicate,
  and supabase-py cannot send one. Any `on_conflict=` naming a column that is only partly unique is
  42P10 on every call. Delete-then-insert is the workaround.
- **A guard on quantity is not a guard on price.** `_build_fill` checked `quantity <= 0` while the
  caller checked `filled_quantity <= 0`; a zero price slipped through both and was reported as a
  fill.
- **`hash(sym)` in a price path makes it differ per process.** Any non-determinism in a price is a
  bug regardless of how small the jitter looks.
- **The demo API dies when the shell call that launched it exits** — it takes a graceful shutdown
  ("Graceful shutdown complete", full ordered teardown), not a crash. Verify within a single
  invocation.

### Known gaps

- Item 6 is **unexplained, not fixed**: observed once under a dirty schema, does not reproduce, and
  its root cause was not pinned. Worth watching for rather than treating as closed.
- Whether production has these tables/columns is **not verified** — the VPS does not answer from this
  workstation. `IF NOT EXISTS` makes applying `04000`/`05000` either way a no-op rather than a
  failure, but production is not measured.
- `20261003_03000` still needs applying to production; `apps/api/.env` still points at local
  Supabase. Load Test needs `DOCKERHUB_TOKEN`; Fyers re-auth needs the PIN + OTP; Dhan market data
  not subscribed until Oct 4.

## Unreleased — the Trade Journal had never rendered its own analytics, and 8 tables the code depends on were never in a migration

> `/journal` declared three response shapes and **none of them existed**. Its `JournalData`
> interface is recognisably a *backtest* result payload — `win_rate`, `sharpe_ratio`,
> `max_drawdown`, `equity_curve`, `monthly_returns` are what `PerformanceAnalytics` produces and
> what `routes/v1_backtest.py` serves — applied to a page reading a live journal endpoint that
> returns `{ analysis, stats }`. Nothing computes those figures for live trading anywhere in the
> codebase.
>
> The page passed every check available. It threw nothing, logged nothing, and rendered its
> "No trading data yet" empty state **permanently**, because the guard
> `total_trades > 0 || entries?.length > 0` was reading two `undefined` values and so was always
> false. A page that is quietly always-empty looks exactly like a working one.

### Fixed

1. **`/journal` crashed the moment a user wrote a journal entry** (`apps/web/app/journal/page.tsx`).
   The trade table renders when `filteredTrades.length > 0` and was fed `/ai/journal/entries` —
   rows of `journal_entries`, whose columns are `id, user_id, entry_type, content, tags,
   trade_ids, created_at`. Only `id` was in the declared `Trade` shape, so `fmt(t.price)` received
   `undefined` and threw.
   **Verified rather than argued:** inserting one `journal_entries` row put `/journal` into its
   error boundary with `Cannot read properties of undefined (reading 'toLocaleString')`. A user's
   first journal entry took the page down. The route crawler could not see it, because the crash
   requires the data to be present and the test user had none.

2. **`/journal` rewritten against what exists** (`apps/web/app/journal/page.tsx`). Four tiles
   labelled with what `_compute_stats` returns; the AI narrative, which is the one genuinely rich
   thing the endpoint returns, given real estate instead of being buried; trade history rebuilt on
   `/engine/orders`, whose rows carry real `symbol`, `side`, `quantity`, `filled_quantity`,
   `average_price`, `status`, `broker` and timestamps; journal entries listed with their real
   columns. `SvgEquityCurve` and `MonthlyBars` were **removed rather than left rendering nothing** —
   a component that cannot produce output is a codebase that lies about what it does.
   The per-trade analytics are gone rather than rendered as zero, and the page says why.

3. **The symbol search and Buy/Sell filter on `/journal` work for the first time.** Both compared
   against `undefined` because `Trade.side` and `Trade.symbol` did not exist; selecting either side
   always produced an empty table.

4. **`ai/copilot.py` read a table nothing has ever written** (`apps/api/ai/copilot.py`). The
   recent-backtests context read `backtest_results`; `backtest/manager.py` persists to
   `backtest_runs`. PostgREST answered `PGRST205`, `async_safe_execute` caught it, and the
   context was set to `[]`. **The copilot has always reasoned about a user with no trading history**
   regardless of what they ran. The only evidence was one WARNING per request.

5. **`/api/v1/alerts/` returned 500 for every alert** — `user_alerts` did not exist in this
   repository at all (see the migration below). The `/alerts` page showed an empty list, which is
   indistinguishable from a user who has set none. Found only by creating an alert through the
   product's own endpoint; loading the page would never have revealed it.

6. **The market-data / execution credential split did not work, and its own migration is why**
   (`supabase/migrations/20261003_03000_drop_stale_broker_credentials_unique.sql`,
   `apps/api/broker_connect/db/connections.py`). Two migrations disagree about uniqueness:
   `20260828_02200` creates a standalone unique **index** `uq_broker_credentials_user_broker` on
   `(user_id, broker)` for the OAuth upsert, and `20261002_01000` later adds the `role` column with
   `UNIQUE (user_id, broker, role)`. `01000` tried to clear the way with
   `DROP CONSTRAINT broker_credentials_user_id_broker_key` — but that is the *init* migration's
   inline constraint, a different object. **`DROP CONSTRAINT` cannot drop a plain unique index.**
   The stricter index survived, so two rows for the same `(user_id, broker)` are impossible no
   matter what `role` says, and saving a market-data credential raises `duplicate key value
   violates unique constraint`.
   The `on_conflict="user_id,broker"` in the connect upsert had the same problem: it would collide
   with an execution row and overwrite it instead of inserting a second role. Now `user_id,broker,role`.

### Why the production verification of `01000` did not catch this

It could not have. `verify_production_broker_roles.py` checks that the `role` column is readable
and that rows are addressable by role; it does not **insert** a second role. All 17 production
rows are `execution`, so no pair ever collided and the stale index stayed invisible. **The same
defect is therefore likely present in production** and needs `03000` applied there — which needs
the Supabase DB password, not available from this workstation.

### Added — migrations

7. **`supabase/migrations/20261003_02000_missing_runtime_tables.sql`** — the eight tables the API
   reads or writes and no migration in this directory creates: `user_alerts`,
   `notification_prefs`, `margin_snapshot`, `squareoff_config`, `strategy_health`,
   `multi_leg_strategies`, `multi_leg_strategy_legs`. Every one exists in production because it was
   created there by hand; none of it was ever captured.
   **A fresh environment built from this repository could not start**, and the failure was silent:
   `core.safe_query` catches every query error and returns `None`/`[]`, so callers read "no rows"
   where the truth is "no table". Columns are taken from the code that uses them —
   `strategy_health` mirrored from `alembic/versions/003_…`, `multi_leg_*` from the insert payloads
   — rather than guessed. `backtest_results` is deliberately **not** created: creating it would make
   the copilot's dead query look alive.
   Idempotent, and a verified no-op on production where all eight already exist.

8. **`supabase/migrations/20261003_03000_drop_stale_broker_credentials_unique.sql`** — drops the
   stale index and re-asserts `(user_id, broker, role)` uniqueness. Skips the constraint when the
   `role` column does not exist yet, so it is safe to apply before deploying `01000`.

Applying the full migration set in order, as a rebuild would, is now clean: **22 applied, 7 no-ops,
1 failure, all 7 being `already exists` duplicates** — no genuine breakage.

### Added — tooling, each validated by mutation rather than by reading it

9. **`scripts/browser/crawl_all_routes.js`** — crawls all 51 routes, and now also fails a route
   whose rendered text contains `NaN`, `undefined`, `[object Object]`, `Infinity` or `₹NaN`. The
   existing crawler only caught *failures*; a mismatched type produces no failure, it renders a
   value that is not a value. Proven by injecting all five forms into `/journal` and confirming
   exactly that route is flagged.

10. **`apps/web/scripts/audit_api_contracts.py`** — diffs each declared response type **and each
    untyped `as { … }` cast** against the keys the endpoints actually returned. `api.ts` has 119
    `request()` calls, 25 without a generic, and pages cast 22 more results by hand; a cast asserts a
    shape as firmly as a declared type and fails exactly as silently.
    Result: **47 endpoints, 31 declarations, 22 casts, 0 mismatches.** Four are reported as
    *not auditable* rather than passed — two generic instantiations the resolver does not handle and
    one endpoint with no rows — which is the only honest thing to say about them.

11. **`apps/api/scripts/audit_table_coverage.py`** — reports tables the code touches that the schema
    lacks, and for each whether a migration **creates** it (comments stripped first) or merely
    mentions it. Found the eight above; revalidated by reintroducing the `backtest_results` bug.

### Four bugs in the audit tool itself, each found by distrusting its own output

Worth recording because each would have made the tool report things that were not true, and for a
bug-finder that is worse than having none — the findings get ignored.

- **Field extraction by regex.** `[^{]` also matches `}`, so a greedy group ran past the end of one
  interface and captured the next one's body. `Alert` resolved to `JournalNote`'s fields; every
  finding was fabricated. Now extracted by brace matching.
- **An apostrophe in a comment.** `/** the model's parsed output */` was read as an unterminated
  string literal, swallowing the closing brace of the type being resolved. `JournalResponse` was
  "unresolvable" while sitting in plain sight.
- **A kind vocabulary that did not match itself.** `resolve_named_type` returned `'fields'` where
  the caller compared against `'inline'`, so every *successfully resolved* named type was reported
  as unresolved — the audit skipped exactly the declarations it exists to check, and looked clean
  because of it.
- **Empty data read as a mismatch.** Two endpoints returned no rows, so comparing a declared type
  against an empty set marked every field missing. Both produced a page of invented findings.
  Absence of data is now reported as not-auditable.

The table-coverage tool made the same class of mistake twice more: it read the wrong repository root
and reported `0` migrations, and it matched its own source file as a phantom table named `x`.

### Earlier in this session

12. **Session P0** (`apps/web/app/auth/page.tsx`) — the sign-in handler's `finally` block cleared
    `tm_auth_token` after a **successful** login, and session restoration gates on that key. Every
    full page load bounced to `/auth` while every API call returned 200, because the httponly cookie
    was still valid. Symptom: "logged out again". No test could have caught it — nothing throws,
    nothing 4xx's, and the cookie stays valid.
13. **CSP made local development impossible** (`apps/web/next.config.js`) — `'unsafe-eval'` was
    omitted from `script-src`, so hydration failed and pages sat on skeletons making **zero network
    requests**; and the API origin in `connect-src` was hardcoded, silently overriding
    `NEXT_PUBLIC_API_URL`. Now environment-aware, and the production policy is byte-identical to
    the string it replaces.
14. **`useApi` never resolved** (`apps/web/lib/use-api.ts`) — the shared inflight promise was bound
    to the hook's own `AbortController`, so React 18 StrictMode's mount/cleanup/mount aborted it and
    the second mount reused the dead promise. 16 files' worth of pages reported
    `Request timed out` against requests the server answered in milliseconds. **Development only** —
    verified by serving a production build with the original code, which renders all seven pages
    correctly.
15. **Three pages crashed on every render** (`/transparency`, `/reports/daily`, `/forward-test`) —
    `x !== null` is not a presence check (`undefined !== null` is true), `{data ? … : '—'}` guards
    the envelope rather than the field, and `GET /forward-tests/` answers `{ items: [...] }` while
    the client typed it as a bare array. Added `lib/format.ts` so the next page does not re-derive a
    guard.
16. **The whole type scale was 0.8125x smaller than written.** `html, body` shared one rule with
    `font-size: var(--text-base)`; on the root element a `rem` resolves against the *initial* 16px,
    not against itself, so the root became 13px and **every other rem token then resolved against
    13px instead of the 16px it was authored against**. Median rendered text 10.07px → 12.07px,
    smallest 8px → 10px, measured across three independent size mechanisms.

### Verification

Route crawler **51/51**, with the bad-value detector active. Web lib tests 42 passed, `tsc --noEmit`
clean, `npm run lint` 0 errors, build compiles. API suite **1198 passed, 1 xfailed**, ruff clean.
Table coverage: every table the code touches exists and the schema is reproducible from the
migrations in order.

### Known gaps — nothing here was verified against production

The VPS is unreachable from this workstation (DNS resolves `187.127.185.56`, general egress works,
the host does not answer), so none of this was confirmed against production. Specifically:

- **`20261003_03000` needs applying to production** for the credential split to work there.
  `02000` should be a no-op there, but that is inferred from `IF NOT EXISTS`, not measured.
- **`apps/api/.env` still points at the local database** — the backup was lost when the server was
  restarted, `.env.vault` is encrypted and needs a `DOTENV_KEY` that is not present locally, and the
  VPS is unreachable. **Deploys are unaffected**: `deploy.sh` requires `apps/api/.env` on the host
  and it is gitignored, so it survives `git reset --hard`. Only local development is affected.
- Load Test has never passed — it needs a `DOCKERHUB_TOKEN` secret.
- Fyers needs a manual re-auth (PIN + OTP). Dhan market data is not subscribed until Oct 4.

## Unreleased — every position row on `/paper` was coloured as a loss

> `/paper` coloured its positions table with `p.side === 'BUY'`. A position's `side` is
> `LONG` / `SHORT` / `FLAT`, not `BUY` / `SELL` — those are the *order* vocabulary. The
> comparison was therefore never true, and both directions rendered red. A profitable long
> showed the text `LONG` in the loss colour, while a short was red by coincidence rather than
> by being recognised. The colour carried no information at all.

### Fixed
1. **`/paper` positions Side column** (`apps/web/app/paper/page.tsx`) — now `isLong(p)`. The
   trade list directly below it still compares against `'BUY'`, correctly, because those rows
   are `TradeRecord`s and fills really do carry `OrderSide`. The comment at the cell records
   why the two tables differ, since "why is one BUY and the other LONG" is the obvious next
   question.
2. **`lib/positions.ts` gains `PositionSide`, `positionSide()` and `isLong()`** — the direction
   vocabulary named once, with 7 assertions. `positionSide()` prefers the `side` the API sent
   but falls back to the sign of `quantity`, which is what `positions.py` uses to derive `side`
   in the first place, so a payload that omits the field still classifies correctly. An
   unrecognised `side` is treated as absent rather than trusted.

Nine other sites in the web app compare `.side` against `'BUY'` and were checked: the rest
either read orders and fills (which do carry `BUY`/`SELL`) or derive their own side from the
sign of `quantity`, as `/positions` does. This was the only one reading a position.

Proven by mutation: `isLong` reverted to `side === 'BUY'` → 2 failures.

A test that only covered a short would have passed against the old code, since `SHORT !== 'BUY'`
too. The long case is the one that separates "correct" from "always red", so that is the case
written.

### A false alarm worth recording
3. The same sweep appeared to find four more missing fields on the paper positions interface —
   `side`, `open_quantity`, `average_price` and `strategy_id` were all absent from
   `paper/models.py::PaperPosition`. They are all present on `execution_engine/positions.py::EnginePosition`,
   which is what `/paper/positions` actually returns: the service does
   `p.model_dump(mode="json")` on `position_manager.get_positions(...)`, not on `PaperPosition`.
   The frontend interface was right; the check had been run against the wrong model. Worth
   stating plainly because the "four missing fields on a money table" framing was announced as
   a significant find before the model was traced back to its source.

### Validation
- Web `lib` tests **28 passed**. `tsc --noEmit` clean, build compiles. API suite **1198 passed,
  1 xfailed** — unchanged, frontend only.
## Unreleased — two of the three P&L tiles on `/funds` were permanently zero

> `/funds` declared one TypeScript interface spanning both response shapes of
> `GET /analytics/pnl` and read all three of its numbers from a single `period=1d` call.
> That endpoint's `1d` branch returns exactly one field. The two cumulative tiles were
> therefore `undefined` on every request, and `?? 0` rendered them as `₹0` rather than a
> dash — so a tenant with open positions and real unrealised profit was shown as flat.

### Fixed
1. **`/funds` P&L tiles** (`apps/web/app/funds/page.tsx`) — now fetches `period=1d` for
   "Today (realized)" and `period=1w` for the cumulative figures, two requests because the
   endpoint has two shapes, not because two numbers are wanted. `/analytics` was already
   doing exactly this; `/funds` was trying to get both from one.
2. **`?? 0` replaced with a dash** wherever the figure is unavailable. `0` means "available
   and flat" and `—` means "this response does not carry that number"; collapsing them made
   the absence look like data. `/analytics` already rendered `—`.
3. **`lib/pnl.ts`** (new) — the two response shapes as separate types plus `pnlTiles()` and
   `formatPnlTile()`, with 11 assertions in `lib/pnl.test.ts`. Inline JSX cannot be asserted
   on, which is why the logic was never covered.

The type split is the durable part. `DailyPnl` and `CumulativePnl` share no properties, so
`pnlTiles(DAILY_ONLY, DAILY_ONLY)` — the original call — is now a **compile error**, not a
silent zero. One test deliberately casts past that error to pin the runtime behaviour, and
says so.

Two mutations confirm the assertions bite:

* absent value coerced to `0` instead of `null` (the original `?? 0`) → 4 failures
* cumulative tiles read off the daily response (the original bug) → 2 failures

Each tile also carries a hint — the period for today's figure, "all time" and "open
positions" for the other two — so "Today (realized)" and "Realized" no longer read as two
labels for one number.

### Validation
- Web `lib` tests **21 passed** (10 position, 11 P&L). `tsc --noEmit` clean, build compiles.
  API suite **1198 passed, 1 xfailed** — unchanged, this commit is frontend only.
## Unreleased — the migrations could not stand up a working database

> Applying the market-data-role migration locally surfaced something much larger. On a
> database built from this directory, `service_role` — the role behind every API read and
> write — had **no privileges on any of the 28 public tables**. Every query returned `42501`,
> `core.safe_query` swallowed it, and the UI showed empty accounts rather than an error.
> Production has these grants, applied by hand and never captured in a migration, so nobody
> noticed. A restore, a staging box or a new machine built from these migrations would have
> looked healthy on `/health` and empty everywhere else.

### Fixed
1. **`20261002_02000_grant_service_role_privileges.sql`** (new) — grants `service_role` full
   table, sequence and function privileges on `public`, plus `ALTER DEFAULT PRIVILEGES` so a
   future migration that creates a table does not reintroduce the gap. Without the default
   privileges the problem returns one release later, which is how it survived in the first
   place. Scoped to `service_role` deliberately: it carries `BYPASSRLS` and is only ever used
   server-side with the secret key. `authenticated` is **not** granted DML here — twelve of
   the 28 tables have RLS disabled, so a blanket grant would expose every row to every
   signed-in user, and which of those should be client-readable is a security review, not a
   side effect of this fix. `anon` needs nothing: it is only sent as the `apikey` header on
   GoTrue calls.
2. **A test file that would have written to production.** The new database-backed tests call
   `activate_broker`, which issues UPDATEs — and `apps/api/.env` points at production
   (`*.supabase.co`), not the local stack. They reached production and only failed to write
   because production has no `role` column, so every role-aware query errored first. That was
   luck, not a safeguard. The file now pins itself to the local database read from `.env.test`
   and *refuses to run* if the resolved client URL is not localhost.

### Verified against the real local database
3. **`20261002_01000_broker_credentials_market_data_role.sql` applied locally**, PostgREST
   schema cache reloaded, and `tests/sql/prove_market_data_role.sql` confirms all five claims
   the migration rests on: both roles coexist for one user and broker, a row written without a
   role defaults to `execution`, a duplicate user+broker+role is refused by
   `broker_credentials_user_id_broker_role_key`, an invalid role is refused by
   `broker_credentials_role_check`, and each role is independently addressable.
4. **`tests/test_broker_market_data_role_db.py`** (6 tests) — the repository against a real
   migrated Postgres with a real tenant, rather than a stub. The gap it closes is that
   `async_safe_single` turns a missing column into `None`, so a stubbed test cannot tell a
   working query from a permission error. Each test creates its tenant by inserting into
   `auth.users`, whose trigger creates the `profiles` row, so nothing is shared with a real
   account.
   Proven by mutation: dropping the `role` column fails 6 with an actionable message;
   removing the execution fallback in `resolve_market_data_broker` fails 1.

### Applied to production
5. **Both migrations are now live.** `01000` and `02000` applied to the production Supabase,
   followed by `NOTIFY pgrst, 'reload schema'`. Verified afterwards:

   * `role` is `text NOT NULL DEFAULT 'execution'`, with zero NULL rows
   * `broker_credentials_user_id_broker_key` replaced by
     `broker_credentials_user_id_broker_role_key`; `broker_credentials_role_check` in place
   * `idx_broker_credentials_user_role_active` created
   * **17 credential rows before, 17 after.** All 17 backfilled to `execution`; the
     per-broker breakdown is byte-identical (zerodha 6, fyers 4, dhan 3, upstox 2, angelone 1,
     lemonn 1) and the 15 active rows are untouched. No tenant was re-pointed.
   * production PostgREST serves `role` (200, real rows) after the schema reload
   * `service_role` already had SELECT on 47 tables, so `02000` was a no-op there — which is
     the "applied by hand, never captured in a migration" diagnosis confirmed from the other
     side

6. **`scripts/verify_production_broker_roles.py`** (new, read-only) — runs the role-aware
   repository against live data for every real tenant. This is the check that "applied" alone
   does not provide: `async_safe_single` turns a permission error or a missing column into
   `None`, and `None` is what every caller already means by "broker not connected", so a
   clean `psql \d` and a passing `/health` coexist happily with a completely broken broker
   path. Result on production: all 12 tenants' execution reads return real rows, and no
   tenant resolves to "no broker" unless its only credential is inactive — which is the
   correct answer. It refuses to run if `SUPABASE_URL` is local, and calls only `get_*` and
   `resolve_market_data_broker`; `activate_broker` would change which broker a paying
   tenant's orders route through.

### Note for deployment
7. **The migration half of the ordering risk is now closed.** Both migrations are live, so
   deploying the code is no longer a schema race. What remains is the code deploy itself.

### Validation
- API suite **1198 passed, 1 xfailed**. `ruff check .` clean. Local database left with zero
  test rows and no leftover auth users.
## Unreleased — lint job green for the first time; an FXTM broker key that resolved to nothing

> The `Lint API` CI job had never passed — 0 green in 60 runs, since it was created on
> 2026-08-24. `main` was unprotected and nobody watches the Actions tab, so it stayed red
> for five weeks. Meanwhile a web build broken on `main` also went unreported for ten days,
> which is what a permanently-red job teaches: that red means nothing here.

### Fixed
1. **`_MT5_BROKER_CONFIG` keyed FXTM as `"fxTM"` while the registry offers `"fxtm"`**
   (`brokers/mt5_adapter.py`) — the lookup is `_MT5_BROKER_CONFIG.get(broker_key, {})`, so a
   mismatch raises nothing; it returns `{}` and every field falls back to its generic default.
   FXTM silently resolved to `"MT5 Server"` instead of `"FXTM Server"`. The key is now
   `fxtm`, and `tests/test_broker_mt5_config.py` (20 tests) asserts every key the MT5 connect
   form can produce resolves in the config, so the next broker added to the registry without
   one — or a case slip on either side — fails a test instead of returning a default.
2. **Duplicate `"fbs"` entry** in the same dict. Values were byte-identical, so there was no
   behavioural difference; the hazard was that it is exactly the shape of entry that makes
   someone later edit the copy that is not in effect.
3. **Documented what that dict actually does** — `display_name` and `description` are read by
   nobody, and its one live field, `mt5_server`, is a *required* credential that
   `authenticate` overwrites with the user's value. So the config contributes nothing to a
   live session today. Recorded in the module so nobody assumes a field is wired up.

### Changed
4. **`IllegalTransition` → `IllegalTransitionError`** (`strategy_runtime/state_machine.py`,
   exported from `strategy_runtime/__init__.py`) — satisfies the `N818` naming rule the repo
   configures. Four call sites; the v1.0.0 CHANGELOG entry is left as written, since it
   records what that release contained.
5. **`Capability` alias now uses the `type` statement** (`brokers/sdk/capabilities.py`) —
   lazily evaluated, so the forward reference to `CapabilityFlag` still resolves.
6. **Live-cert probes import `UnsupportedFeatureError` under its own name** rather than the
   `_USFE` alias (`brokers/sdk/live_cert.py`).

### Dev / CI
7. **`Lint API` passes.** The 43 findings were 23 `F811` re-imports of pytest fixtures and
   module flags (a documented idiom, now a `per-file-ignores` entry for `tests/*.py`), 4
   quoted type annotations, 1 duplicate dict key, 4 semicolon-joined statements, 2 aliased
   CamelCase imports and 2 naming rules. None was a behavioural defect; the duplicate dict
   key in item 2 above is the only one that could ever have become one.
8. **The ruff config in `pyproject.toml` was dead.** `apps/api/ruff.toml` takes precedence,
   and the two disagreed — `select` listed `I` while the effective config ignored `I001`, and
   `line-length` was 100 in one and 120 in the other. Editing the `pyproject.toml` section
   appeared to work and changed nothing, which is a likely reason the job was never fixed.
   The empty tables remain with a signpost explaining where the real settings live.
9. **New `Test Web Lib` CI job** runs the `apps/web/lib` assertions, and the `test:lib`
   script discovers `*.test.ts` with `find` instead of naming files, so a new test cannot be
   silently skipped by a script that was never updated.

### Known gaps (deliberately not fixed here)
10. **The `mypy` CI step has never run.** It is passed `market/runtime/engine/core/execution`,
    which does not exist — those are five sibling directories, not a nested path. The step
    errors immediately and `|| true` swallows it, so type checking has never once executed in
    this project. Pointed at the real paths it reports **181 errors across 48 files** (mostly
    `no-untyped-def`, with `disallow_untyped_defs = true`).
    Left alone on purpose: switching it on with 181 findings would create a second job that is
    red forever, which is the failure mode item 7 above exists to undo. It needs either 181
    annotations or an agreed baseline, and that is a standards decision rather than a side
    effect of a lint cleanup.
11. **`Load Test` has also never passed** — 0 green in 60 runs. The cause is infrastructure,
    not the code: `supabase start` pulls its image set anonymously and hits Docker Hub's
    rate limit (`toomanyrequests: Rate exceeded`), after which `supabase db reset` fails on
    `schema_migrations_pkey`. No load test has ever actually executed. Fixing it needs a
    Docker Hub credential in repository secrets.

### Validation
- API suite **1192 passed, 1 xfailed**. `ruff check .` clean (first time). Web build compiles.
- `mt5` config tests proven by mutation: `"fxtm"` → `"fxTM"` fails 4; re-adding the duplicate
  `"fbs"` fails 1.
- Zerodha import guard proven by mutation: removing the module-level `import httpx` fails 4.

## v1.8.0 (2026-08-24) — Google sign-in (Supabase GoTrue OAuth) — code live; provider activation pending dashboard config

> "Continue with Google" is now on the sign-in/sign-up pages end-to-end. The full code path ships and is deployed; flipping it live requires ONE manual step in the Supabase dashboard (Google provider credentials), which only the project owner can do.

### Added
1. **`POST /auth/google`** (`routes/v1_auth.py`) — exchanges a Supabase GoTrue OAuth session for the app's own session: verifies the GoTrue `access_token` against GoTrue `/auth/v1/user`, requires a `google` identity, finds-or-creates the profile row, mints cookie + JWT exactly like `/signin`, audits as `signin`.
2. **Frontend** — "Continue with Google" / "Sign up with Google" on `/auth` (redirects to GoTrue `/auth/v1/authorize?provider=google` with `redirect_to=/auth/callback`); new standalone `/auth/callback` page parses the fragment tokens, exchanges them, and routes admin→`/dashboard`, fresh non-admin→`/onboarding`, else→`/live`; friendly error state with back-to-sign-in link.

### Activation steps (owner, ~5 min)
1. Google Cloud Console → APIs & Services → Credentials → create **OAuth client ID** (Web application); Authorized redirect URI: `https://nwutlfuowiulfpbsrldn.supabase.co/auth/v1/callback`.
2. Supabase Dashboard → Authentication → Providers → **Google**: paste Client ID + Secret, enable, save.
3. Supabase Dashboard → Authentication → URL Configuration → add `https://ai.trademetrix.tech/auth/callback` to **Redirect URLs**.

### Validation
- API suite **1042 passed** (+5 in `test_auth_google.py`: exchange happy path, non-Google identity 400, invalid token 401, profile find-or-create both branches).
- Web `tsc` clean; BUILD_ID `3Ok2nMUsloeBLc9Mdb1LZ` served; button renders on prod `/auth`; endpoint registered (CSRF-guarded 403 on bare probe).
- Commit: `4bc4cc9`.

## v1.7.3 (2026-08-24) — Chart data 500s fixed app-wide + real-data contract restored in buyer backtests (PRODUCTION VERIFIED)

> A prod browser crawl (fresh user × 21 pages, console+network capture) found 43 issues with a single root cause: every chart widget fed the backend BARE index symbols (`NIFTY50-INDEX`, no exchange prefix), the Yahoo fallback gate silently rejected them, and the resulting `ValueError` escaped as raw ASGI 500s. Post-fix crawl: **0 issues**.

### Fixed
1. **Yahoo fallback gate rejected canonical symbols** (`market/historical.py`) — gate now evaluates the MAPPED symbol (via `_map_symbol` → `YAHOO_SYMBOL_MAP`), so bare index symbols resolve to real Yahoo tickers (`^NSEI` etc.) and charts keep working when the broker token is expired/unavailable.
2. **Unhandled 500 on `/marketdata/historical`** (`routes/v1_marketdata.py`) — data gaps now surface as a clean **400** ("No real market data available…"), unexpected failures as a logged **502**; no more ASGI tracebacks.
3. **Quotes had the same hole** (`providers/yahoo.py`) — bare `-INDEX` aliases added to `YAHOO_SYMBOL_MAP` (18 entries; `NIFTY50-INDEX` had also been missed by digit-less symbol regexes).
4. **Buyer backtests were still fabricating candles** (`application/services/buyer_strategy_service.py`) — `_generate_simulated_candles` fallback removed per the v1.7.0 real-data contract; data gaps raise ValueError → route 400.
5. **`/orders` dead URL** — now redirects to `/positions` (open orders render there).

### Validation
- API suite **1037 passed, 1 xfailed** (+21 regression tests in `test_chart_data_500_fix.py`; 2 stale tests updated to the new contracts).
- Prod deploy verified in-container: `NIFTY50-INDEX` / `NIFTYIT-INDEX` / `INDIAVIX-INDEX` 5m/1d → **200 with 75 real candles each** (was 500).
- Full browser crawl after deploy: **0 issues** across /live /trade /positions /portfolio /orders /funds /terminal /strategies /backtest /journal /alerts /risk /analytics /settings /account /brokers /marketdata /workspace.
- Commit: `86ce507`. Web BUILD_ID `FsW9ro2uKGwY5fxuIsG2Y`.

## v1.7.2 (2026-08-24) — Lemonn broker: connect-flow scaffold (API-pending, honest unsupported surface)

> Lemonn (lemonn.co.in — NU Investors Technologies, SEBI INZ000304837) publishes **no public trading API** today. Users can now pre-connect Lemonn through the normal brokers flow; every trading/data capability fails TYPED (`UnsupportedFeatureError` with an honest detail message) until Lemonn ships real endpoints — never silent fallbacks, never fabricated data.

### Added
1. **`LemonnAdapter` (`brokers/lemonn_adapter.py`)** — full `BaseBroker + BrokerAdapterBase` surface; credential validation on `authenticate` (ValueError when `client_code`/`secret_key` missing), typed `UnsupportedFeatureError` for all 10 trading/data methods, safe no-op disconnect. Capability matrix row is deliberately **EMPTY** (`brokers/sdk/capabilities.py`) so capability-gated paths fail closed.
2. **Connect flow** — registry metadata entry (`display_name "Lemonn"`, fields `client_code`+`secret_key`, instructions stating the API-pending status); `/brokers` page renders it dynamically; onboarding picker entry ("Lemonn (API pending)") + custom lemon logo in `broker-logos.tsx`.
3. **Registration plumbing** — `brokers/__init__.py` registration, execution-layer `_build_capabilities` name (all-false read model), conservative rate-limit entry (30/60s), `validate_production.py` import smoke. Cert suite picks the adapter up automatically (Level A interface cert passes).
4. **Migration `20260824_02000_broker_credentials_lemonn.sql`** — adds `lemonn` to the `broker_credentials.broker` CHECK constraint AND fixes a latent bug: `groww` was never in the constraint (saving Groww credentials would have failed with 23514). Applied to prod via psql (constraint verified).

### Validation
- API suite **1016 passed, 1 xfailed** (+21: `tests/test_broker_lemonn.py` covers registration, empty capabilities, connect-flow validation, every typed-unsupported method, health/capabilities contract).
- Web `tsc --noEmit` clean; prod build clean (BUILD_ID `C35wNJ5ki45512xgH5EX9` served == local).
- Prod deploy: migration applied (constraint now includes `groww`,`lemonn`); 6 API files hot-deployed, restart clean, `/health` 200; in-container check `lemonn registered: Lemonn | caps: 0 | fields: [client_code, secret_key]`; web `.next` deployed stop→cp→start→chown; `/brokers`, `/onboarding`, api health all 200 post-deploy.

### Activating live later
Implement the adapter methods against real endpoints and flip the `"lemonn"` capability row from `set()` to the earned flags **in the same change** — the tests in `test_broker_lemonn.py` assert both halves of that contract today.

## v1.7.1 (2026-08-12) — Builder template signals + kill-switch hardening + Angel One broker fixes (PRODUCTION VERIFIED)

> Three fix clusters: every builder strategy template now emits real signals on real candles (and the legacy backtest route returns the full result shape), the global kill switch can no longer fail open, and Angel One is a first-class data/order broker (scrip-master token resolution, batch FULL quotes, feed started with the user's ACTIVE broker).

### Fixed — Strategy Builder
1. **Templates emit real signals on real candles** (`1990a29`) — added the missing runtime compute functions (`source.candle`, `source.close_history`, `source.market_time`, `signal.breakout`, `time.day_of_week`, `time.time_range`, `constant.number`); `sma`/`ema` emit value+series ports, `macd` emits series_macd/series_signal (signal line = EMA of the MACD line), `cross_above`/`cross_below` use the wired series input; `logic.not` reads port `value`; VWAP falls back to a time-weighted average when volume is absent (Yahoo index candles carry none). Broken templates rewired: vwap deviation-band via constants, scalping via cross entries (dropped unimplemented `order.sl`/`order.target`), ICT via `smc.fvg` + time_range; `expiry_hunter` curated out of templates (needs `greek.iv`, unavailable in the single-instrument candle runtime).
2. **Redeploy gate fixed** (`56606e0`) — deploy set status to PAPER then rejected every redeploy (400 "Strategy is paper") because PAPER wasn't in the allowed statuses; `/deploy` now aligns with `/start`: PAPER and STOPPED strategies are redeployable.
3. **Legacy `/backtests/run` shape fixed** (`1990a29`) — returned the pre-BTResult payload (no `config`/`summary` keys) which crashed the backtest page client-side; it now routes through `backtest_manager.run` and returns the full `_result_payload`.

### Fixed — Risk
4. **Kill switch can't fail open** (`56606e0`) — comparisons in `risk/kill_switch.py`, `risk/rules.py`, `risk/riskguard.py` and the admin read used `val == "1"`, but `cache.get` json-decodes so a raw `redis-cli SET global:kill_switch 1` came back as int `1` and the gate failed OPEN. All comparisons are now `str(val) == "1"` so raw and `cache.set` writes both engage it. New tests: `test_builder_deploy_gate.py` (9), `test_kill_switch_hardening.py`.

### Fixed — Brokers / Market Data (Angel One)
5. **Index tokens resolve from the scrip master** (`5a14f4e`) — the Angel scrip master names indices `Nifty 50`/`Nifty Bank` while the app uses `NSE:NIFTY50-INDEX`; canonical pre-prefixed symbols built doubled keys (`NSE:NSE:...`) and never resolved → empty feed for every symbol. Segment prefix stripped before lookup, BSE honored for SENSEX, canonical index symbols aliased to scrip-master tokens.
6. **Quotes via batch FULL quote endpoint** (`d4f27c6`) — `order/v1/getLtpData` returns AB4033 "Invalid tradingsymbol" on this account so quotes silently fell back to Yahoo; switched to `market/v1/quote/` FULL (batched by exchange; gives OHLC + prev close) with rows mapped back to canonical symbols.
7. **Feed starts with the user's ACTIVE broker** (`35f7bc2`) — `start_market_feed` hardcoded `broker_type=fyers`, so Angel One users got the Yahoo fallback instead of live ticks; resolves the active broker like the quote route and passes stored secret/additional params into feed auth (Angel may fresh-login via TOTP when only a secret is stored → valid SmartAPI feedToken).
8. **Segment adoption + sector aliases** (`eefea34`, `b3ebaa3`) — token resolution adopts NFO/BSE/MCX from the symbol prefix (quote tokens grouped under NFO exchange); `INDEX_ALIASES` expanded to sector indices (IT, Pharma, Auto, etc.).

### Validation
- API suite **995 passed, 1 xfailed** (re-verified 2026-08-24 at `91654b1`).
- Prod deployment verified 2026-08-24: VPS git = origin/main = `91654b1`; all 11 changed API files md5-match inside `trademetrix_api`; containers healthy (uptime since the 08-12 restart).
- Health sweep 200: `/health`, `/live`, `/trade`, `/backtest`, `/sitemap.xml`. Kill switch `global:kill_switch` = `"1"` (ENABLED, untouched). Last-24h API logs: only pre-existing yfinance fetch noise (KNOWN_ISSUES #13), zero new errors.
- Commits: `1990a29`, `56606e0`, `5a14f4e`, `d4f27c6`, `b3ebaa3`, `eefea34`, `91654b1`.

## v1.7.0 (2026-08-08) — Backtest Engine: real 5-year windows + curated working strategy surface (PRODUCTION VERIFIED)

> Backtest engine honesty pass: the backtest surface now contains ONLY strategies that emit real trade signals from candles, the window ceiling is raised from 60 days to 5 years with correct provider period handling, and backtests can never silently run on fabricated (synthetic) candles again.

### What was done
1. **Curated backtest surface** — `/api/v1/backtests/strategies` now returns only candle-working strategies (`trend_rider`, `macd_cross`, `bollinger_bandit`, `rsi_mean_reversion`, `orb_pro`, `smc_sniper`, `intraday_momentum`, `mean_reversion_pro`, `breakout_scanner`, `arbitrage_hunter`) plus a `catalog` of their metadata. Tick-dependent (`vwap_band`, `gap_up_express`) and live-option-LTP/leg-selling strategies (`long_straddle`, `trend_rider_buyer`, `momentum_breakout_buyer`, `expiry_hunter`, `option_wheel`) stay registered for the live trader runtimes but are curated OUT of backtests (their `on_candle` can never generate a fillable trade). UI drop-down rebuilt to the same 10.
2. **60 days → 5 years** — default backtest window raised 60d → 365d, cap 1825d (daily; intraday capped 730d with a clear 400 otherwise). All run routes (`/run`, `/run-v2`, `/run-v3`, `/optimize`, `POST /`, `/candles`) validate the window; UI `Days` input `max=730` → `max=1825` with label "Days (up to 5y daily)".
3. **Real data only — synthetic fallback removed** — `engine/backtest.fetch_historical_data` no longer falls back to `_synthesize_candles()` fabricated candles; it raises a clear `ValueError` ("backtests never run on fabricated candles") that the routes surface as a 400. Verified the durable store path (Supabase → broker → Yahoo) is entirely real-data.
4. **Yahoo period mapping fix** — `market/historical.py` maps windows to yfinance period tokens (`1mo`…`10y`) instead of a raw `"{N}d"` string that yfinance rejects past ~60d (the old ceiling). Backtest durable store already keyed by date-range/cache, so long windows fill from the accumulated Supabase store then gap-fill.

### Validation
- API suite **982 passed, 1 xfailed** (2 tests updated: legacy fetch now asserts the real-data error; Yahoo period token assertion updated).
- Web `tsc --noEmit` 0 err; prod build clean (BUILD_ID `pxW63XXu953F8XA3qWM00` served).
- Prod in-container: `NIFTY` 1d loads **1235 real candles** (2021-08-09 → 2026-08-07); v2 `macd_cross` backtest on the full 5y window: **63 trades, win rate 36.5%, net P&L ₹+208,779** on ₹10L (candles_analyzed 1235); legacy engine run over the same real window executes with the real loader; in-container smoke also confirms legacy routes run with real data only.
- Health sweep: `api/health`, `/backtest`, `/strategies`, `/live`, `/trade`, `/positions`, `/sitemap.xml` all 200. Kill switch `global:kill_switch` = `1` untouched (this was a read/backtest-only change).
- Commit: `edfff84` (8 files, +118/−33). Deployed: 5 API files hot-deployed (md5-verified) + web `.next`.

## v1.7.0-beta.1 (2026-08-07) — Trader Workspace: full Indian index options trading workflow (PRODUCTION VERIFIED)

> Trader-centric sprint: users can pick any of the five supported index families, position an ATM/ITM/OTM strike chain, choose CE/PE, size by lots, and drive buy + the five position actions against their paper or live broker — all through the existing OMS/engine endpoints. Backend was touched ONLY for `MIDCPNIFTY` constants; no new REST contracts.

### What was done
1. **`/trade` trader workspace** — 5 index chips (NIFTY/BANKNIFTY/FINNIFTY/MIDCPNIFTY/SENSEX), ATM anchoring with moneyness steps (ATM/ATM±1=ITM/OTM, ATM±2), CE/PE toggle, strike interval grid, lots multiplier (1–4 → qty = lots × lot_size), and margin estimate — all composable from the existing `api.marketdata`/`api.engine` clients plus new helpers (`options-contracts.ts`, `strategy-labels.ts`, `trader-presets.ts`).
2. **Option-chain workflow** — chain rows never auto-order; the BUY card is an explicit side-action with confirm that places exactly one engine trade (paper or live); row clicks are pure selection. New `components/trade/*` (index-strip, chain-panel, order-card, presets-bar, fills-ticker) + `components/positions/position-actions.tsx`.
3. **Position actions** — `Exit`, `Partial Exit`, `Add`, `Reverse`, `Trail SL`, `Modify` on `/positions`, wired to `engine.modifyOrder` (paper+live) and engine trades; Trail SL currently re-issues via `modifyOrder` with `result.broker_order_id` (raw live-order SL-M fallback is a noted next-sprint hardening).
4. **MIDCPNIFTY support** — `market/option_chain.py` + `routes/v1_marketdata.py` gain MIDCPNIFTY `STRIKE_INTERVALS=25` / `LOT_SIZES=75`; prod `/marketdata/option-chain` MIDCPNIFTY returns 200/19 strikes (parity with NIFTY). MD5-verified hot-deploy.
5. **Route polish** — `/strategies`, `/backtest`, `/terminal/option-chain` rebuilt against the trader flows; `app/sitemap.ts` restored (was VPS-only / missing from deploys) so public pages are crawleable.

### Validation
- API suite **982 passed, 1 xfailed** (option-chain/midcp constant tests incl.). Web `tsc --noEmit` 0 err, `next lint` 0 new, prod build clean; BUILD_ID `skiffJrBrpDasaPxRGY-` served.
- **Prod browser e2e 36/36** (puppeteer, fresh user, mocked chain/positions/engine + `.margin-intercept`): 5 index chips click-active; moneyness 5/5 + CE/PE; lots `+3 → 4×50=200`; margin ₹53,000; 0 orders from selection; qty-deliberate BUY = exactly 1 order; 5 position actions reachable with Partial Exit + Modify exercised through engine endpoints; no unexpected console/response errors.
- Post-deploy health: `api`, `/live`, `/trade`, `/strategies`, `/backtest`, `/sitemap.xml` all 200; prod logs free of new errors.
- Commits: `8896b17` (feature, 18 files +1914/−597), `36ce84c` (sitemap restore + `*.bak` ignore), `0eb92d1` (analyzer retirement). Tag `v1.7.0-beta.1` @ `8896b17`.

### Ops — legacy analyzer retired
- Pre-monorepo `analyzer/` stack (own backend + Next.js/Capacitor dashboard, 0 Caddy routes, UFW-blocked) STOPPED, archived to `/root/trademetrix-backups/analyzer-2026-08-07/` on the VPS (257,951 bytes, 203 entries, manifest verified), containers + project network removed, source tree deleted, `analyzer/` gitignored. Features superseded by `apps/api` + `apps/web`; recovery = restore tar + `docker compose -f analyzer/docker-compose.yml up -d --build`.

## v1.6.9 (2026-08-07) — Stability Sprint: verified P1/P2 fixes from the Product Acceptance Audit

### Fixed
1. **P1-1 Option chain 503 on index symbols** — `normalize_index_symbol()` (strips `NSE:`/`BSE:`/`NFO:`, maps `NIFTY50-INDEX`/`NIFTYBANK-INDEX`/`FINNIFTY-INDEX`/`SENSEX-INDEX` aliases) in `market/option_chain.py`; dead-code Fyers success block dedented (real chains now parse); shared `_generate_simulated_chain()` fallback (mock-flagged, `is_simulated`) replaces the buggy route-local mock so supported index families always return a chain, never 503.
2. **P1-2 AI Journal CORS-blocked 500** — migration `20260807_01900_trades_schema_align.sql` aligns the schema-drifted prod `trades` table; `_get_recent_trades` now reads `orders` (FILLED) first with `trades` fallback, never 500s on schema drift; `get_journal` degrades gracefully; global 500 handler now attaches CORS headers since ServerErrorMiddleware sits outside CORSMiddleware.
3. **P1-3 Three admin tabs broken (404 HTML)** — new `GET /admin/users/with-brokers` + `GET|POST /admin/ip-whitelist` + `DELETE /admin/ip-whitelist/{ip_id}` (super-admin gated, existing `AdminService` methods); Trade Router / Trades / IP Whitelist tabs now use the typed `api` client (`API_BASE`) instead of relative fetches.
4. **P2-1 Login throttle/lockout** — per-email+IP progressive delay then `429` after 5 failures/5 min (`core.cache`-backed, `X-Forwarded-For` aware, audit `auth_failed`/`login_locked`); success path never degraded, fail-open when Redis is down.
5. **Audit rows for unauthenticated events dropped (found in prod verification)** — `audit_log.user_id` was `UUID NOT NULL REFERENCES profiles(id)`, so throttle events (no actor) sent `user_id=""` → PostgREST `22P02` → row silently discarded. Migration `20260807_01910_audit_log_user_id_nullable.sql` drops NOT NULL (FK stays, NULL bypasses the reference); `core.audit._do_insert` coerces empty `user_id` → `None`. Verified on prod: `auth_failed` (attempts 2–5) + `login_locked` (attempts 6) rows now persist with `user_id=NULL`.

### Validation
- Full API suite **981 passed, 1 xfailed** (baseline 963/1; +18 new tests: option-chain normalize 7, journal resilience 5, auth throttle 4, audit null-user 2).
- Web `tsc --noEmit` 0 err; `next lint` 0 new; `next build` clean (BUILD_ID `QiL_h7JpOgCdxeeLs4DV6`).
- Reports: `reports/Stability-Fixes-v1.6.9-{Root-Cause,Files-Changed,Regression,Security}.md`.

## v1.6.8 (2026-08-07) — Live Dashboard: unified `/live` operational cockpit + landing wiring (PRODUCTION VERIFIED)

> Additive frontend feature ONLY — `apps/api` untouched this release (Phase A signal payload was shipped earlier under the v1.6.7 line). No new REST endpoints: the dashboard composes existing OMS/Engine/Paper/Runtime/Marketdata services. No redirects were removed for any existing page.

### What was done
1. **New route `/live` (`apps/web/app/live/page.tsx`)** — three-column cockpit: header (logo→`/live`, LIVE badge, Market OPEN/CLOSED chip, Stream SSE chip, Online chip, Workspace link, user name); left segmented Positions | Orders | Portfolio (live+paper positions with quote-driven change%, engine orders with cancel, portfolio summary incl. engine margins); center symbol chips (indices + your open positions) + `Chart` + Quick Trade; right rail Trading Controls (Emergency Stop w/ confirm dialog, Pause All, collapsible runtime diagnostics) + Live Signals (SignalGenerated SSE feed with filters + runtime seeds). Every widget renders Loading/Empty/Offline/Broker-disconnected/Market-closed via the shared `widget-frame`.
2. **Shared `apps/web/components/live/` (13 files)** — types, use-live-connection, use-live-data, widget-frame, table, market-overview, positions-panel, orders-panel, use-live-feed, signal-card, live-signals, trading-controls. Built entirely on the existing design system + W6 primitives (KpiCard, SkeletonBar, Dialog, Badge/Dot/Chip) — no new CSS.
3. **Landing wiring** — landing page CTAs/nav/footer → `/live`; app-layout Home section → single "Live Dashboard"; logo pixel + admin-route non-admin bounce → `/live`; sign-in + onboarding (CTA + completed-guard) → `/live` for non-admins, `/dashboard` for admins. Portfolio/Workspace/Backtest/etc. remain directly accessible.
4. **Validation** — web `tsc --noEmit` 0 errors, `next lint` 0 new errors, `npm run build` clean (`.env.production` swap + restore); backend suite **963 passed, 1 xfailed** (unchanged by this release).
5. **Deployment** — web hot-deploy (BUILD_ID `YCwC6U2jJMRugxdXVPcI1`); health 200, `/live` + `/` + `/portfolio` 200 public + in-container; **browser smoke on prod 13/13** (fresh users via GoTrue; anonymous → gate, signup → onboarding → CTA → `/live`, login → `/live`, widgets render, logo → `/live`, no page errors); smoke users swept; Redis `global:kill_switch` untouched (ENABLED, 1, TTL -1).

> Monitoring after deploy: none of the dashboard/resource states reported. See AGENTS.md session entry for the reference notes on `/live` composition and the CSS-uppercase smoke gotcha.

## v1.6.7 (2026-08-06) — Sprint-3 W6: shared UI primitives — KpiCard/Badge/Skeleton/Dialog consolidation (PRODUCTION VERIFIED)
> No API, routing, or state changes. No visual redesign. Sprint 4 explicitly NOT started.

### What was done
1. **`apps/web/components/ui/` shared primitives** — `kpi-card.tsx` (`KpiCard` stat/metric/beta),
   `badge.tsx` (`Badge`/`Dot`/`Chip`/`OrderStatusBadge`/`InstrumentTypeBadge`/`TierBadge` via
   `BadgeVariant`, colors → token-backed `t-badge`/`t-dot`/`t-chip` classes), `skeleton.tsx`
   (`SkeletonBar` + `PageLoadingSkeleton`; re-exported via `components/skeleton.tsx`),
   `dialog.tsx` (`Dialog` — single source replacing 7 inline `t-modal` sites).
2. **Consolidation** — KPI cards (backtest/admin-beta/strategies/[key]/dashboard pnl), skeletons
   (3 `loading.tsx` + 5 page panels), dialogs (settings/account/brokers/strategies/marketdata/
   terminal-builder/alert-modal/deploy-wizard), badge sets (dashboard admin-content, catalog,
   builder, watchlist) all delegate to the shared primitives; legacy shims in `components/`
   (`empty-state.tsx`, `skeleton.tsx`) keep old import paths working.
3. **Deploy** — web consolidated via production deploy flow (`infra/production/deploy.sh`),
   `origin/main` at `a0e5b8a`; API + web health 200. Post-deploy: 12 public routes 200,
   visible-text parity 12/12 (only webpack chunk-order noise in raw HTML), BUILD_ID `znbojLqT0xaMuNozJJ5dw` served.
4. **Reports** — `reports/` (`Consolidation-Sprint-3.md`, `W6--Detailed.md`,
   `W6-Visual-Verification.md`, `W6-Validation.md`, `W6-UI.md`).

> Internal consolidation only — no routes, endpoints, response formats, serializers or dead-code
> changes (nothing deleted; legacy `v1_portfolio` router tagged INACTIVE, not removed). **SPRINT 2
> PRODUCTION VERIFIED** (2026-08-06).

### What was done
1. **One canonical reader** — new `application/services/position_service.py` (`PositionService`)
   owns every position read: `get_positions_with_broker` (portfolio), `get_user_positions` /
   `get_user_positions_list` (engine — PAPER-run branch via portfolio_manager, else live engine),
   `get_paper_positions` (open-only), `list_all_positions` (admin snapshot + profiles join).
   Each consumer router became a thin adapter; the four historical envelopes are preserved
   byte-for-byte.
2. **Routes rewired** — `v1_engine.py` `/positions`, `v1_paper.py` `/positions`,
   `v1_admin.py` `/admin/positions`, `v1_portfolio.py` `/api/v1/positions` all delegate to
   `PositionService`; the v1_portfolio router is tagged **INACTIVE** (holdings/funds/summary
   still use `portfolio_manager` directly).
3. **Public service contracts kept** — `EngineService.get_positions` (same semantics incl.
   `BrokerTokenExpiredError` propagation + transient-error → `[]`) and `AdminService.
   list_positions` (same dict contract) now delegate to the canonical service; new public
   `EngineService.get_engine_for` accessor reuses the shared engine cache.
4. **Parity tests** — new `tests/test_position_service_parity.py` (11 tests: envelope + path
   parity for all four consumers + service delegation equality); `TestGetPositions` in
   `test_engine_service.py` updated to the delegation contract.

### Verification
- API regression **955 passed, 1 xfailed** (v1.6.5 944/1 → +11, zero failures); imports clean.
- **Production gate PASSED (user-approved)** — 7 files hot-deployed (`position_service.py`,
  `engine_service.py`, `admin_service.py`, `routes/v1_{admin,engine,paper,portfolio}.py`),
  md5-verified in-container, restart clean, health 200.
  - **Byte-parity**: BEFORE/AFTER capture of 12 endpoints (live, paper, admin, funds,
    holdings, engine status) — every status identical; response key-trees identical; only
    allowed diff = `positions[].updated_at` wall-clock refresh. Expired-token admin keeps
    its documented `401 BROKER_TOKEN_EXPIRED`; live admin keeps 2 real positions.
  - **Paper lifecycle (real HTTP path) 6/6**: BUY 5 `NSE:NIFTY50-INDEX` paper → filled
    @ 24653.27 (≈2.2–2.5 s) → position visible → portfolio open=1 → trade recorded →
    SELL 5 → position closed → realised −98.8, equity 500000 → 499901.2.
  - **Monitoring**: 0 Prometheus alerts, api memory 288 MiB stable, 0× 5xx, error log =
    pre-existing yfinance 404 noise only.
  - **Kill switch**: Redis `global:kill_switch` was ENABLED pre-gate (product-wide halt);
    cleared for the paper demo on user approval, then **re-enabled** (prod restored).
  - Report: `07_sprint2_w2_production_verification.md`. Next: Sprint 3 (W6) on approval.

## v1.6.5 (2026-08-06) — Canonical backtest metrics: ONE Sharpe + ONE cost model (Consolidation Sprint 1 / W1)

> Internal consolidation only — no routes, endpoints, response formats, UI or dead-code
> changes (consolidation-sprint constraint: nothing deleted). Deployment = 4 files hot-deployed
> to prod (md5-verified) + restart; PRODUCTION VERIFIED.

### What was done
1. **B1 fixed — one canonical Sharpe across every backtest path.** New
   `backtest.performance.compute_sharpe_ratio(returns)` (sample stdev `n−1`, annualized
   `√252`, `<2` returns → `0.0`). `PerformanceAnalytics` now calls it; the **legacy `/run`
   engine** (`engine/backtest.py`) previously used population stdev over per-trade PnL —
   a unit-mismatched ratio diverging from run-v2/v3 — and now computes
   `compute_sharpe_ratio` over the same equity-curve period returns as run-v2/v3. Removed the
   now-unused per-trade `_returns` list (internal, not an API).
- **B2 fixed — one canonical fee implementation.** Legacy `/run` cost math was a flat
   4-component approximation (slippage+brokerage%+STT%+exchange%) that never matched the
   segment-aware `estimate_cost` model run-v2/v3 use. `BacktestEngine._apply_costs` now routes
   through canonical `estimate_round_trip` (`EQUITY_INTRADAY`, `commission_min=0.0`,
   legacy knobs → `BacktestCostConfig` overrides). Same trade → identical fees on `/run`,
   run-v2 and run-v3 (includes stamp-duty/GST/SEBI the flat math omitted). `paper/fill_engine`
   `_build_fill` also routes through `estimate_cost` with `gst_enabled=False,
   sebi_fees_enabled=False` to keep paper fills **byte-identical** to their historical math.
3. **New parity suite `tests/test_backtest_consolidation.py` (10 tests)** — legacy-Sharpe ==
   `compute_sharpe_ratio` == `PerformanceAnalytics`, sample-vs-population guard, `<2` → `0.0`,
   legacy cost == `estimate_round_trip`, stamp-duty leg placement, paper-fill parity.

### Verification
- API regression **944 passed, 1 xfailed** (baseline 934/1 → +10, zero failures).
- **Prod deploy + smoke (in-container, real auth) — 13/13 PASS:** `POST /backtests/run` 200,
  payload keys unchanged, equals `POST /backtests/` exactly (sharpe/trades/pnl identical);
  `run-v2` 200 (sharpe −4.2, 38 trades); `GET /{run_id}` fee parity **38/38**
  (`cost_total == slippage+charges+taxes`, e.g. 2282.58 = 0.0+1150.55+1132.03); JSON export
  200; paper fills byte-identical for zero-fee and fee-bearing configs. Logs clean (0
  non-baseline errors, 0 5xx in 15min; only pre-existing marketdata 503s/Yahoo noise).

## v1.6.4 (2026-08-06) — Housekeeping: dead admin endpoint fixed, lint wired, log noise swept

> Health-check pass (tests/tsc/lint/prod probes). No features — aligns with the freeze.

### Fixed
- **`GET /api/v1/admin/strategies/all-user`** — the admin "User Strategies" tab always showed
  "No user strategies found" because the route was never registered (KNOWN_ISSUES #15).
  The existing `AdminService.list_all_user_strategies` now maps rows for the UI
  (`type` from `strategy_type`, `is_active` from `status`), and the route is registered with
  `require_admin` + optional `?user_id=` filter. 3 new tests.
- **`apps/api/core/cache.py`** — replaced deprecated `setex()` with `set(..., ex=ttl)`.
- **`apps/api/brokers/sdk/certification.py`** — `health()` probe no longer creates a discarded
  coroutine (`asyncio.iscoroutine(adapter.health())` → `inspect.iscoroutinefunction`).
- **`apps/api/tests/test_squareoff_service.py`** — scheduler tests close the discarded
  `_squareoff_loop` coroutine (kills the "never awaited" RuntimeWarning).
- **ESLint wired** — `apps/web/.eslintrc.json` (`next/core-web-vitals`) + `eslint@8` +
  `eslint-config-next@14.1.0`; `next lint` now runs non-interactively. Fixed the 17
  `react/no-unescaped-entities` errors (straight quotes → typographic) across
  `ai/page.tsx`, `dashboard/admin-content.tsx`, `onboarding/page.tsx`, `portal/page.tsx`,
  `portfolio/page.tsx`. 35 pre-existing `react-hooks/exhaustive-deps` warnings left as-is
  (deliberate omissions; not fixing to avoid behavior changes).
- **Docs** — INCIDENTS.md: INC-007 (watchlist, now in Workspace), INC-009 (MARKET price
  validation, conditional since v1.5.9), INC-010 (no duplicate content-types — verified on
  the live schema) marked Resolved with evidence. KNOWN_ISSUES #15 marked Resolved.

### Verification
- API regression **934 passed, 1 xfailed** (+4 tests; warnings 76 → 9, remaining are
  background-poll task teardown artifacts in HTTP-flow tests, not production code).
- Web `tsc --noEmit` clean; `next lint` 0 errors (35 warnings).
- `git push` of the previously-unpushed v1.6.1–v1.6.3 commits (local was 4 ahead of
  `origin/main` — a future VPS `git reset --hard origin/main` would have dropped them).

## v1.6.3 (2026-08-05) — Beta analytics: `is_auth` split so DAU/bounce/funnel are trustworthy (v1.6.2 follow-up)

> Evidence-backed (W32 reports 06/07/08/10 — DAU/bounce/cohort numbers were inflated by
> anonymous sessions and smoke traffic). Small, additive; no features.

### Changed
- **`apps/web/lib/analytics.ts`** — `is_auth` injected into EVERY queued event at flush time
  (client auth state resolved via `useAuth`), so `session.start` / `page.view` / clicks all
  carry it; unknown until auth resolves (then server truth wins anyway).
- **`apps/web/components/analytics-tracker.tsx`** — now reads `useAuth()` and syncs
  `setAnalyticsAuthState`; mounted INSIDE `Providers` (`app/layout.tsx`) so the context is
  available (was rendered outside).
- **`apps/api/routes/v1_analytics.py`** — `track-batch` resolves identity via proper FastAPI
  DI (`Depends(get_optional_user)` — previously called manually with `credentials=None`, so
  only the cookie branch ever ran) and sets `properties.is_auth = bool(user_id)` server-side
  as the authoritative value.

### Verification
- Regression **930 passed, 1 xfailed** (3 new route-level tests: signed-in true, anonymous
  false, non-dict properties untouched). Web tsc + prod build clean.
- Prod wire probe (in-container, real HTTPS): anonymous batch → `is_auth=false` + no
  user_id; signed-in batch (`fa668109`) → `is_auth=true` + user_id persisted. Confirmed in
  `analytics_events`. API redeployed (health 200), web `.next` deployed (BUILD_ID
  `dyvmbDSGyGqOqcTjXxdgV`), probe rows/files cleaned.

## v1.6.2 (2026-08-05) — BETA LAUNCH SUPPORT W32: weekly intelligence cycle + risk-audit persistence (ops-only)

> Beta Launch Support week 1: evidence collection cycle established. Full W32 evidence
> suite authored in `docs/weekly/2026-W32/` (01-product-health → 13-next-week-priorities)
> from live Supabase analytics, Prometheus and container logs.

### Ops fixes shipped (evidence-backed, feature freeze respected)
- **`risk_audit_log` migration applied to prod** — `20260804_01600_risk_audit_log.sql`
  (`CREATE TABLE IF NOT EXISTS` + index) executed on remote Supabase; PostgREST schema
  reloaded (`NOTIFY pgrst, 'reload schema'`); `rest/v1/risk_audit_log` returns 200. Closes
  KNOWN_ISSUES #14 [Action required]: emergency-stop audit writes no longer hit PGRST205
  and no longer fall back to `audit_log`. Zero code changes (DDL only).
- **Feedback store cleaned** — the 9 `E2E prod-readiness test — please ignore` rows (all
  `prtest*` users, 2026-08-02) marked `wontfix` + notes via PostgREST PATCH, so the W33
  feedback dashboard counts only real user reports.
- **Known issue triage** — KNOWN_ISSUES #14 resolved; #1 (token cycle) mitigated by the
  auto-refresh cron + INC-016; INC-015/016/017 closed (already shipped `fd896ca`).

### Evidence findings (see docs/weekly/2026-W32/)
- Backtest runs 2 → 38 (5 users), builder strategies 7 → 20, accounts 26 → 31; requests
  50,390 → 101,600 with p95 latency *improving* (API 0.249s).
- 0 container restarts; fyers breaker 2 → 0 OPEN; client errors 20 → 0 since the 08-03
  chart color-parse fix (verified in current build).
- Top open items: broker-step activation (13% connect), `/alerts/` poller 429s (610/7d),
  `async_safe_single` None log noise (653×/48h), `strategy_runs` 22P02 schema debt.

### Verification
- Migration: table + 6 columns present, PostgREST 200 on the table, `NOTIFY` sent.
- Feedback: 9 rows returned `wontfix` with notes from the PATCH response.
- No API/web code changed; health 200 (no redeploy required).

## v1.6.1 (2026-08-05) — BACKTEST ENGINE PHASE D: Trade Intelligence (interactive trade learning)
> Phase D of the institutional backtest roadmap (A/B/C/D). **Transforms every completed
> trade in `apps/web/app/backtest/page.tsx` into an interactive learning object** — click
> any trade (trades table row or the Overview equity-curve E/X marker) and a **Trade
> Intelligence** panel opens: a real candlestick price chart (candles from the same durable
> store the backtest used via `GET /backtests/candles/{symbol}/{interval}?days=`) with
> **Entry/Exit markers** and **SL/Target price lines**, a crosshair tooltip (PnL, RR, risk
> amount, signal reasons, charges/taxes/slippage/cost, risk state incl. drawdown at entry
> and capital remaining), **Replay from entry candle** (client-side step-through starting
> exactly at the entry candle), and **Prev Trade / Next Trade / Jump to Max Drawdown /
> Jump to Best / Jump to Worst**.
>
> **Constraints honoured** — visualization only: analytics and execution engine untouched
> (backend **zero** diffs), no duplicate calculations (SL is a display-level inverse of the
> persisted `risk_amount = |entry − stop| × qty`; target is honoured only when the trade
> exited via a target/LIMIT fill — `exit_reason`), all other values read straight from the
> existing run payload. Data limits surfaced honestly in the UI: SL line appears only when a
> resting stop existed (`risk_amount > 0`); per-candle indicator snapshots are not persisted
> so the signal context is shown via entry/exit reasons.

### Added
- **`apps/web/app/backtest/page.tsx`** — `TradeChart` (lightweight-charts v5:
  `CandlestickSeries` price chart, `createSeriesMarkers` entry/exit markers + animated
  replay cursor, `createPriceLine` dash lines for SL/Target, crosshair tooltip, viewport
  auto-centred on the entry candle, ResizeObserver); clickable trade rows (highlight) +
  toolbar (Prev/Next/Max Drawdown/Best/Worst); `Trade Intelligence` panel (12 detail cards
  + signals card + chart + replay control); `BacktestChart` gained trade-click → trades tab;
  `BTTrade` extended with the already-shipped enriched fields; `BTCandle`/`TradeView` types;
  `candleTime`/`nearestCandleIdx` helpers. Candles fetched once per run with the run's
  `config.days` window (`api.backtest.candles`), cached across trade selections.

### Changed
- **`apps/web/app/backtest/page.tsx`** — trades table adds RR column + selected-row
  highlight; Overview equity chart markers are clickable ("Click an E/X marker to inspect
  that trade").

### Verification
- Web `tsc --noEmit` clean; prod build clean (BUILD_ID `iia71_nq1kK2DYPZhdi9P`).
- Full API regression (backend untouched): **915 passed, 1 xfailed**.
- Deployed (`.next` swap into `trademetrix_web`, stopped-container `docker cp`, `chown -R
  1001`); `✓ Ready`, `/backtest` 200 in-container + public, new page chunk served.
- Prod smoke (puppeteer, fresh user, `p0e2e/e2e-trade-intel.js`): **12/12 OK** — run
  renders → Trades tab → click row 0 opens Trade Intelligence 1/3 with real candles →
  SL price line derived → detail cards (charges/RR/signals) → crosshair tooltip shows
  P&L/RR/charges/risk → Replay toggles and steps from the entry candle → Best→3/3,
  Worst→2/3, Max Drawdown→2/3, Next→3/3 → zero console/page errors. Smoke users swept.

## v1.6.0 (2026-08-05) — BACKTEST ENGINE PHASE C: risk-aware backtest reports (risk analytics in the UI)

> Phase C of the institutional backtest roadmap (A/B/C). **Surfaces Phase B's
> `risk_analytics` in the Backtest Engine report UI** — a new **Risk** tab (visible only
> when `risk_enabled=true`) shows why the simulation rejected orders and how capital/
> exposure/drawdown evolved, so a rejected run is diagnosable at a glance. Risk-off runs
> render byte-identical (tab hidden). No OMS / Broker Layer / Execution Engine changes.
>
> Wire budget: the persisted `BacktestResult.risk_analytics` stays exact (full timeline,
> curves, per-order rejections), but the payload/`GET /{run_id}` surface now budgets it the
> same way trades and the equity curve are budgeted — timeline/capital/exposure curves
> LTTB-downsampled to 2000 points (first/last preserved), per-order rejections capped at
> 200 with a `rejections_truncated` flag. `RiskAnalytics.rejections` (additive, persisted)
> carries the full per-order rejection records (rule, reason, capital/risk remaining,
> drawdown, exposure, timestamp/symbol/side/qty/price).

### Added
- **`apps/web/app/backtest/page.tsx`** — `RiskChart` (lightweight-charts: capital-remaining
  line, exposure area, drawdown% line, crosshair tooltip) + **Risk tab**: KPI cards
  (accepted / rejected / circuit halts / rules fired), "Rejections by Rule" bar chart,
  "Risk State Over Time" chart, and a **Rejected Orders** table (time, symbol, side, qty,
  price, rule chip, reason, capital remaining, risk remaining (`∞` when unlimited),
  drawdown%, exposure) with truncation notice; `BTRiskAnalytics` types; conditional tab.
- **`apps/api/routes/v1_backtest.py`** — `_payload_risk()` (LTTB downsample of
  timeline/capital_curve/exposure_curve at `PAYLOAD_MAX_RISK_POINTS=2000`, rejection cap
  `PAYLOAD_MAX_REJECTIONS=200` + `rejections_truncated`) applied to run-v3 `_result_payload`
  and `GET /{run_id}` (risk-off passthrough unchanged).
- **`apps/api/backtest/models.py`** — `RiskAnalytics.rejections: list[RiskRejection]`
  (additive, persisted in `backtest_runs.summary`; old rows default empty).

### Changed
- **`apps/api/backtest/risk.py`** — `analytics()` now includes `rejections=list(self._rejected)`
  (was only counts/reasons/curves).

### Verification
- **7 new tests** (`tests/test_backtest_risk_payload.py`): curve downsample >2000 (first/
  last preserved, monotonic), passthrough below threshold, risk-off passthrough, rejection
  cap + flag, enabled wire shape, route-level `GET /{run_id}` budget + risk-off passthrough.
- Full suite **915 passed, 1 xfailed** (908 baseline + 7). Web `tsc` clean, prod build
  clean (BUILD_ID `q-Eff63YJmQe0dbJva2B6`).
- Prod smoke **25/25** (user fa668109, ema_crossover, NIFTY 5m/60d = 3101 candles): risk OFF
  212 trades; risk ON `max_trades_per_day=3` → 3 trades, accepted 6, **418 rejections** all
  `MAX_TRADES_PER_DAY` ("Trade count 3 exceeds daily limit 3."), halts 0; 3101-point curves
  downsampled to exactly **2000** (first index 0 / last 3101 preserved); rejections capped
  418→**200** with `rejections_truncated=True`; full payload fields incl. `risk_remaining
  -1.0` NO_LIMIT sentinel; `GET /{run_id}` persisted with the same budgeted shape.

## v1.5.11 (2026-08-05) — BACKTEST ENGINE PHASE B: simulated risk engine (risk_enabled=true fixed)

> Phase B of the institutional backtest roadmap (A/B/C). **Fixes the
> `risk_enabled=true → 0 trades` incident**: backtest orders were being evaluated by the
> LIVE Risk Engine dry-run, which read live state (Supabase orders queries, Redis kill
> switch, market status) for a `backtest:<hex>` pseudo-user — fail-closed defaults
> (`kill_switch_enabled=True`) rejected every order. Backtests now run a **simulated risk
> engine** (`backtest/risk.py`) that reuses the shared Risk Engine vocabulary
> (`RiskConfig` extended, `RiskDecision`, `RiskRuleType`) but evaluates orders against the
> SIMULATED account only (BacktestBroker equity/cash/positions/realized P&L). No live
> broker/OMS/DB/market-state access.
>
> Simulated rules (mirroring live semantics): position sizing (`max_risk_per_trade_pct`
> clamps opening quantity), max capital, max exposure, max symbol exposure, max open
> positions, max quantity, max trades/day, daily loss limit, daily profit target (warning),
> max drawdown, circuit breaker (halts remaining orders after a daily-loss/drawdown
> breach — simulated kill switch), kill switch + emergency stop config flags.
> Deliberately NOT simulated: broker auth, market-open validation, trading window, live
> margin API, broker connectivity, OMS queue state, duplicate/cooldown/rate rules.
>
> Every rejected order carries: reason, rule triggered, capital remaining, risk remaining,
> drawdown, exposure. `BacktestResult.risk_analytics` (additive) exposes accepted/rejected
> trades, rejection reasons, halt count, risk timeline, capital curve, exposure curve.
> Configurable via new `BacktestConfig.risk` dict; capital-derived institutional defaults
> (10% daily loss, 25% drawdown, 5× exposure, 10 open positions) guarantee risk ON never
> zeroes a healthy run. Constraint honored: OMS / Broker Layer / Execution Engine / Public
> APIs unchanged (one additive `BacktestBroker.last_price/last_time` accessor only); no new
> UI, reports unchanged; legacy `/run` payload unchanged.

### Added
- **`apps/api/backtest/risk.py` (new)** — `BacktestRiskConfig(RiskConfig)` with
  backtest-only knobs (`max_risk_per_trade_pct`, `circuit_breaker`); `BacktestRiskCheck`;
  `BacktestRiskSimulator` (per-run, broker-only state reads): `check()` rule chain,
  `snapshot()` per-candle risk timeline, `analytics()`, rejection records with the full
  payload contract; `NO_LIMIT` sentinel for unlimited risk budget.
- **`apps/api/backtest/models.py`** — `BacktestConfig.risk: dict` (rule overrides);
  `RiskRejection`, `RiskTimelinePoint`, `RiskCurvePoint`, `RiskAnalytics` models;
  `BacktestResult.risk_analytics` (additive, default empty).

### Changed
- **`apps/api/backtest/manager.py`** — `_place_via_broker` gates orders via
  `BacktestRiskSimulator.check()` (with quantity clamping) instead of the live
  `risk_manager.evaluate(dry_run=True)`; `run`/`_fast_run` build the simulator when
  `risk_enabled` and attach `result.risk_analytics`; `_collect_snapshot` records risk
  timeline points; replay path passes `risk_sim` through.
- **`apps/api/backtest/replay_engine.py`** — `run(..., risk_sim=None)`: simulator path
  replaces the live risk dry-run when provided; live `risk_manager` path kept as legacy
  fallback for external callers.
- **`apps/api/backtest/execution.py`** — additive `last_price(symbol)` / `last_time()`
  accessors on `BacktestBroker` (risk sim price source).

### Verification
- **25 new tests** (`tests/test_backtest_risk_sim.py`): rule semantics, rejection payload
  contract, sizing clamp + reducer exemption, circuit-breaker halt, kill/emergency-stop
  config, analytics shape, risk-off parity + risk-on-never-zero + tight-limit reduction at
  the manager level, replay-path simulator use, broker-level sized fill.
- Full suite **908 passed, 1 xfailed** (883 baseline + 25).

## v1.5.10 (2026-08-05) — BACKTEST ENGINE PHASE A: enriched TradeRecords, big-run performance (equity downsampling + trade pagination), interactive charts

> Phase A of the institutional backtest roadmap (A/B/C). TradeRecords now carry the full
> audit trail — entry/exit reasons, per-side slippage/charges/taxes/cost totals, risk amount
> and R-multiple — without breaking any existing payload (all new fields defaulted). Big runs
> (>2k trades, >2k equity points) no longer produce monolithic payloads: equity is
> downsampled server-side (LTTB, first/last preserved) and trades are cursor-paginated. The
> backtest UI swaps static SVG equity/drawdown for interactive `lightweight-charts` canvases
> (crosshair tooltip + entry/exit markers).
>
> Constraint honored: additive changes to the backtest module only — OMS, Risk Engine, Broker
> Layer, Execution Engine untouched; legacy `/run` payload unchanged and backward compatible.

### Added
- **`apps/api/backtest/models.py`** — `TradeRecord` extended with `entry_reason`,
  `exit_reason`, `slippage`, `charges`, `taxes`, `cost_total`, `risk_amount`, `rr` (all
  defaulted for backward compatibility).
- **`apps/api/backtest/execution.py`** — `BacktestBroker._apply_fill` rewritten to open
  records with the signal reason, split entry/exit costs per side, consume entry costs
  proportionally on partial closes (`_consume_entry_costs`, `_clear_entry_state`), and map
  the exit type to a reason (`_exit_reason`: SL/SLM→stop, LIMIT→target, MARKET/signal→
  signal, close_on_end). `_record_trade` computes per-trade slippage, charges
  (brokerage+exchange_tc), taxes (STT+stamp+GST+SEBI), cost_total, `risk_amount`
  (from any resting SL trigger on the symbol at close), and `rr = pnl/risk_amount`.
  Added `total_slippage` property (reset in `__init__`/`update_config`/`reset`).
- **`apps/api/backtest/manager.py`** — `_place_via_broker` sets `order.reason` from the
  signal reason before the risk dry-run; reason threaded through the MAX loop, `_fast_run`
  and `close_on_end` (`_make_close_order(..., reason="close_on_end")`).
- **`apps/api/backtest/replay_engine.py`** — copies `signal.reason` onto orders when empty.
- **`apps/api/backtest/performance.py`** — `downsample_pairs(points, threshold=2000)` LTTB
  (largest-triangle, keeps first/last); `PerformanceAnalytics.calculate(..., max_equity_points)`
  downsamples `equity_curve` after computing ratios/returns (so KPIs stay exact).
- **`apps/api/routes/v1_backtest.py`** — new `GET /backtests/{run_id}/trades?cursor&limit`
  (cursor-paginated, limit clamped 1–2000); `_result_payload` + run-v2 cap trades at
  `PAYLOAD_MAX_TRADES = 2000` with a `trades_truncated` flag via shared `_payload_trades`/
  `_payload_equity` helpers; restored `export_backtest` signature.
- **`apps/web/app/backtest/page.tsx`** — `BacktestChart` (lightweight-charts `LineSeries`,
  `CrosshairMode` tooltip, `createSeriesMarkers` entry/exit markers) replaces the static SVG
  charts for Equity Curve and Drawdown %.

### Verification
- New tests: enriched trade fields (entry/exit reasons, cost breakdown, duration, model),
  risk/RR from a resting SL, `downsample_pairs` endpoint + shape preservation + full-series
  KPI accuracy, pagination route (clamp, cursor walk, past-end, 404). Suite **883 passed,
  1 xfailed** (was 873). Web `tsc` clean, prod build clean.
- Prod smoke (user `fa668109`, in-container): run-v3 EMA Crossover on `NSE:NIFTY50-INDEX`
  60d/15m, risk off → **57 trades**, all enriched keys present, cost consistency
  (cost_total = slippage+charges+taxes), pagination `total=57 / len=3 / next_cursor=3`;
  1026 equity points served. Backend hot-deployed (6 files, health 200); web `.next`
  deployed (new BUILD_ID, `/backtest` 200, chart bundle served).
- Note: backtests run with `risk_enabled=True` can yield 0 trades because the risk dry-run
  (`risk_manager.evaluate(dry_run=True)` in `_place_via_broker`) rejects backtest orders —
  pre-existing behavior, unrelated to Phase A. Run with risk off (as the UI's default during
  this phase) to exercise trades.

## v1.5.9 (2026-08-04) — BACKTEST DATA + P&L HONESTY: real candles, correct trade attribution

> Backtest hand-check revealed two production defects, both on the legacy and manager run
> paths: (1) `fetch_historical_data` called fyers directly and, when fyers failed (which it
> always does from the container — WAF 403 on `/data/history`, plus a wrong-URL 404 and a
> read-only `fyersApi.log` SDK fallback), it silently returned synthetic candles; the legacy
> `/run` route ran on fabricated data. (2) `build_trades_from_snapshots` priced SHORT entries
> from `average_buy_price` (0.0 for shorts) → entry ₹0 → one PnL of −1.8M per short. And the
> durable candle store returned a partial slice whenever it had ≥2 candles (a 7-day request
> got ~3 days) without topping up.

### Changed
- **`apps/api/engine/backtest.py`** — `fetch_historical_data` now routes through
  `backtest_historical.load` (durable store → broker → Yahoo); synthetic candles remain only
  as a clearly-logged last resort, never when real data exists. Removed dead
  `_map_to_fyers_symbol`/`_resolve_fyers_interval`/`_candle_to_dict` helpers.
- **`apps/api/backtest/historical.py`** — `load` is now **coverage-aware**: refetches +
  merges when the stored slice doesn't span the requested window (trading-day tolerance for
  the 09:15 IST session open), instead of returning a stale partial store.
- **`apps/api/backtest/performance.py`** — `build_trades_from_snapshots` prices SHORT entries
  from `average_sell_price` and LONG from `average_buy_price` (matches the new per-side
  `get_positions`), so short P&L is correct.
- **`apps/api/backtest/execution.py`** — `BacktestBroker` now tracks a position's `entry_time`
  (open candle) and threads it through `_record_trade`, so Trades show real open→close times
  instead of the close candle for both walls.
- **`apps/api/backtest/manager.py`** — `run` builds Trades from `broker.trades` (authoritative
  fill-level records) instead of lossy snapshot reconstruction when available; snapshots use
  the candle timestamp, not wall-clock; `total_fees` is populated from `broker.total_costs`
  (was dead 0.0 — return% is cost-inclusive, `net_pnl` is gross, so the gap was invisible).
- **`apps/api/brokers/fyers_adapter.py`** — SDK history fallback writes to `/tmp/` instead of
  `/app/fyersApi.log` (Errno 13 → SDK fallback always failed).

### Verification
- New tests: legacy fetch → durable store (no synthetic when real data exists); synthetic
  only when the store is empty; coverage-aware refetch+merge; short/long trade attribution
  prices; broker `entry_time`/`exit_time`. Suite **873 passed, 1 xfailed** (was 867).
- Prod probes (user `fa668109`): durable loader now returns a full range (125 real candles for
  a 7-day/15m window across 5 sessions, close range 24178–24774). Manager `trend_rider` on
  `NSE:NIFTY50-INDEX` 30d/15m: 550 candles, 9 trades, real entry → exit timestamps
  (2026-07-07 → 2026-07-10 etc.), and full reconciliation
  `net_pnl + total_fees = equity change` (e.g. qty1: −152.75 + 555.47 = −708.22). Legacy
  `/run` 200 with 550 real candles analyzed (0 trades on trend_rider 15m/7d is a legit
  no-crossover window; oversized qty rejects BUYs over capital — both correct engine behavior).
- Hot-deployed (7 files, health 200).

## v1.5.8 (2026-08-04) — BROKER-FIRST MARKET DATA: real LTP/change% for compact option symbols

> Follow-up to v1.5.7: positions now show real P&L, but LTP/Chg% still came from Yahoo only.
> `/marketdata/quote` bypassed the broker entirely — Yahoo can't resolve the fyers compact
> option format (`SENSEX2680679000CE`, `NIFTY2680424450PE`), so those positions showed `—`
> instead of live prices. Market data now comes from the broker.

### Changed
- **`apps/api/routes/v1_marketdata.py`** — `GET /marketdata/quote` is now **broker-first**:
  resolves the user's active broker and calls the adapter's `get_quotes` (fyers REST
  `/data/quotes`; reuses the running feed adapter via `shared_socket.get_broker_adapter`, else
  the cached `EngineService` engine). Symbols the broker can't price fall back to Yahoo
  per-symbol. No broker → pure Yahoo (unchanged).
- **`apps/api/brokers/fyers_adapter.py`** — `_ensure_fyers_symbol` and `_ws_symbol` now use a
  `BSE:` prefix for SENSEX underlyings (was hardcoded `NSE:` → BSE symbols couldn't be quoted
  or WS-subscribed); `_normalize_quote` preserves `Exchange.BSE` from the symbol prefix.
- **`apps/api/engine/executor.py`** — `ExecutionEngine.get_quotes(symbols)` delegate.
- **`apps/api/market/data_socket.py`** — `get_broker_adapter(broker_type)` accessor.

### Verification
- New tests: broker-first with Yahoo fill (mixed batch → fyers + yahoo quotes by symbol),
  full Yahoo fallback (no broker data), BSE prefix in `_ensure_fyers_symbol`/`_ws_symbol`.
  **867 passed, 1 xfailed**.
- In-container route probe (user `fa668109`): `SENSEX2680679000CE` → `last 106.5 close 206.95
  broker fyers` (real position LTP), `NSE:NIFTY50-INDEX` → `24614.9 / 24774.3 broker fyers`,
  `NIFTY2680424450PE` → `0.1 / 18.35 broker fyers` (closed position — UI uses realised P&L).
- Hot-deployed (4 files, `docker cp` + restart, health 200), pushed `eb4f7d3`.

## v1.5.7 (2026-08-04) — POSITIONS 0.00 FIX: map fyers v3 position fields (real root cause)

> Follow-up to v1.5.5/v1.5.6: the portfolio/terminal positions still showed **0.00** P&L and
> empty averages even for *today's* real trades. Root cause was **backend**: the fyers v3
> `/api/v3/positions` API renamed its fields — `avgBuyPrice/avgSellPrice/unrealised/realised`
> are **null in v3**; the real data lives in `buyAvg/sellAvg/pl/realized_profit/
> unrealized_profit/netQty`. `FyersAdapter._normalize_position` read the null v2 names → every
> live position normalized to `quantity 0 / avg 0.0 / pnl 0.0` (proved via raw in-container
> probe of the v3 payload, user `fa668109`). The v1.5.6 frontend guard was necessary but not
> sufficient — this closes the loop at the source.

### Fixed (`apps/api/brokers/fyers_adapter.py`)
- **`_normalize_position`** — reads v3 fields with v2 fallbacks: `buyAvg`→`average_buy_price`,
  `sellAvg`→`average_sell_price`, `netQty`→`quantity`; `unrealised_pnl` = `unrealized_profit`
  (fallback `pl` for open positions), `realised_pnl` = `realized_profit` (fallback `pl` for
  closed positions), `m2m` = `pl`. Previously all `avgBuyPrice`-style names → zeros.
- **Exchange preserved** — `BSE:`-prefixed symbols now map to `Exchange.BSE` (was hardcoded
  `Exchange.NSE` + prefix dropped, so BSE options lost their exchange).
- **Product mapped** — `productType` `MARGIN` → `ProductType.NRML` (was hardcoded INTRADAY).
- **`_parse_instrument` compact options** — fyers v3 compact symbols (`NIFTY2680424450PE` =
  yymdd + strike, `SENSEX2680679000CE` = strike 79000, expiry 2026-08-06) now parse to
  `OPT`/strike/expiry instead of falling to EQ. Alpha format (`NIFTY26AUG24450CE`) unchanged.

### Verification
- New tests `tests/test_broker_fyers.py`: `test_get_positions_v3_fields` (open MARGIN + closed
  BSE position with real v3 payload → avg 116.1 / realised 2915.25 / NRML / OPT / strikes /
  expiry) + `test_parse_instrument_compact_numeric_options` — **15 passed**; full suite
  **864 passed, 1 xfailed** (+2).
- Hot-deployed to prod API (`docker cp` + restart, health 200); in-container probe via
  `_authenticate_adapter` → **5 real positions**: open `SENSEX2680679000CE` qty 20 avg 116.1
  unrealised −192, closed `NIFTY2680424500PE` realised +2915.25, `NIFTY2680424600CE` −575.25,
  `SENSEX2680677500PE` −884, `NIFTY2680424450PE` −1287 — matches fyers `overall`
  (`pl_realized 169 / pl_unrealized −192`).
- `/engine/positions` route probe → same real values (BSE exchange, NRML, OPT metadata).
- Browser smoke on prod (puppeteer, mocked real payload shapes): open position shows **−192**
  unrealised (not 0.00), closed shows **+2915.25** / **−575** realised, Unrealised·Realised
  totals present, 0 console errors — **7/7 OK**. Smoke user (`tmv3*`) deleted.

## v1.5.6 (2026-08-04) — PORTFOLIO 0.00 FIX: fall back to broker P&L when no live quote

> Follow-up to v1.5.5: the portfolio/terminal positions still showed **0.00** P&L for symbols
> the live quote cannot price. Root cause: the quote poll returns `last_price: 0` for symbols
> Yahoo can't resolve (custom option formats like `SENSEX2680677500PE` / `NIFTY2680424450PE` —
> confirmed via in-container probe: `/marketdata/quote` → `{last_price:0, close:0}`), and
> `positionQuote` treated that as a *valid* quote → P&L computed `qty × (0 − avg) = 0.00`
> instead of using the broker's `unrealised_pnl`. **A quote/tick is only valid when
> `last_price > 0`.** Also hardened the Today's P&L `unrealisedPnl` memo to the same rule.

### Fixed
- **`apps/web/app/portfolio/page.tsx`** — `positionQuote` and the `unrealisedPnl` memo now
  require `last_price > 0` before treating a tick/quote as authoritative; otherwise fall back
  to the position's own `unrealised_pnl` / `realised_pnl`.
- **`apps/web/app/terminal/page.tsx`** — identical guard for `positionQuote` and
  `quoteForTicket` (terminal had the same latent bug for zero-quotable symbols).

### Verification
- In-container probe (user `fa668109`): `/engine/positions` → 5 rows all in the
  `SENSEX2680677500PE`-style format with `quantity:0 avg:0 pnl:0`; `/marketdata/quote` returns
  `last_price 0 / close 0` for all 5 → previously rendered as P&L 0.00.
- Browser smoke on prod (puppeteer, mocked zero-quote positions): open position with broker
  `unrealised_pnl=+500` shows **+500** (not 0.00), closed position shows +500 realised,
  no fabricated `+0%`, 0 console errors — **5/5 OK**.
- Web `tsc` + `next build` clean; deployed `.next` (BUILD_ID `wn34X_4_dOkAyST4mlg6Y`),
  `/portfolio` + `/` 200. Smoke user (`tmzero*`) deleted.
- API untouched (862 passed, 1 xfailed baseline).

## v1.5.5 (2026-08-04) — PORTFOLIO: rich positions (open + closed today) + trade history

> Beta feedback fix (allowed under feature freeze): the portfolio page only showed a minimal
> Open Positions table (symbol/qty/avg/LTP/P&L) with no closed-positions view, no per-position
> buy/sell detail, no change% / P&L% columns, and no trade history. Everything needed was already
> returned by `/engine/positions` (`buy_quantity/sell_quantity/average_sell_price/realised_pnl/
> m2m`) and `/engine/orders` (filled orders) — **frontend-only change**, same data sources the
> terminal already used.
> - **Positions panel** — upgraded to the terminal's rich layout: split into **Open Positions**
>   (Symbol/Qty/Buy/LTP/**Chg%**/Unrealised P&L + pnl%) and **Closed Today** (Buy Qty/Avg Buy/
>   Avg Sell/Realised P&L), with an Unrealised · Realised total in the panel header. Live change% /
>   LTP come from the WS tick first, else a 5s quote poll of the position symbols (`usePolling`),
>   else the broker's own P&L fields.
> - **Trade History panel (new)** — the 20 most recent **executed (FILLED)** orders: Symbol/Side/
>   Qty/Price/Time with an executed-count in the header. Recent Orders (all statuses) kept below it.

### Changed
- **`apps/web/app/portfolio/page.tsx`** — extended `Position` interface (buy/sell qty, avg sell,
  realised pnl, m2m); added `TickData`/`usePolling` imports, `QuoteData` state, position-symbol
  WS subscription, `refreshQuotes` + `positionQuote` helpers; split positions open/closed; new
  Trade History table of FILLED orders.

### Verification
- Web `tsc --noEmit` clean; `next build` (`.env.production`) clean.
- Browser smoke on prod (puppeteer, real signup, mocked `/engine/positions` + `/engine/orders`
  via fetch override — new rows flow through the same react-query hooks): **18/18 OK** —
  Positions (3): Open (2) header + rows `NIFTY50-INDEX`/`RELIANCE-EQ`/`NIFTY26AUGFUT`, Closed
  Today (1), chg% column (`-0.32%`), pnl% cell, realised `+6000` on the closed row; Trade
  History "2 executed" with BUY + SELL fills; Recent Orders PENDING + PAPER badge intact; 0
  console errors (only the known anonymous `/auth/me` 401 filtered).
- Deployed web `.next` tar → stopped container → `chown -R 1001` → restart: `✓ Ready`,
  `/portfolio` + `/` 200, new BUILD_ID served. Smoke user (`tmport*`) + 4 leftover
  `tmchgpct*` test users deleted from GoTrue.
- API untouched (862 passed, 1 xfailed baseline unchanged).

## v1.5.4 (2026-08-04) — FEED FIX: real change% on every tick + live streaming for typed symbols

> Beta feedback fix (allowed under feature freeze): the terminal's change% showed **0.00** for
> symbols with live ticks (price moved, percentage never did). Two root causes, both on the
> backend feed path — one line of code and one wiring gap:
> 1. **Fyers data socket ran in `litemode=True`** — the payload is stripped to just
>    `{ltp, symbol}`. `_parse_sdk_tick` read `ch`/`chp` → always `0.0` → every relayed tick
>    carried `change_pct: 0.0` regardless of symbol. Flipped to full mode: ticks now carry real
>    `change`, `change_pct` (and bid/ask/oi/prev_close/open/high/low).
> 2. **Typed symbols were never streamed** — `/feed/start` subscribes only the fixed MAJOR list,
>    so user symbols (e.g. `NSE:NIFTY26AUGFUT`, `NSE:NIFTY26AUG25000CE`) never produced ticks and
>    the Yahoo quote fallback returns 0/0 for futures/options. WS `subscribe` now extends the
>    running fyers feed (`subscribe_symbols` keeps the reverse name map + subscribed list in sync;
>    short retry loop while the SDK socket connects).

### Fixed
- **`apps/api/brokers/fyers_adapter.py`** — `litemode=False` in `FyersDataSocket` (was silently
  stripping every field except ltp); new `subscribe_symbols()` returning still-pending symbols
  (symmetric to the existing `unsubscribe_symbols`).
- **`apps/api/market/data_socket.py`** — `SharedDataSocket` now registers the **inner** adapter
  (not the `CircuitBreakerBroker` wrapper, which doesn't forward privates); new `add_feed_symbols`
  + `feed_has_ws` (retries while a fyers socket is expected, i.e. token present).
- **`apps/api/routes/v1_marketdata.py`** — WS `subscribe` action extends the running fyers feed
  with the client's symbols (up to 10s, bounded).
- **`apps/web/app/terminal/page.tsx`** — belt-and-braces: prefer the live tick's `change_pct`;
  only fall back to the quote poll when the tick lacks change data.

### Verification
- Prod WS probe (API-minted token + `tm_session` cookie): before → `NSE:NIFTY50-INDEX`
  `change=0.0 change_pct=0.0`; after → `change=-159.4 change_pct=-0.64`, and the user's real
  symbol `NSE:NIFTY26AUGFUT` now streams `change=-97.1 change_pct=-0.39` (feed extension works,
  log: `Feed fyers extended (pending=0)`).
- Browser smoke on prod (puppeteer, real signup): typing `NSE:NIFTY50-INDEX` renders the ticket
  quote panel `NSE:NIFTY50-INDEX 24614.9 -0.64%` — real change%, not 0.00. 6/6 OK, 0 console
  errors (only the known anonymous `/auth/me` 401 noise filtered).
- API regression **862 passed, 1 xfailed** (4 new fyers adapter tests). Web `tsc` + `next build`
  clean.
- Deployed: API hot `docker cp` (3 files) + restart, health 200; web `.next` tar
  (`--strip-components=1`) + restart, `✓ Ready`, `/terminal` 200.

### Notes
- The Redis pub/sub `market:ticks:*` path still builds `Tick` without `change_pct` (nothing
  writes that channel in-repo) — untouched, out of scope.
- Yahoo fallback feeds (no fyers token) only cover the MAJOR list — futures/options need the
  fyers feed (or broker creds), by design.

## v1.5.3 (2026-08-04) — TERMINAL UI FIX: change%, open/closed positions, buy/sell price + realised/unrealised P&L



> Beta feedback fix (allowed under feature freeze): the terminal's change percentage never
> rendered for typed symbols and position details (buy/sell price, realised/unrealised P&L,
> closed positions) were not visible. Frontend-only fix — the backend already returns every
> field via `/engine/positions` (`buy_quantity`, `sell_quantity`, `average_buy_price`,
> `average_sell_price`, `unrealised_pnl`, `realised_pnl`, `m2m`). Deployed: hot `docker cp` of
> `.next` into `trademetrix_web`. `tsc` + `next build` (`.env.production`) clean.

### Fixed
- **`apps/web/app/terminal/page.tsx`** — extended `Position` interface (buy/sell qty, avg sell,
  realised P&L, m2m); positions split into **Open Positions** (Qty / Buy / LTP / Chg% / Unrealised
  P&L + pnl%) and **Closed Today** (Qty / Avg Buy / Avg Sell / Realised P&L) sections; header
  totals for Unrealised + Realised; live-tick-first, quote-poll-fallback LTP; change% column.
- **Change% root cause**: WS tick feed only relays `subscribed_symbols` (fixed MAJOR feed), so
  typed symbols had no `change_pct`. Now the terminal polls `GET /marketdata/quote` every 5s
  (`usePolling`) for position + typed symbols and computes `(last−close)/close` client-side
  (`Quote.close` = previous close). Falls back to `Tick.change_pct` when the symbol is WS-fed.
- **`apps/web/lib/api.ts`** — added `marketdata.quote(symbols)` client method.

### Verification
- Browser smoke on prod (puppeteer, real login via API-issued `tm_session` cookie with
  `domain=.trademetrix.tech`): 0 console/page errors; quote poll fires; change% renders for a
  typed symbol (RELIANCE −1.96%); with mocked positions payload: **OPEN POSITIONS (2)** +
  **CLOSED TODAY (1)** headers render with Buy 1280 / Avg Sell 3412 / Unrealised +134 /
  Realised +84 / RELIANCE change% ~−1.9% all present in the DOM.
- Deployment note: `.next` must be extracted with `--strip-components=1` (tar contains a `.next/`
  prefix — a nested `.next/.next` crashed the server on BUILD_ID ENOENT; fixed via host-side
  extraction + `docker cp` into the stopped container + `chown`, no drift vs repo after).

### Notes
- Fresh-user paper `/engine/trade` returns `RISK_REJECTED` — pre-existing backend risk behavior
  (worker-side shared rule state), not a regression of this fix; unchanged here.
- Test users cleaned from prod (10 GoTrue admin deletes).

## v1.5.2 (2026-08-04) — user_strategies JSONB PARITY FIX (FINAL CORRECTNESS DEPLOY)

> The legacy `/api/v1/user-strategies` service assumed a dev-only relational schema that does
> not exist on prod Supabase: legs live in a `legs` jsonb column and legacy scalar fields
> (`entry_time`, `overall_*`) live inside a `config` jsonb column. List/get/create/update on
> prod failed with PGRST200 (phantom `user_strategy_legs` join) and PGRST204 (missing columns).
> Deployed: commits `ebcf9ff` + `19a1bbc`, hot-updated on VPS. Full suite **858 passed, 1 xfailed**.
> Report: `docs/evolution/certs/web_v1.5.1/user_strategies_jsonb_deploy_report.md`.

### Fixed
- **strategy_service** list/create/get/update/`_row_to_strategy` read/write the prod jsonb schema
  (`select("*")`, legs as jsonb, `entry_time`/`overall_*` folded into `config` on create and merged
  on update); `normalize_user_strategy_row()` merges config back into the row.
- **user_strategy_runner `_get_open_legs`** reads the jsonb legs column via the normalized row.
- **copilot** funds context reads the live `margin_snapshot` table.
- **Migration `20260804_01800_user_strategies_jsonb.sql`** — idempotent `ADD COLUMN IF NOT EXISTS`
  `config`/`legs` jsonb; no-op on prod (columns already present), applied locally.

### Verification
- API E2E on prod: create → read (legs=2, config merged) → update → list → **restart** → re-read
  persists; DB rows confirmed `config={"entry_time":"10:00"}`, legs=2.
- Browser E2E (real prod UI session): **13/13 OK** — signup → Create → Read → Edit+Save → Reload
  → Deploy/Start (PAPER, 2/2) → Stop (paused) → Delete; zero page errors; schema cache verified via
  OpenAPI (legs+config present, `user_strategy_legs` absent).
- Post-deploy logs: 0 schema-cache/PGRST errors; only pre-existing timeout-middleware and
  yfinance/Redis noise. Health endpoints green throughout.

### Notes
- Feature freeze now in effect: only production bug fixes, security fixes, broker compatibility
  updates, performance improvements, and beta feedback fixes are accepted.
- Beta backlog: dashboard "User Strategies" tab targets a nonexistent `/admin/strategies/all-user`
  endpoint (404 → empty table); no end-user UI exists for the legacy user-strategies lifecycle.

## v1.5.1 (2026-08-04) — BETA HARDENING SPRINT

> Reliability/correctness hardening driven by 48h prod telemetry + browser E2E + beta
> feedback. No new features. Deployed: commit `fd896ca`, API hot-updated on VPS.
> API full suite: **858 passed, 1 xfailed** (+25 regression tests vs v1.5.0).
> Post-deploy prod logs (30 min): **0×** `invalid input syntax for type uuid: "system"`,
> **0×** `Paper bracket quote refresh failed`, **0×** `CircuitBreaker[broker_fyers] is open`,
> **0×** `async_safe_single query failed: 'NoneType'`.
> Full detail: `docs/evolution/certs/web_v1.5.0/hardening_report.md`.

### Fixed
- **Kill switch (P1):** global gate read Redis `global:kill_switch` flag (the old `risk_settings`
  probe with `user_id='system'` always returned 22P02 and silently disabled the gate);
  emergency-stop state persisted to Redis and restored on startup (restart-safe); audit writes
  fall back to `audit_log` when `risk_audit_log` is missing. Migration
  `20260804_01600_risk_audit_log.sql` added (apply to prod via SQL editor; DDL blocked from API).
- **Broker token expiry (P1):** `TokenManager` fast-fails on an already-expired stored token and
  maps open circuit breaker → structured `BrokerTokenExpiredError`; `/engine/positions|funds`
  return `401 BROKER_TOKEN_EXPIRED` instead of raw 500 tracebacks.
- **Paper bracket quotes (P2):** SL/TARGET price discovery is broker-independent for paper orders
  (cache → Yahoo → broker REST last); per-symbol warning throttle 1/60s kills the 5542-line spam.
- **`async_safe_single` (P2):** guards a None `execute()` result (was surfacing misleading
  `'NoneType' object has no attribute 'data'` warnings and masking the query).
- **Rate limiter (P3):** `/analytics/track-batch` exempt from the shared per-IP budget (5s
  fire-and-forget batch consumed 12/60 RPM); default budget 60 → 120 RPM.

### Verification
- New tests: `test_kill_switch_hardening.py` (7), `test_token_manager_hardening.py` (4),
  `test_safe_query_hardening.py` (3), `test_ratelimit_hardening.py` (3),
  `test_bracket_quote_hardening.py` (4); extended `test_engine_service.py` (+4), adapted
  `test_risk_fail_closed.py`, `test_auto_trading.py`.
- Live prod smoke: emergency stop/release persist to Redis and restart-safe recovery sees stops;
  global kill switch enable sets Redis flag and gates `global_kill_switch_active()`; both cleaned up.
- Incidents: INC-015, INC-016, INC-017 added (Resolved).

> **Release status: `v1.5.0-beta` — TRADEMETRIX V1.5.0 BETA READY** (tag `v1.5.0-beta`).
> Web app deployed for Auto Trading v1.0: `next build` clean (BUILD_ID `gJiJa4QYQJlUThzieN0Ff`),
> hot-swapped into `trademetrix_web`, container healthy. Browser E2E (Playwright, prod):
> **38/38 functional checks PASS** — 18 routes, 9 API integrations, paper lifecycle
> (deploy/status/pause/resume/reconcile/stop), live-no-confirm **409 gate**, emergency
> stop + release, Confirmation Wizard (client checkbox + server 409). **0 page errors,
> 0 hydration warnings, 0 React warnings.** Reports:
> `docs/evolution/certs/web_v1.5.0/{web_deployment_report.md, browser_smoke_report.md, browser_smoke.json}`.
> API full suite: **832 passed, 1 skipped, 1 xfailed**.
> Known pre-existing prod noise (not regressions): `/engine/*` CORS blocks from expired
> Fyers token (circuit breaker open, tracked since 2026-08-01, pending re-auth).

### Added
- **`strategy_runtime/` (new package, v1.0.0)** — first-class runtime owning the full strategy lifecycle (start → run → pause/resume → stop → restart → recover): typed `StrategySpec`/`StrategyTrigger`/`RuntimeState` (`models.py`), strict `RuntimeStateMachine` + `IllegalTransition` + `can_transition` (`state_machine.py`), per-user/per-broker `RuntimeRegistry` (`registry.py`), `RuntimeContext` + `position_memory_for()` (`context.py`), `RuntimeLifecycle` + `runtime_strategy_lifecycle` singleton (`lifecycle.py`), `StrategyRuntimeManager` + `strategy_runtime_manager` singleton (`manager.py`), `RuntimeDispatcher`/`CandleDispatcher`/`TriggerDispatcher` (`dispatchers.py`), `StrategyWorker` (run loop, candles, time-trigger fold, manual dry-run evaluate) (`workers.py`), `RuntimeRecovery` (restore + adopt + fail-open) (`recovery.py`), `RuntimeObservability` (`observability.py`), `RuntimeEvent`/`runtime_bus` (`events.py`), `StrategyStateStore` + `CheckpointStateStore` + `InMemoryStateStore` (`state_store.py`), public API + `__version__` (`__init__.py`).
- **HTTP surface** — `routes/v1_strategy_runtime.py` (prefix `/api/v1/runtime`, auth-gated): POST `/deploy`, `/{id}/stop|pause|resume|restart|evaluate`, GET `/{id}/status`, `/strategies`, `/health`, POST `/event` (admin). Legacy `routes/v1_builder.py` deploy/start/stop now delegate **runtime-first** with legacy `start_graph_strategy` fallback (`_build_runtime_spec`/`_runtime_start`/`_runtime_stop`).
- **App wiring** — `main.py` lifespan: `configure_state_store(SupabaseCheckpointStore())` + `await initialize()` (fail-open) + 4s-delayed `RuntimeRecovery().recover()` background task + graceful `shutdown()` (scheduler → workers → dispatcher).
- **Prometheus** — additive metrics in `core/prometheus.py`: `strategy_runtime_running` Gauge; `strategy_runtime_lifecycle_events_total{state}`, `_orders_total{outcome}`, `_errors_total`, `_restarts_total`, `_ticks_total`, `_dropped_ticks_total` Counters; `strategy_runtime_latency_seconds`/`strategy_runtime_recovery_seconds` Histograms.

### Changed
- `execution_engine/persistence.py` `recover_runtime_state()` skips runtime-owned strategies (checkpoint kind `strategy_runtime` → `runtime_owned_strategies` → recorded in `strategy_skips`) — no double-start with engine recovery.
- Manager: `_start_running` calls `_stop_legacy(...)`; new `_stop_legacy()` cancels surviving legacy `graph_strategy_runner._running_tasks` for adopted strategies; new `shutdown()`.

### Fixed (found while building the runtime)
- `core.cache` `get`/`set` are coroutines — `_persist_seen_ids`/`_load_seen_ids` in `workers.py` now async and awaited in `stop()` and the run-loop `finally`.
- `recovery.py` bogus `from strategy_runtime.recovery import runtime_observability` removed; `_adopt` called on `self` (not `self._manager`); `obs.record_recovery` → `runtime_observability.record_recovery`.
- `routes/v1_builder.py` manager junk line removed; `_publish_event` wrapper removed (`_on_broker_disconnect` now emits `_publish_runtime_event("BrokerDisconnected", ...)` directly).

### Verification
- New tests: `tests/test_strategy_runtime.py` (18: lifecycle, state-machine table, pause/resume/restart, restart-from-stopped, candle eval + orders, seen-candle dedup, no-signal, two-strategy isolation, MTF aggregation, manual dry-run, broker disconnect/reconnect + per-broker isolation, session open/close, checkpoint persist/remove, health, user isolation), `tests/test_strategy_runtime_recovery.py` (8: restore running, idempotent, skip stopped, paused-as-paused, adopt legacy-running, engine-recovery skip guard, legacy-only restart, fail-open broken store), `tests/test_strategy_runtime_api.py` (3 HTTP: deploy→status→pause→resume→evaluate→stop lifecycle, health, 404 unknown id).
- Full regression: `pytest tests/` → **806 passed, 1 xfailed** (+3 vs v1.4.0's 803, +50 vs v1.3.1's 717).
- Benchmark (`benchmark_strategy_runtime.py`): tick throughput ≈78k ticks/s (0 dropped), candle eval ≈15.7k evals/s (avg 0.31ms), 10-worker fanout ≈4.2k ticks/s (uniform, 0 dropped), seen-candle dedup 10k replays → 1 eval/1 order.

### Known gaps
- Order execution still flows through the frozen `engine.gate.execute_order(...)` path; runtime-level risk integration (position/order checks) deferred.
- Recovery is fail-open by design — a broken store means no auto-restore (never crashes startup).
- Supabase `strategy_runs` insert noise (permission-related) is benign warn-level.
- Docs: `docs/evolution/STRATEGY_RUNTIME_V1.md`, `docs/evolution/RELEASE_AUDIT_STRATEGY_RUNTIME_V1.md`, `docs/evolution/PROD_READINESS_STRATEGY_RUNTIME_V1.md`.

## v1.4.0 (2026-08-03) — EXECUTION ENGINE V1.0 (CANONICAL EVENT-DRIVEN EXECUTION LAYER)

### Added
- **`execution_engine/` (new package)** — canonical, event-driven execution layer composed on top of the frozen Broker SDK v2: typed domain bus (`events.py`, 6 domains / 24 event types, thread-safe publish with `call_soon_threadsafe`, single async FIFO dispatcher, deterministic inline dispatch pre-startup, sequence + correlation ids, 2000-event ring buffer, legacy `execution.event_bus` bridge), canonical `OrderState` machine with `FAILED` + `PARTIAL` alias (`state_machine.py`), FIFO lot engine (`fifo.py`), fills ledger + `TradeManager` (`trades.py`, optional `TradeStore` protocol), event-driven netting + MTM (`positions.py`), per-account P&L with IST daily window + equity/peak/drawdown recomputed from state (`pnl.py`), portfolio snapshots (`portfolio_engine.py`, optional `SnapshotStore`), `ExecutionEngine` facade with idempotent `submit`/`cancel`/`modify` (`engine.py`), Prometheus sink (`metrics.py`), and one-call bootstrap `init_execution_engine(loop)` wired into `main.py` lifespan.
- **Legacy composition** — `portfolio/manager.py` `refresh()` mirrors broker-truth state onto the canonical bus (`portfolio.snapshot`, `source: portfolio_manager`), additive and fail-open.

### Changed
- `apps/api/main.py` — lifespan calls `init_execution_engine()` after `order_manager.start()` and `shutdown_execution_engine()` on graceful shutdown (both non-fatal on failure).

### Fixed (found while building the engine)
- FIFO realized P&L sign inversions (SELL-against-longs + BUY-against-shorts) — closing above entry now realizes a profit.
- Infinite `portfolio.snapshot` fanout (PortfolioEngine self-trigger) + duplicate snapshots per fill (subscription scoped to PORTFOLIO domain).
- Duplicate ring-buffer entries (`_finalize` idempotency) and inline-dispatch race (`apublish` drains cascade tasks).
- `EXECUTION_RESULT` KeyError on non-fill statuses; `open_positions` added to `portfolio.revalued` payload.

### Verification
- New tests: `tests/test_execution_engine.py` (40 tests: state machine, FIFO, bus incl. thread-safety, trade ledger, positions lifecycle, P&L/portfolio chain with FIFO round-trip 267.5, facade outcomes, metrics, bootstrap, legacy composition).
- Full regression: `pytest tests/` → **756 passed, 1 xfailed** (+39 vs v1.3.1's 717).

### Known gaps
- Durable `TradeStore`/`SnapshotStore` adapters not wired (legacy `orders` audit table remains the durable trail).
- `oms/state_machine.py` / `execution/models.py` delegation to the canonical machine deferred to keep the regression surface frozen.
- Docs: `docs/evolution/EXECUTION_ENGINE_V1.md`, `docs/evolution/RELEASE_NOTES_EXECUTION_ENGINE_V1.md`.

## v1.3.1 (2026-08-03) — UNIFIED BROKER SDK V2 (PHASES 3 & 4: OBSERVABILITY + LIVE CERTIFICATION)

### Added
- **`brokers/sdk/events.py` (new)** — typed broker audit event bus: canonical `BrokerEventKind` set (login/logout, token refresh/expiry, auth, order sent/rejected/filled, position, websocket up/down, rate-limited, circuit open, health-changed, reauth-required), sequence-numbered fan-out to sinks, in-memory ring buffer (`recent`), severity normalisation, `LoggingSink` (structured `event=…` lines), `MetricsSink` → Prometheus `broker_events_total`, and a health bridge (state transitions publish `HEALTH_CHANGED`).
- **`brokers/sdk/auth.py` (new)** — unified authentication layer: `Token` / `TokenState` / `token_state()` (valid / expiring-soon / expired / invalid with 5-min buffer), single-flight refresh (`ManagedSession`), re-auth-required state, `InMemoryTokenStore` + pluggable `TokenStore`, per-account `SessionManager` registry with snapshot, and `AuthProvider` base for brokers. Re-auth on refresh failure → `ReAuthRequiredError`; state exposed via `session.health()`.
- **`brokers/sdk/websocket.py` (new)** — unified WebSocket manager (backend-agnostic via a `WebSocketBackend` factory): auto-reconnect with exponential backoff (cap 60s), heartbeat + latency monitoring, subscription dedup + resubscription on connect, message routing to handlers, stats (`messages_in`, reconnects, last pong), and `health()`.
- **`brokers/sdk/health.py` (new)** — `BrokerHealthService`: component signals (REST, WS, auth, rate-limit, circuit, degraded) → one canonical `BrokerHealthState` (connected/rest/ws-only/degraded/rate_limited/circuit_open/auth_failed/disconnected); event-bus driven; per-broker snapshot with `reported_at`.
- **`brokers/sdk/metrics.py` (new)** — unified broker metrics surface: flat serialisable snapshot (requests/success/failure/retry, breaker, ws, auth, token-refresh count, order/rest/ws latency, cache/dedup hit ratio, rate-limit utilisation), `MetricSource` producer protocol, `BrokerMetrics` registry with per-broker snapshots + health overlay.
- **`brokers/sdk/observability.py` (new)** — one-call app wiring (`wire_default_observability`): `TransportMetricSource` (adapts `HttpTransport.snapshot()`/`health()` to the metrics contract), `breaker_state_bridge` (circuit-breaker callback → health + `CIRCUIT_OPEN` event + prometheus gauge), and health/event/metrics composition. Wired in `main.py` lifespan (non-fatal on failure).
- **`brokers/fyers_provider.py` (new)** — Fyers auth `AuthProvider` (access-token consent model, no silent refresh → `ReAuthRequiredError`) + live-observability glue `register_fyers_observability` (real transport snapshot into the default metrics/health registries).
- **New broker endpoints** — `GET /api/v1/brokers/health` (all brokers), `/health/{broker}`, `/metrics/{broker}` (14-key flat snapshot), `/capabilities` (runtime discovery). Auth-required; unknown broker → 404. Brokers block added to `/health/metrics` (`brokers` key).
- **Prometheus** — `broker_events_total{broker,kind}`, `broker_health_state{broker}` (1–8 ladder), `broker_auth_state{broker}` (0–5 ladder), plus `record_broker_event/record_broker_health/record_broker_auth` in `core/prometheus.py`.
- **`brokers/sdk/live_cert.py` (new)** — live certification framework for the canonical engine workflow: `LIVE_STEPS` (login → token refresh → quotes → history → option chain → websocket → positions → holdings → funds → disconnect → reconnect → token-expiry → circuit-recovery → [place/modify/cancel order]). Drivers speak the canonical v2 surface (`connect(credentials)`, `refresh_token(credentials)`, `get_option_chain(symbol)`, `subscribe_market_data(symbols, on_tick)`), signature-filtered for legacy methods; the websocket probe subscribes in a background task and accepts a connected, error-free feed (ticks are market-hours dependent).
- **`brokers/live_cert.py` (new)** — `python -m brokers.live_cert --broker <name> [--allow-orders] [--user <uuid>] [--out path]` orchestration: resolves the adapter via the SDK registry, optionally authenticates from stored broker credentials (`--user`), runs every step with a per-step timeout, and writes `.{json,md}` certification reports.

### Changed
- `apps/api/routes/v1_brokers.py` — health/metrics/capabilities endpoints (Phase 4) with auth + 404 handling, per-broker payloads backed by the SDK health/metrics registries.
- `apps/api/core/metrics.py` — `/health/metrics` now includes the `brokers` key from the SDK metrics registry.
- `apps/api/core/prometheus.py` — broker state gauges + event counter (Phase 4).
- `apps/api/main.py` — `wire_default_observability()` called in lifespan (event bus → health → metrics composed), `broker.connected` event recorded on credential save.
- `apps/api/brokers/sdk/live_cert.py` — `LiveCertResult` is skip-aware (`add(..., skipped=True)`); `passed` = every **executed** (non-skipped) step passed; `ran` lists executed steps; order-steps recorded as skipped unless `allow_orders=True`; `write_report` emits `.json` + `.md`; `_call_live` scores a completed call (even returning `None`) as passing, matching adapter fire-and-forget semantics; credential-backed connect steps (`login`/`reconnect`/`circuit_recovery`) reuse the stored creds; capability-absent steps raise `UnsupportedFeatureError` → recorded as SKIP.

### Verification
- New tests: `tests/test_sdk_phase3.py` (events bus fanout/ring/severity/sinks, auth lifecycle incl. refresh/re-auth/invalidate/session-manager, health derivation/tracking/degrades, websocket manager subscribe/reconnect/routing/latency — ~25 tests) + `tests/test_sdk_phase4.py` (metrics overlays, registry snapshots, breaker bridge, health/metrics/capabilities endpoint shapes — ~13 tests) + `tests/test_sdk_live_cert.py` (healthy pass, broken adapter, token-expiry invalidation, opt-in order steps, per-step timeout, report serialisation/presence, default-driver coverage of all steps, capability-absent skip, credential-backed CLI recipe — 11 tests).
- Full API regression: `pytest tests/` → **717 passed, 1 xfailed** (baseline 662 for v1.3.0; +55 new).
- **Fyers live certification — LIVE_CERTIFIED (2026-08-03)**: credential-backed run (`--user fa668109-…`) completed in 18.1s against production: login, quotes, history, websocket, positions, holdings, funds, disconnect, reconnect, circuit-recovery all PASS on real live data; `token_refresh`/`token_expiry`/`option_chain` recorded as SKIP (Fyers capability-absent — `UnsupportedFeatureError`). Report: `docs/evolution/certs/fyers_live_cert.{json,md}`.

### Known limitations (not regressions)
- **Fyers `get_option_chain` live certification** is recorded as SKIP in the live-cert run (`UnsupportedFeatureError` — no direct Fyers API surface); the platform-level option-chain route remains covered by the transport (10s TTL) and the Fyers rate-limit audit. Tracked in `docs/evolution/BROKER_SDK_V2.md` → Known Gaps.
- Live certification for the 10 non-Fyers brokers still waits on active credentials (cert-only step recorded when run).

## v1.3.0 (2026-08-03) — UNIFIED BROKER SDK V2 (PHASE 2: GENERIC TRANSPORT)

### Added
- **`brokers/sdk/transport.py` (new)** — generic, broker-agnostic `HttpTransport` extracted from `brokers/fyers_http.py`: per-token sliding-window rate limiter (RPM + burst), jittered exponential backoff honoring `Retry-After` (429/1015), zero-retry WAF blocks (403), in-flight dedup, GET response caching, correlation ids, `health()`, and Prometheus counters (`broker_http_calls/wire_calls/cache_hits/dedup_hits/retries/rate_limited/waf_blocks/failures_total` + `broker_http_latency_seconds`).
- **Pluggable strategy extension points** — `AuthStrategy` (header + signing hook), `HeaderStrategy`, `URLBuilder`, `ResponseParser`, `ErrorTranslator` (status → typed `BrokerError`), `RetryPolicy`, `RateLimiter`/`TokenRateLimiter` — zero `if broker` branches; adding a broker = config + strategy overrides only.
- **`GET /brokers/admin/rate-limit`** now backed by the same transport (unchanged shape) — per-token RPM/retry ledger plus new `health()` data.

### Changed
- **`brokers/fyers_http.py` refactored into a thin facade** over the generic transport — public API identical (`FyersTransport`, `FyersResponse`, `FyersWAFError`, `TokenRateLimiter`, `get_transport`, `fyers_rate_snapshot`); all 7 consumer sites untouched. `FyersWAFError` now subclasses SDK `BrokerWAFError`.
- **`core/prometheus.py`** — new `broker_http_*` transport counters + `record_broker_transport_metric()`/`record_broker_transport_latency()`.
- **Structured logs** gained a `corr=` field (per-request correlation id) on `fyers.request`/`fyers.retry`/`fyers.waf` records.

### Verification
- API regression: `pytest tests/` → **662 passed, 1 xfailed** (baseline 644; +16 generic-transport tests in `tests/test_sdk_transport.py`). Two `asyncio.sleep` patch targets moved from `brokers.fyers_http` to `brokers.sdk.transport` (where sleep now executes).
- Before/after benchmark (`apps/api/benchmark_transport.py`, canned workload vs git HEAD): **Δ = 0 on every accounting counter** (calls, wire calls, cache hits, dedup hits, retries, rate-limited, WAF blocks, failures); overhead ≈ +0.09 ms + ~63 B per request (correlation id + metric emit). Report: `docs/BrokerTransportBenchmark.md`.
- Docs: `docs/evolution/BROKER_SDK_V2.md` §2/§8/§11 updated (Phases 1–2 marked done, onboarding recipe).

## v1.1.0 (2026-08-03) — PRODUCTION READINESS FIXES

### Product policy: complete-and-keep (no removals)
All audit findings (`docs/ProductCleanupAudit.md`, KEEP 29) are now fixed in place — every page is functional, live-data, and discoverable. No features deleted.

### Added
- **`GET /api/v1/feedback` (user feedback history)** — new route in `routes/v1_feedback.py` + `list_user_feedback()` in `application/services/analytics_service.py` (Supabase `feedback_items` query, fail-open fallback); scoped to the authenticated user; new test `test_list_user_feedback_scoped_to_user`.
- **`/funds` page** (`app/funds/page.tsx`) — live margin cards, margin breakdown (pay-in/pay-out, collateral, MTM unrealised) and P&L panel from `/engine/funds` + `/analytics/pnl?period=1d`; broker-connect CTA when no broker. New Trade nav item `Funds` (💰) alongside the broker-management page (`/brokers`, 🏦).
- **Workspace→Terminal integration** — `components/workspace/sidebar.tsx` gained Terminal (💻, `/terminal`) and Option Chain (📡, `/marketdata`) entries.

### Changed
- **Feedback page** (`app/feedback/page.tsx`) — real API submit via `api.feedback.submit` (removed fake `setTimeout`), submission history via `api.feedback.myHistory`, status badges (new/triaged/resolved/wontfix), NPS 0–10 persisted in metadata, auto-refresh after submit.
- **Analytics page** (`app/analytics/page.tsx`) — live `/analytics/pnl?period=1d|1w` + `/analytics/mtm`; KPI row now real (Today's P&L, Total P&L, Win Rate, Avg Win/Loss, Expectancy, Active Runs) plus a live P&L Snapshot panel (realized/unrealized/weekly/monthly/overall P&L, current equity, drawdown %, MTM).
- **Status page** (`app/status/page.tsx`) — rewritten: live probes to `/health`, `/health/ready` (db/cache dependencies), `/health/metrics` (CPU/memory/requests/threads) and EventSource websocket check; 60s auto-refresh; real version/uptime; fake incidents and the mock maintenance button removed.
- **Landing page** (`app/page.tsx`) — header nav gained Pricing + System Status; footer expanded to full public nav (Product: Pricing/Client Portal/Open Terminal; Resources: System Status/Documentation/Contact; Legal: Privacy/Terms/Risk Disclosure/Disclaimer). Footer styles hoisted to module constants to avoid a TypeScript JSX parser bug with nested inline styles.
- **`lib/api.ts`** — new `feedback` (submit/myHistory) and `analytics` (pnl/mtm) client groups; `api.feedback.submit` matches the production endpoint.
- **`docs/ProductCleanupAudit.md`** — updated to KEEP 29; prior HIDE/REMOVE recommendations superseded by the no-delete policy.

### Verification
- API regression: `pytest tests/` → **563 passed, 1 xfailed** (incl. new feedback-history test). Note: bare `pytest` at repo root collects the standalone `pat_test.py` runner (matches `*_test.py`) which exits at import — run scoped to `tests/`.
- `tsc --noEmit` clean; prod build clean (all pages incl. `/funds`).
- Prod E2E + screenshots of landing/funds/feedback/analytics/status and workspace sidebar.

## v1.1.1 (2026-08-03) — POST-DEPLOY E2E HOTFIXES

### Fixed
- **Status probes hit the wrong origin** — health endpoints mount at the API root (no `/api/v1` prefix), so probes 404'd; the status page now derives `API_ORIGIN = new URL(API_BASE).origin` and probes `/health`, `/health/ready`, `/health/metrics` there (`44462a4`, `362c026`).
- **Metrics renderer assumed the wrong payload shape** — `/health/metrics` `requests` is a per-path dict (`{path: {count, avg_ms, max_ms, min_ms}}`), not a flat object; total + top path are now computed and rendered (`362c026`).
- **Logged-out users got 3× 401 retries on every page** — `auth-context` `fetchUser` now fast-paths any `401` to anonymous state immediately (`44462a4`).
- **Status EventSource opened unauthenticated** — the events stream is auth-gated; the page now checks `/auth/me` first and marks the stream operational for anonymous visitors instead of failing (`44462a4`).
- **lightweight-charts parse errors on the workspace chart** — `color-mix()`/CSS-var colors are unparseable by the chart library; all theme colors are now resolved to concrete hex at runtime via `colorVar()` (getComputedStyle) + `mix()` (hex-alpha) helpers (`dc673d9`). Zero pageerrors after fix.
- **Intermittent 405 / stale profile on `PATCH /api/v1/auth/profile`** — two distinct causes, both fixed:
  1. `profiles.onboarding_completed` column did not exist on remote Supabase (PGRST204 → 500). New migration `supabase/migrations/20260803_01400_onboarding_completed.sql` applied.
  2. The 120s in-memory `_user_cache` was never invalidated by profile writes, so `/auth/me` returned the pre-PATCH profile for up to 2 minutes; `update_profile` now pops the cache entry (`a8cbc16`). FastAPI 0.141.x lazy `_IncludedRouter` startup warm-up was also added as a hardening measure (`b0c73f1`).

### Verification
- API regression: `pytest tests/` → **563 passed, 1 xfailed**.
- Full prod E2E green (18/18): landing nav/footer, live status probes, signup → onboarding PATCH → `/auth/me` reflects `onboarding_completed: true`, funds CTA, feedback submit + history, analytics live P&L, workspace Terminal/Option-Chain links. Zero pageerrors, zero hydration errors.
- Remaining expected console noise: single 401 on `/auth/me` per anonymous page visit (no retries), 503 from the external option-chain vendor.

## v1.1.2 (2026-08-03) — FYERS RATE-LIMIT COMPLIANCE

### Added
- **`brokers/fyers_http.py` (new)** — shared per-token `FyersTransport`: sliding-window `TokenRateLimiter` (budget **100 RPM + 8 req/s burst** per access token, 50% headroom under Fyers' ~200/min community-observed ceiling), response caching (`cache_ttl`), concurrent-request dedup (in-flight future), jittered exponential backoff (base 0.25s, cap 8s, `MAX_RETRIES=3`) honoring `Retry-After`, and Cloudflare semantics: **1015 retryable**, **403 = WAF block → `FyersWAFError`, zero retries**. Process-wide registry keyed by `client_id`; `fyers_rate_snapshot()` per-token stats.
- **`GET /brokers/admin/rate-limit`** (admin-only) — live snapshot of per-token Fyers traffic (calls, wire calls, cache/dedup hits, retries, rate-limited, WAF-blocked, failures, RPM). `fyers` key added to `/health/metrics`.
- **Structured logs** — `fyers.request` (endpoint, method, status, retries, latency_ms, cached, dedup, rate_rpm, caller) and `fyers.retry` (attempt, delay, reason).
- **`_fetch_csv` in `market/symbol_master.py`** — 24h TTL cache + backoff for the static Fyers symbol CSVs (NSE_CM/NSE_FO).

### Changed
- **All Fyers REST traffic routed through the transport** — authenticate, place/modify/cancel, orderbook (3s TTL), positions (5s), holdings (10s), funds (5s), quotes (0.5s), span margin (60s cache), history (retries=1/URL, no cache). Order writes (place/modify/cancel) never retry; auth retries=2; reads retries=3.
- **Option-chain call sites** (`routes/v1_marketdata.py` POST + `market/option_chain.py`) — now via `get_transport` with 10s TTL; web route capped at retries=1.
- **OMS bracket quotes WS-first** — `_bracket_quote` prefers a fresh WS-fed tick (`market_cache`, age <5s) over REST and single-flights quotes per (user, symbol) so the global 2s bracket monitor issues one REST quote per symbol regardless of bracket count.
- **`_stream_yahoo` backoff** — Yahoo fallback polling now backs off exponentially (cap 30s) instead of tight-looping on failures.

### Verification
- New `tests/test_fyers_http.py` (9 tests: 429/`Retry-After`, 1015 backoff cap, WAF no-retry, 400 no-retry, dedup → 1 wire call, cache, sliding window + burst ceiling, RPM accounting); `tests/test_broker_fyers.py` rewritten against the mocked transport; `tests/test_margin_estimate.py` updated to transport-shape assertions.
- Full API regression: `pytest tests/` → **573 passed, 1 xfailed**.
- Compliance report: `docs/FyersRateLimitAudit.md` (full endpoint inventory, RPM table, controls, residual risk).
- Pending post-deploy: `/brokers/admin/rate-limit` snapshot on a live trading day; `fyers` block in `/health/metrics`; `fyers.request`/`fyers.retry` lines in logs.

## v1.2.0 (2026-08-03) — UNIFIED BROKER SDK V2 (PHASE 1 FOUNDATION)

### Added
- **`brokers/sdk/` (new)** — enterprise broker-agnostic layer:
  - `errors.py` — typed `BrokerError` taxonomy: `UnsupportedFeatureError`, `BrokerAuthError`, `BrokerRateLimitError` (Retry-After aware), `BrokerWAFError` (never retried), `BrokerConnectionError`, `BrokerTimeoutError`, `BrokerDisconnectedError`, `BrokerValidationError`, `OrderRejectedError`/`MarginInsufficientError`, `BrokerServerError` — each with `code`, `broker`, `retryable`, `http_status`, `retry_after`, `correlation_id`; `translate_broker_error(status, body, headers)` and `translate_exception()` map HTTP/raw failures onto the taxonomy.
  - `capabilities.py` — `CapabilityFlag` enum (19 features: order mod, bracket, cover, GTT, multi-leg, option chain, historical, websocket, market depth, greeks, indices, currency, commodity, margin calculator, …) + `BrokerCapabilities` (canonical `supports()`/`require()` with typed `UnsupportedFeatureError` + the legacy boolean surface) + authoritative per-broker matrix.
  - `registry.py` — `BrokerRegistry` (adapter class + UI metadata + capabilities in one spec), `create()` preserving the `CircuitBreakerBroker` factory contract.
  - `interface.py` — `BrokerPort` protocol (19-method v2 surface) + `BrokerAdapterBase` mixin bridging v2 names onto legacy `BaseBroker` methods; unimplemented features raise the typed error instead of failing unpredictably.
  - `certification.py` — reusable Level A interface cert + Level B behavioral flow.
- **All 11 broker adapters now expose the identical v2 surface** (via `BrokerAdapterBase`; zero behavior change).
- **Certification suite** (`tests/test_broker_certification.py`) — Level A cert for every registered broker; all 11 currently CERTIFIED; one capability gap recorded (fyers `option_chain` — Phase 4 will implement it on the adapter).

### Changed
- **Single source of truth** — execution-layer `BROKER_CAPABILITIES` and UI broker metadata now derive from the SDK registry/matrix (values identical, verified by `test_legacy_equivalence`); legacy `create_broker`/`register_broker`/`get_broker_metadata` delegate to the SDK.

### Documentation
- `docs/evolution/BROKER_SDK_V2.md` — layers, capability matrix, sequence diagrams (order flow, market data, error translation), phased roadmap (transport → auth/ws/health/audit → adapter porting → live cert → benchmarks), migration plan, rollback strategy.

### Verification
- Full API regression: `pytest tests/` → **644 passed, 1 xfailed** (+71 new SDK/certification tests).


## v1.0.1 (2026-08-02) — USER NAVIGATION REDESIGN (P0 INCIDENT FIX)

### Product discoverability — navigation only (zero backend/API/logic changes)

### Fixed
- **P0: normal users were trapped on `/portfolio`** — the app shell hard-redirected every non-admin away from all non-standalone pages, so the sidebar (the only navigation surface) never rendered for them and 4 of 5 shipped features were invisible. The redirect gate now only bounces non-admins from admin routes (`/admin*`, `/dashboard`).
- **Sidebar now renders for every authenticated user** with the full platform: Home (Home/Watchlist/Portfolio shell), Trade (Trading Workspace, Orders, Positions, Funds), Build & Analyze (Market Analyzer, Strategy Builder, Backtest, Analytics, Trade Journal), Manage (Alerts, Risk Control, Settings, Help), Platform (Terminal, Option Chain, Terminal Builder, Strategies, Marketplace, AI Assistant) — all 14 required nav items present.
- **Admin routes fully isolated** — `/admin/*` + `/dashboard` unreachable by users (client gate + existing server-side `require_admin` RBAC untouched); admin sidebar gained a Beta section (Beta Dashboard, Broadcast).
- **Orphaned pages wired in** — Catalog + Multi-Leg buttons on the Strategies page; Account/Feedback/Changelog/Transparency/Status added to the profile popover; logo link is role-aware.
- **Dead ends removed** — `/trade`, `/marketdata`, `/brokers` links from the portfolio header now work for users; sidebar active-state matching tightened (exact-or-child).

### Changed
- `components/app-layout.tsx` (user nav sections, role-aware gate + sections, profile popover, `isActive_`), `app/strategies/page.tsx` (header links), `docs/DiscoverabilityAudit.md` (audit + fix report with navigation map).

### Verification
- Every nav href resolves to a real route (44/44); all 37 user+admin routes return 200 on the prod build; SSR HTML contains the full user nav.
- `tsc --noEmit` clean; prod build clean (46 static pages).
- Post-deploy E2E on prod: login → Home → all menu items, logout, admin-route isolation, console/hydration checks (see `docs/DiscoverabilityAudit.md`).

## v1.0.1-beta (2026-08-01) — BETA OPERATIONS MODE

### GA evidence collection (no product features — telemetry, dashboards, reports)

### Added
- **Persistent product analytics** — new Supabase tables `analytics_events` (event/properties jsonb/session_id/user_id/created_at + 4 indexes) and `feedback_items` (category/title/description/metadata/status/notes + indexes), migration `20250801_01300_analytics_persistence.sql` applied to remote. Replaces the lossy in-memory tracker: everything now survives restarts.
- **Client tracker** (`apps/web/lib/analytics.ts` + `components/analytics-tracker.tsx`) — privacy-first: no PII (`user_id` resolved server-side from auth), payload redaction (secrets stripped, strings capped), sampling + excluded paths + Do-Not-Track respect, 5s batching + keepalive/beacon flush, CSRF-aware, `NEXT_PUBLIC_ANALYTICS_ENABLED`/`NEXT_PUBLIC_ANALYTICS_SAMPLE` config. Tracks session.start, page.view (SPA-aware), click, scroll.depth, client_error.
- **Server-side value events** — authoritative `strategy.created`, `backtest.run`, `order.placed`, `broker.connected` recorded from auth context (never client-supplied); `api_error` recorded by the timing middleware on 5xx.
- **Feedback Center** — in-app dialog (bug/feature/nps/report) now persists to Supabase; admin list + status triage (new/triaged/resolved/wontfix) via `GET/PATCH /api/v1/admin/feedback`.
- **Beta Dashboard** (`/admin/beta`) — admin-guarded: activation overview (DAU/WAU/MAU, activation/retention/crash-free rates, 14d activity), activation funnel, custom step-funnel with drop-off %, weekly retention cohort matrix, most-used features ranking, session list + per-session event replay timeline, crash signatures grouped by key, feedback triage table.
- **Admin analytics API** — `/api/v1/admin/analytics/{overview,funnel,retention,features,sessions,crashes}` + `/sessions/{id}/events`, all `require_admin`; anonymous ingest `POST /api/v1/analytics/track-batch` (fail-open, CSRF-protected).
- **Weekly analytics reports** (`infra/scripts/analytics_report.sh`) — generates `docs/weekly/<W>/06-funnel, 07-activation, 08-retention, 09-most-used-features, 10-drop-off, 11-most-requested-features` from remote Supabase; W31 baseline authored with real data.

### Changed
- `AnalyticsService` rewritten DB-first (in-memory fallback keeps ingest fail-open); `v1_feedback.py` DB-backed; `core/deps.py` adds `get_optional_user`; test mocks use the service module's imported `get_supabase`/`async_supabase` references.

### Verification
- API regression: **562 passed, 1 xfailed** (11 new analytics tests).
- Web: `tsc --noEmit` clean; prod build clean.
- Deployed hot to prod; in-container smoke (auth + CSRF): track-batch 200/accepted, all 6 admin endpoints 200, feedback submit + triage, session replay, admin event filter — **ALL PASSED**; smoke rows cleaned.
- New web BUILD_ID served on prod.

## v1.0.0 (2026-08-01) — GENERAL AVAILABILITY

### GA Preparation (production readiness — no new features)

### Added
- **Single-command production deploy** (`infra/production/deploy.sh`) — non-interactive: installs Docker/Compose if missing, `git reset --hard origin/main` (repo = sole source of truth), env-file guard, OpenRouter key injection only when explicitly provided, DNS advisory, `build --parallel api web`, `up -d`, health gates on API `/health` + web (18×10s), clear failure tips, `Deployment Complete — v1.0 GA` banner. Validated E2E on prod from a fresh `origin/main` checkout.
- **Verified backup pipeline** (`infra/scripts/backup.sh`) — Redis RDB via `redis-cli SAVE`; Prometheus consistent TSDB snapshot (admin API, zero downtime); Grafana/n8n/Caddy via brief stop + tar of their `production_*` volumes; env-file copy; 14-day retention; every archive `tar tzf`-verified (exit 1 on any failure). E2E: all components `[OK]`, 49M verified.
- **Prometheus admin API enabled** — `--web.enable-lifecycle` + `--web.enable-admin-api` in the production compose (Prometheus 3.x split the flags; required for snapshot-based backups). Force-recreated container; snapshot verified (`20260801T082220Z-…`).
- **Remote Supabase fully migrated** — `20250731_01100_builder_persistence.sql` + `20250801_01200_backtest_persistence.sql` applied to `db.nwutlfuowiulfpbsrldn.supabase.co` (PostgreSQL 17.6): `builder_strategies`, `builder_strategy_versions`, `builder_strategy_logs`, `backtest_runs`, `candles`, `corporate_actions` all created (RLS on, service-role bypass). Verified post-restart: 7 strategies / 2 runs / 533 candles persisted.
- **Restart persistence verified (prod)** — builder strategy (status `ready`), COMPLETED backtest run, lifecycle logs and version history all survive an API restart; OMS recovery confirmed ("Recovered 1 active orders…").
- **GA docs** — `DEPLOYMENT.md` (rewritten, single-command), `DISASTER_RECOVERY.md` (rewritten, RPO/RTO + scenarios), `BACKUP_RESTORE.md` (new), `RUNBOOK.md` (refreshed), `RELEASE_NOTES.md` (rewritten for GA), `KNOWN_ISSUES.md` (new), `UPGRADE_GUIDE.md` (new).

### Changed
- **Backtest data reliability** (`backtest/manager.py`, `backtest/data_loader.py`, `market/historical.py`) — run-v3 now propagates `user_id` to the data loader at both call sites (previously loaded zero candles); the auto source routes through the durable candle store (`backtest_historical.load`: Supabase-first, gap-fill, write-back) instead of broker-only; Yahoo fallback (`^NSEI` etc.) engages when creds are absent/expired/fetch fails/`not user_id`. Backtests complete without any broker credentials.
- **Repo made authoritative** — 112-file backlog (Phases 4.3–6) committed (`f88d300`) and pushed to public GitHub `main`; verified zero tracked secrets (`.env*` gitignored); VPS repo now `git reset --hard origin/main` (env files survive as untracked).
- **Deployment UX** — old interactive `read -rp "Enter your OpenRouter API key"` paths removed (they aborted non-TTY deploys); backup archives no longer truncated (`tar -C /v .` only, stopped-container tar for sqlite-backed volumes).
- **reportlab baked** — 5.0.0 and all runtime deps verified in a clean `--no-cache` image build; fresh containers need zero manual post-install.

### Verification
- Full API regression: **551 passed, 1 xfailed**.
- Web: `tsc --noEmit` clean + prod build clean.
- Deploy E2E from `git reset --hard origin/main`: images built, api+web healthy (200), GA banner, exit 0.
- Backup E2E: all components verified (`[DONE] Backup complete and verified`), exit 0.
- Persistence smoke post-deploy-restart: `strategies=7, runs=2, candles=533` in remote Supabase.

### Known gaps
- See `KNOWN_ISSUES.md` (Fyers token re-auth, TRADINGVIEW_WEBHOOK_SECRET unset, Telegram stubs, service-role keys, single-host footprint, on-VPS-only backups).

## v0.2.0-rc.7 (2026-08-01)

### Phase 6 — Product Polish (Accessibility, Consistency, Performance Audit)

### Added
- **Audit + Improvement Plan** (`docs/evolution/PHASE6_PRODUCT_POLISH.md`) — full survey of 63 pages + 42 components with four reports: UX (dead header tabs, fake search div, hardcoded `v0.1`, duplicate nav, toast/inline-success inconsistency, empty-state drift, no error boundary), Performance (84.6 kB shared JS, 9 polling intervals all cleaned, no RSC/streaming/dynamic chunks), Accessibility (A1–A9), Visual Consistency (≈100 hardcoded hexes, ~340 buttons without `type` — deferred).
- **Skip-to-content link** — visible-on-focus `Skip to content` in the app shell targeting `#main-content` on the content container (keyboard-first navigation).
- **Real search button** — global search trigger is now a `<button data-search-open aria-label="Search symbols, strategies, pages (⌘K)">` (was a non-focusable `<div>`).
- **Search overlay dialog semantics** — overlay is now `role="dialog"` + `aria-modal="true"` + `aria-label`, with a Tab focus trap while open and focus restored to the trigger on Escape (only when focus was inside the overlay).
- **Dropdown a11y** — notifications + profile popovers: `role="menu"`, `aria-label`, `aria-expanded`, `aria-controls` (ids `notifications-popover`/`profile-popover`); `aria-current="page"` on active nav links; `aria-label` on sign-out, theme-toggle, sidebar collapse/expand icon buttons.
- **Root error boundary** — `app/error.tsx` (Try again + Back to Dashboard, dev-only error dump) and `app/not-found.tsx` (friendly 404 with dashboard link) — the app previously had zero `error.tsx` files anywhere.
- **Real app version** — header badge and portal footer now render `AppVersion`/`getAppVersion()` (env-driven) instead of hardcoded `v0.1`.
- **Toast a11y** — toast container `role="status"` + `aria-live="polite"`; each toast item `role="alert"`.

### Changed
- **Contrast fixes** — dark-theme `--text-faint` `#5b5875` → `#7d79a0` (~2.5:1 → 4.5:1); light-theme `--text-faint` `#9aa0a6` → `#757580`; `error-message.tsx` `#ef4444` → `var(--text-red)`.
- **Color literal sweep** — `#ef4444` → `var(--red)` (6 files incl. portal, strategies/catalog, admin beta/broadcast, strategy-builder types, equity-curve); `#555570`/`#8888a0` → `var(--text-faint)` (5 files).
- **Dead code removed** — `apps/web/components/header.tsx` deleted (zero imports; duplicated the app-shell header with non-functional tabs + hardcoded version).
- **Dashboard tabs already lazy-loaded** — verified all 11 admin tabs use `next/dynamic(..., { ssr: false })`; no change needed.

### Verification
- Per-batch: `npx tsc --noEmit` exit 0 after B1/B2/B3; prod `npm run build` clean after every batch.
- Full API regression: **549 passed, 1 xfailed** (API untouched by Phase 6 — baseline unchanged).
- Prod deploy (web only): new BUILD_ID manifest served, `/backtest` 200, `/dashboard` HTML contains skip-link target, `aria-current="page"`, `data-search-open`, and the new search `aria-label`.

### Known gaps
- ~340 buttons still missing explicit `type="button"` (deferred; visual/behavioral risk low, churn high).
- Remote Supabase migration still blocked (placeholder DB password) — unchanged from rc.6.
- Search results list keyed to marker but not yet indexed as a full `combobox` pattern (overlay + focus management shipped in this phase).

## v0.2.0-rc.6 (2026-08-01)

### Phase 5 — Institutional Backtest Engine (Build → Backtest → Optimize → Deploy)

### Added
- **Backtest costs module** (`backtest/costs.py`) — Indian-market cost model: brokerage (₹20 flat equity/options/intraday, ₹20 flat futures, min ₹20), STT (0.1% delivery, 0.025% intraday/futures, 0.0625% options sell-side), exchange transaction charge (0.00297% non-agg F&O, 0.003% equity), SEBI charges, stamp duty (0.003% delivery, 0.02% derivatives), GST. `estimate_cost` returns a segmented breakdown per trade; `estimate_round_trip`; configurable override knobs.
- **Durable candle store** (`backtest/historical.py` + migration `20250801_01200_backtest_persistence.sql`) — `candles`, `corporate_actions`, `backtest_runs` tables in Supabase. `BacktestHistoricalData` loads DB-first, gap-fills from the broker, and write-throughs best-effort (fail-open to in-memory). Corporate-action adjustment (split/bonus price scaling) applied at load; continuous-futures contract stitching (`-CONT`) with proportional back-adjustment on roll.
- **BacktestBroker + realistic fill engine** (`backtest/execution.py`) — MARKET fills at close ± slippage, LIMIT trade-through with expiry, SL/SL-L trigger-then-limit, SL-M trigger, seeded partial fills, fill latency measured in candles. Broker exposes the same contract as PaperBroker and plugs into `ExecutionManager._adapters` as a fake `backtest:{run_id}:paper` user — zero OMS/broker changes.
- **Manager MAX-speed path** (`backtest/manager.py`) — broker-direct replay loop (no portfolio manager): broker `on_candle` before strategy, risk dry-run checks when enabled, position close-out at the end, per-candle snapshots, in-memory trade recording with entry/exit times. Results persisted to `backtest_runs` at completion; `get_run` restores from DB when the in-memory run is gone (restart-safe).
- **Performance extensions** (`backtest/performance.py`) — expectancy & expectancy-per-R (R = average loss), average/median risk-reward ratio, weekday/hour/month trade distributions, and 252-day annualized alpha/beta vs a benchmark (benchmark candles passed from the manager).
- **Optimizer** (`backtest/optimizer.py`) — grid search (≤512 combos), walk-forward (6 windows, train-prior-fold/test-current-fold), Monte Carlo (2000 bootstrap paths over trade PnLs → p5/p25/p50/p75/p95, mean, probability of profit), and OFAT ±20% sensitivity. Lean `_fast_run` path with `candle_slice` support so folds don't reload data.
- **run-v3 route** — backtest any builder (DSL) strategy by `strategy_id`; compiles + validates the DSL, runs it as `GraphStrategy` (same runtime as paper/live), returns the full Phase-5 metrics superset.
- **Compare + exports** — `POST /backtests/compare` (up to 10 run IDs); `GET /backtests/{run_id}/export?format=json|csv|pdf` (reportlab landscape A4 report).
- **Deploy-to-paper** — `POST /backtests/{run_id}/deploy-to-paper` starts the backtested builder strategy in paper mode via the existing graph runner.
- **Data endpoints** — `GET /backtests/candles/{symbol}/{interval}` (durable store read) and `GET/POST /backtests/corporate-actions` (adjustment ingestion).
- **Web UI** (`apps/web/app/backtest/page.tsx` rewrite) — built-in or builder (DSL) source selector, run form (slippage/latency/partial-fill/risk), 14-metric KPI grid (expectancy, expectancy/R, RR ratios, alpha/beta, sortino, calmar), equity + drawdown SVG charts, weekday/hour/month distributions, weekday×hour P&L heatmap, server optimizer tab (grid/walk-forward/Monte Carlo/sensitivity with best-combo highlight), compare-runs tab, trade log, one-click JSON/CSV/PDF export and deploy-to-paper.

### Changed
- `apps/api/backtest/models.py` — `BacktestConfig` gained `strategy_id`, `user_id`, `candle_slice`, `slippage_pct`, `latency_candles`, `partial_fill_probability`, `seed`, `cost`; `strategy_type` now defaults to `""`; `BacktestResult` gained the Phase-5 metric fields.
- `apps/api/replay_engine.py` — optional `broker`/`risk_check`/`bt_user_id` parameters (back-compat kept).
- `apps/api/requirements.txt` — `reportlab>=4.0`.
- `apps/web/lib/api.ts` — `api.backtest` gained `runV3`, `optimize`, `getOptimize`, `compare`, `exportJson/Csv/Pdf`, `deployToPaper`, `candles`, `corporateActions`, `addCorporateAction`; `backtestExportUrl` helper for binary downloads.

### Verification
- Unit: 55 new tests (`test_backtest_{costs,historical,execution,performance,optimizer,routes_v3}.py`). Full suite **549 passed, 1 xfailed** — baseline 485 + 64 Phase-5 tests, no regressions.
- Local Supabase: migration `20250801_01200_backtest_persistence.sql` applied; PostgREST 200 on `candles`, `corporate_actions`, `backtest_runs`.
- Prod (api.ai.trademetrix.tech, authenticated): **20/20 smoke checks** — builder strategy created → run-v3 (DSL backtest, all new metrics present) → get run → JSON/CSV/PDF exports (PDF is valid %PDF bytes) → compare → deploy-to-paper (runner started, then stopped cleanly) → candles endpoint returns data → corporate-actions list 200. Web: new build served (BUILD_ID rotated, `/backtest` 200, chunk contains new UI).

### Known gaps
- Remote Supabase migration still blocked (placeholder DB password) — `backtest_runs`/`candles`/`corporate_actions` persistence on prod is fail-open (in-memory + broker fetch) until the migration can be applied; `POST /backtests/corporate-actions` needs the remote table.
- Prod container needed `docker exec -u root pip install --ignore-installed reportlab` (PIL owned by root) — the image doesn't bake it in yet.

## v0.2.0-rc.5 (2026-08-01)

### Phase 4.3 — Strategy Lifecycle Management (Strategy Builder V2 → full lifecycle)

### Added
- **Version control** — every save of name/nodes/edges/settings snapshots a version (v1, v2, …) into `builder_strategy_versions` (capped at 50, ring-buffer in memory, write-through to Supabase). Restore rolls back any version to a NEW version number (history is never rewritten). Version diff (`/compare`) shows added/removed/changed nodes, edges, params and settings between any two versions.
- **Lifecycle statuses** — `draft → validated → ready → paper/live → stopped → archived` with `published` kept as a legacy alias so existing publish/start routes keep working. Validate promotes draft→validated; the new Ready button marks a strategy deployable; deploy sets paper/live; stop sets stopped; archive is reversible only via clone.
- **Deployment wizard** — paper/live mode (fail-closed: live REQUIRES a broker), symbol, interval, capital, risk (risk-per-trade %, max daily loss, SL %, target %) and schedule (trading days, start/end time, Asia/Kolkata). Persisted as a `deployment` JSONB on the strategy and honored by the runner (mode drives `is_paper`).
- **Validation score** — 5-metric scorecard (quality, risk, complexity, readability, readiness) with overall %, A–F grade and a per-metric breakdown, computed from the compiled graph (`/score`).
- **Strategy logs timeline** — lifecycle (deploy/stop/ready/archive), validation results, signal decisions, order placements, rejections and runner errors recorded per strategy (in-memory ring 500 + write-through to `builder_strategy_logs`); auto-refreshing panel in the builder and pollable via `/logs`.
- **Execution dashboard** — `/strategies` page now shows all running graph strategies with health (ok/degraded), symbol/interval/mode, candles/signals/orders/filled/rejected/errors counters, realized PnL (read-only estimate from the orders audit table — no OMS writes), and a deep link into the builder. Auto-refreshes every 5 s.
- **Runtime instrumentation** in `engine/graph_strategy_runner.py` — per-strategy runtime stats, lifecycle/signal/order/rejection log records, latency tracking, and `get_runtime_dashboard()`/`get_running_strategies()`.
- **Template categories** — `list_templates` now returns the `official` category tag per template.

### Changed
- `apps/api/builder/manager.py` — version-on-save, `get_version`/`get_versions`/`compare`/`set_status`, deployment persistence; module-level `_snapshot_version` (ring-buffer helper).
- `apps/api/routes/v1_builder.py` — new routes: `/ready`, `/deploy` (DeployStrategyRequest with RiskDeployRequest + ScheduleDeployRequest), `/score`, `/logs`, `/compare`, `/dashboard`; validate/start/stop/publish/archive/clone/rollback are lifecycle-aware (status transitions + log records).
- `apps/web/lib/api.ts` — `api.builder` gained `ready`, `deploy`, `score`, `logs`, `compare`, `dashboard`; `start` accepts `mode`.
- `apps/web/app/strategies/builder/page.tsx` — status chips (live/paper/stopped/ready/validated/draft/archived), Versions button, Ready button, working Deploy wizard, validation score panel and auto-refreshing logs panel.
- `apps/web/app/strategies/page.tsx` — live Execution Dashboard section with per-strategy health/orders/PnL.
- `apps/web/components/workspace/strategy-builder/` — new `deploy-wizard.tsx`, `versions-drawer.tsx`, `strategy-score.tsx`, `strategy-logs.tsx`.
- `supabase/migrations/20250731_01100_builder_persistence.sql` — added `builder_strategy_logs` table + `deployment` JSONB column (applied to local Supabase; remote apply still blocked on Supabase DB password).
- `apps/api/middleware/csrf.py` — the INC-013 cookie-rotation fix was present locally but the deployed container still ran the old pre-fix version (cookie was set only on the first request → body token rotated on every `/auth/csrf` while the cookie never updated → every POST after the first returned 403 "CSRF validation failed"). Re-deployed the fixed middleware; rotation now verified live.

### Verification
- Unit: 9 new lifecycle tests (`tests/test_builder_lifecycle.py`) — every-save-snapshots, compare, rollback-bumps-version, rename, status transitions, deployment roundtrip, score structure, logs, template categories. Full suite **494 passed, 1 xfailed** (baseline 485 + 9 new, no regressions).
- Integration (local HTTP): 19-step lifecycle smoke — create → validate (promotes) → ready → deploy paper (persists deployment) → live-without-broker rejected → save creates v2 → compare → score (A) → logs (lifecycle+validation) → dashboard (running=1) → stop → status stopped. All green.
- Restart persistence (local Supabase): strategy written in process A (name v2, ready, paper deployment, ≥2 versions) fully restored in fresh process B.
- Prod (api.ai.trademetrix.tech): full lifecycle via authenticated API — create → validate → ready → deploy paper (runner "subscribed to live tick feed" for NIFTY) → dashboard shows 1 running → stop clean → status stopped. Web: new build served (BUILD_ID rotated, `/strategies` 200).

### Known gaps
- `builder_strategies`, `builder_strategy_versions`, `builder_strategy_logs` tables still MISSING on the prod Supabase (migration blocked on the placeholder DB password) — strategies survive only in-memory on prod; write-through persistence activates automatically once the migration is applied.

## v0.2.0-rc.4 (2026-07-31)

### Phase 3 — Unified Trading Intelligence (`/workspace`)

### Added
- **Universal symbol context** — one active symbol drives the chart, action bar, position card, analyzer, option chain and alert modal (`lib/stores/ui-store.ts`); switching anywhere re-syncs everything.
- **Chart action bar** — BUY / SELL / 🔬 Analyze / ☰ Option Chain / 🤖 Strategy / 📈 Backtest / 🔔 Alert / 📓 Journal for the active symbol.
- **Position intelligence card** (bottom-left tab) — LONG/SHORT + qty, live P&L + %, entry/current/SL/TARGET (OMS auto-bracket defaults −10%/+15%)/RISK/REWARD/RR/product grid, holding time from first fill, actions: Modify (pre-filled drawer), Exit (MARKET close via engine `source:exit_sl`, no cascading brackets), Reverse, Scale In, Scale Out.
- **Order timeline** (bottom-right tab) — Requested → Validated → Sent → Accepted → Filled → Completed mapped from OMS statuses, with rejection reason chips for REJECTED/CANCELLED/EXPIRED.
- **AI trade summary** in the analyzer — rule-based bias (RSI/VWAP/MACD/structure/PCR votes), ADX momentum, risk grade, confidence %, suggested stop/target from S/R levels; explicit "analytics only, not a trading signal" disclaimer.
- **Universal search** — ⌘K / Ctrl+K palette across recents, symbols, positions, orders, alerts, strategies and quick actions, with keyboard navigation.
- **Notifications center** (top bar bell) — order filled/rejected, position closed, broker token invalidated/removed, market feed down/up, strategy started/stopped; unread badge, persist up to 60 events in `localStorage`.
- **Workspace persistence** — active symbol, analyzer/chain open state, bottom tab, chart interval, drawer prefs (paper/product/order type) and recents survive reload (`tm_ws_prefs`, `tm_drawer_prefs`, `tm_recent_symbols`).
- **Option chain slide-over** — CE/PE LTP + OI per strike, ATM highlight, PCR header, per-row Buy/Sell into the drawer (lazy chunk).

### Changed
- `components/chart.tsx` — controlled `interval` + `onIntervalChange` props; chart wrapped in clipped container so the canvas can't intercept panel clicks.
- `components/quick-order-drawer.tsx` — drawer prefs persisted + `prefillQty` support.
- `components/workspace/top-bar.tsx` — search/notifications slots; `watchlist-panel.tsx` reuses shared `alert-modal.tsx`.
- New: `chart-action-bar.tsx`, `position-card.tsx`, `order-timeline.tsx`, `command-palette.tsx`, `notifications-popover.tsx`, `option-chain-panel.tsx`, `alert-modal.tsx` (shared).
- Fixed during verification: React #185 (workspace restore effect depended on whole zustand state → infinite update loop), React #425/#418 hydration (store no longer reads localStorage at module init; prefs applied post-mount; chart height mount-gated), palette dropdown now closes on blur/Escape without blocking the action bar, legacy ⌘K search overlay disabled on `/workspace` (was covering the bottom tabs), `/auth/me` retried 3× before redirecting to `/auth` (transient API burst on cold load), palette data fetched once on mount with `useMemo` hits (was refetch-looping when the host passed unstable callbacks), palette symbol hits normalized to `NSE:` full keys, palette symbol pool seeded from the watchlist feed (production `/market/instruments` catalog is empty until the 02:30 UTC symbol-master sync, and upstream Fyers/NSE symboldumps are unreachable from the VPS — watchlist gives a live, real symbol catalog).
- `infra/production/docker-compose.yml` — API service `ulimits.nofile` raised to 65535 (container was exhausting the 1024 default at ~1021 fds → `[Errno 24] Too many open files` in `core.safe_query`).

### Regression
- `tsc --noEmit` clean; `next build` clean (`/workspace` 17.5 kB, first load 177 kB). Headless Chromium on prod (minted JWT): action bar, ⌘K palette (focus + symbol search via watchlist catalog), option chain, analyzer + TRADE SUMMARY + AI, position tab, timeline stages, notifications, and persistence (active symbol + bottom tab restored — asserted on the active-tab class) all pass. PAGE_ERRORS = 2, all pre-existing chart color-mix parse warnings (no React errors, no 503s); /portfolio /marketdata /trade /portal /dashboard regressions all 0. Screenshots 08–14 in `/root/web-verify/`. Position card verified in its empty state (`No open position`); the filled card (LONG + ENTRY/CURRENT/RISK/REWARD/RR + Modify/Exit/Reverse/Scale) is pending the live Fyers re-auth click (token expired 2026-08-01 00:30 UTC, positions feed returns empty until then).



### Phase 2 — Trading Workspace V2 (`/workspace`)

### Added
- Single-screen trading workspace at `/workspace` (standalone, no admin chrome):
  - **56px icon sidebar** (Home/Trade/Analyze/Automate/Portfolio/Settings) with active-state highlighting.
  - **Top bar** — LIVE/SIM feed status, broker + token status chip (RE-AUTH NEEDED when expired), symbol search with dropdown results (navigates chart), alert count badge with notification shortcut.
  - **Watchlist panel** (left, 238px) — groups (All/Intraday/Options/Stocks/Swing/ETF) persisted in `localStorage` (`tm_watchlist_groups`), pinned favorites (`tm_watchlist_favs`, sort-to-top), filter box, per-row LTP / % / OI / Volume / Trend / mini sparkline / actions (Buy/Sell/🔬/🔔/★). Windowed rendering (only visible rows mounted), sparkline data fetched lazily for visible rows (5m candles, cached per session). Single-click syncs the chart; double-click opens the order drawer. Add-symbol modal with searchable catalog + free-text entry; in-row price-alert modal (crosses above/below, via `POST /alerts/`).
  - **Center chart** — reuses existing `components/chart.tsx`, re-keyed by active symbol.
  - **Analyzer side panel** (right of chart, `next/dynamic` lazy chunk, opened via 🔬 on a row or the market panel) — live price, VWAP, EMA 9/21, RSI 14, MACD/Signal/Hist, ADX, PCR (from option chain), swing structure (HH/HL/LH/LL), SMC support/resistance levels, risk-to-support + RR chips, rule-based AI summary, and Trade / Backtest / Strategy actions (Trade opens the drawer).
  - **Market panel** (right, 268px) — VIX live + change, PCR, OI bias (CE-PE near ATM), S/R levels from 15m swing data, gainers/losers from the live tick pool, AI summary with bullish/bearish/neutral verdict.
- Quick Order Drawer **collapsible Advanced section** (collapsed by default): SL % / Target % (drive the auto-protection preview), trailing-SL toggle + step, risk-per-trade %, capital, expected RR, risk amount vs capital %, estimated margin (client-side placeholder). Order payload is unchanged from Phase 1.

### Changed
- `components/workspace/` — new `indicator.ts` (pure EMA/RSI/MACD/ADX/VWAP/swings/trend/ai-summary), `mini-chart.tsx`, `sidebar.tsx`, `top-bar.tsx`, `watch-row.tsx` (memoized), `watchlist-panel.tsx`, `market-panel.tsx`, `analyzer-panel.tsx`.
- `components/quick-order-drawer.tsx` — Advanced section + SL/Target % now feed the protection preview.
- `CHANGELOG.md` — this entry.

### Regression
- `tsc --noEmit` clean; `next build` clean; `/workspace` route emitted (14.4 kB, analyzer as separate lazy chunk). Headless Chromium on prod (Playwright, minted JWT): sidebar/topbar/groups/market panel all render, 22 watch rows with B/S/🔬/🔔/★ actions, single-click chart sync, double-click opens drawer, Advanced collapsed by default and expands, analyzer computes RSI/MACD/ADX/VWAP/SMC levels + AI summary with real data, 0 page errors on /portfolio /marketdata /trade /portal regression. Expected-only console noise: option-chain 503 for index symbols (no chain exists) and pre-existing chart color-mix parse warnings.

# Changelog

## v0.2.0-rc.2 (2026-07-31)

### Portfolio Home (new user landing)

### Added
- New `/portfolio` page — user home with: Today's P&L (live unrealised from open positions at current market prices + FIFO-estimated realised today from fills), Broker Status (credentials, active flag, token status + expiry countdown), ⭐ Watchlist with per-symbol Buy/Sell wired to the Quick Order Drawer, Recent Orders, Open Positions, and Market Summary index cards. Live ticks via the existing market feed; auto-refresh via react-query hooks.
- `/portfolio` registered as a standalone route; non-admin users now land here after sign-in (previously `/portal`); landing-page CTAs repointed to `/portfolio`.

### Fixed
- Hydration mismatch on `/portfolio` (React #425/#418/#423): greeting/date now mount-gated so SSR (UTC build-time) matches the client's first render.
- Deploy path bug: `app-layout.tsx` was staged flat into `apps/web/` instead of `components/`, silently leaving the old layout live.

### Regression
- `tsc` clean, `next build` clean, deployed to prod. Headless Chromium verification: all six sections render, 12 Buy + 12 Sell actions, drawer opens from the portfolio watchlist, 0 page errors, no admin sidebar on the standalone page.

# Changelog

## v0.2.0-rc.1 (2026-07-31)

### Phase 1 — Quick Order Drawer (TradeMetrix OS)

### Added
- Global quick-order drawer (`components/quick-order-drawer.tsx`) mounted in the root layout, reachable from any page.
- BUY / SELL quick actions on every Market Data watchlist row (opens the drawer pre-set to that side).
- Drawer features: live LTP + change from the market feed, lot-aware quantity stepper (NIFTY 65 / BANKNIFTY 30 / FINNIFTY 60 / SENSEX 20 / MIDCPNIFTY 75), MARKET/LIMIT order type, INTRADAY (MIS) / NRML product, PAPER / LIVE mode toggle (PAPER default), auto-protection preview (SL −10% / Target +15% from entry, mirrors backend auto-bracket), notional + estimated charges, Esc/backdrop to close.
- Order submission reuses `POST /api/v1/engine/trade` with `is_paper` + `source='quick_drawer'`; success invalidates orders / positions / funds queries.

### Changed
- `lib/api.ts` — `engine.trade` payload type extended with `is_paper` / `source`.
- `lib/stores/ui-store.ts` — added `quickOrder` state + `openQuickOrder` / `closeQuickOrder` actions.
- `styles/components.css` — new drawer primitives (`t-drawer-overlay`, `t-drawer`, `t-drawer-header/body`, `t-drawer-label`, `t-seg`, `t-seg-btn`, `t-stepper`).
- `app/marketdata/page.tsx` — Buy / Sell quick actions added to watchlist rows.

### Regression
- `tsc --noEmit` clean, `next build` clean, deployed to prod, drawer compiled into root layout chunk, Buy/Sell into marketdata chunk, page serves 200.

# Changelog

## v0.1.0-rc.1 (2026-07-28)

### Release Candidate 1 — Production Readiness Validation

### Features Verified
- Fyers OAuth login flow (token exchange, encryption, storage)
- Token refresh and expiry handling
- Broker credentials management (create, list, delete)
- Kill switch (enable, disable, status, survives restart)
- Order placement (MARKET, LIMIT, SL, SLM) via paper broker
- Order modification and cancellation
- Position tracking with cross-restart persistence
- Portfolio P&L computation
- Strategy lifecycle (create, deploy, start engine, execute signal)
- Risk engine (market hours, trading window, cooldown, duplicate, kill switch)
- RBAC (admin, user, blocked roles)

### Fixed since previous sessions
- **CSRF race condition** — middleware now stores token on request.state instead of double-cookie
- **Subscription table column mismatch** — code reads `plan` column with fallback to `tier`
- **Order lifecycle** — `NormalizedOrder.insert` field cleaning for empty `id`
- **Paper order risk exemptions** — `MarketClosedRule`, `TradingWindowRule`, `TradeCooldownRule`, `DuplicateOrderRule` now skip for `is_paper=True`
- **Execution manager paper routing** — `_get_adapter()` uses `"paper"` when `req.is_paper` is True
- **PortfolioManager position access** — dict-model safe access in `_sync_positions`
- **Strategy signal validation** — `EngineService.execute_trade()` now sets `is_paper=True` for active PAPER runs
- **Broker resolution for paper trades** — `gate.py` uses `"paper"` broker directly when `order.is_paper` is True
- **Cross-restart position recovery** — `PaperBroker._restore_positions()` reconstructs from filled orders on `connect()`
- **UserStrategyRunner TypeError** — `days_of_week` string/list parsing fix in `_check_square_off()`
- **Engine positions/funds routing** — checks for active PAPER run before querying live broker

### Known Issues
- Fyers token expires ~24h, no refresh_token — user must re-auth (broker limitation)
- Sentry DSN not configured
- Strategy `user_strategies` table has FK constraint requiring direct SQL insert for new strategies
- Marketdata option-chain returns 503 (external API limitation)
- Rate limiter has 60s cooldown after ~40 requests