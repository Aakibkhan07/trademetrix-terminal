import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, it } from "node:test";

/**
 * `app/dashboard/admin-content.tsx` had three components whose `msg` was a bare string and whose
 * colour was picked by substring matching:
 *
 *     msg.includes('saved') || msg.includes('success') ? green : red
 *     msg.includes('expired') ? red : green
 *     msg.includes('fail')    ? red : green
 *
 * Two of those paint anything not containing the word "fail" in green, and every `catch` block does
 * `setMsg(e.message)` — so a failed request whose wording was "Could not reach broker" or a 401 body
 * rendered as a success. Measured separately: with zero Fyers credentials the panel said
 * "All tokens valid" in green above its own "No Fyers credentials found."
 *
 * The browser check `scripts/browser/verify_admin_msg_tone.js` covers the empty-state branch by
 * measurement, but it cannot reach the error branch — validate succeeds, so no `catch` runs, and a
 * mutation that set `tone: 'ok'` inside the catch passed it. That limit is why these source
 * assertions exist: the error direction has no cheap measurement, only the invariant.
 */

const SOURCE_PATH = path.join(process.cwd(), "app", "dashboard", "admin-content.tsx");
const source = readFileSync(SOURCE_PATH, "utf8");

/** Strip comments so a historical explanation cannot satisfy — or break — an assertion. */
// The `s` flag is not available at this project's compile target, so dot-all is spelled out.
const code = source
  .replace(/\/\*[\s\S]*?\*\//g, "")
  .replace(/^\s*\/\/.*$/gm, "")
  .replace(/\/\/[^\n]*$/gm, "");

const lines = code.split("\n");

describe("admin-content message severity", () => {
  it("never infers severity from the words in a message", () => {
    // Matched on the shape rather than on the variable name. The first version looked for
    // `msg.includes(`, and a mutation writing `msg.text.includes('expired') ? red : green` sailed
    // straight through it — the defect returned under a different receiver and the guard said
    // nothing. What matters is that no colour is chosen by a substring test, whoever it is called.
    const offenders = lines
      .map((l, i) => ({ l, n: i + 1 }))
      .filter(({ l }) => /\.includes\([^)]*\)[^\n]*\?[\s\n]*['\"]var\(--(red|green|amber)/.test(l));
    assert.deepEqual(
      offenders.map((o) => `${o.n}: ${o.l.trim()}`),
      [],
      "severity must be carried by an explicit tone, not by substring matching",
    );
  });

  it("has no bare-string setMsg left, so a tone cannot be forgotten", () => {
    // setMsg('') and setMsg('text') carry no tone at all. The null reset is the only string form left.
    const offenders = lines
      .map((l, i) => ({ l, n: i + 1 }))
      .filter(({ l }) => /setMsg\((?!null)/.test(l) && !/setMsg\(\{/.test(l));
    assert.deepEqual(
      offenders.map((o) => `${o.n}: ${o.l.trim()}`),
      [],
      "every setMsg must pass an object with a tone",
    );
  });

  it("tones every error message as an error", () => {
    // A catch block is what these lines are; the browser check cannot reach them.
    const catchSites = lines
      .map((l, i) => ({ l, n: i + 1 }))
      .filter(({ l }) => /setMsg\(\{[^}]*(instanceof Error|'[^']*failed'|"[^"]*failed")/i.test(l));
    assert.ok(catchSites.length > 0, "expected the catch blocks to still be here");

    const wronglyToned = catchSites.filter(({ l }) => !/tone: 'error'/.test(l));
    assert.deepEqual(
      wronglyToned.map((o) => `${o.n}: ${o.l.trim()}`),
      [],
      "an error message rendered green is worse than no message — it says the write path works",
    );
  });

  it("reports zero credentials as nothing-to-check rather than as a pass", () => {
    assert.match(
      code,
      /results\.length === 0/,
      "the empty-result branch is gone, so [] falls through to an all-valid message again",
    );
    assert.match(code, /No Fyers credentials to validate/);
    // and the all-valid branch must name the count, so it cannot describe a set of zero
    assert.match(code, /All \$\{results\.length\} token\(s\) valid/);
  });

  it("gives each of the three panels a typed message", () => {
    const declared = code.match(/const \[msg, setMsg\] = useState<\{/g) || [];
    assert.equal(
      declared.length,
      3,
      "three panels render a message; each needs the tone carried in its state type",
    );
  });
});
