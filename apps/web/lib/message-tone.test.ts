import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { describe, it } from "node:test";

/**
 * No colour anywhere in the app may be chosen by matching words in a message.
 *
 * ## What this replaces
 *
 * Eight sites did this, across three files, in three different shapes:
 *
 *     msg.includes('saved') || msg.includes('success')   ? green : red
 *     msg.includes('expired')                           ? red   : green
 *     msg.includes('fail')                              ? red   : green
 *     batchMsg.includes('fail')                         ? red   : green
 *     assignMsg.includes('Failed') || includes('fail')  ? red   : green
 *     e.action?.includes('error') || ... (four tests)
 *     msg.includes('symbol')                            ? red   : green
 *     deployMsg && !deployMsg.includes('Error')         ? green : red
 *
 * The dangerous direction is that **the `catch` block decides the wording**. `setMsg(e.message)`
 * puts whatever the server said in there, and a server reporting a failure does not have to write
 * "Error" or "fail" to do it — "Could not reach broker", "Strategy not found" and "INSUFFICIENT_MARGIN"
 * all rendered green, next to the button that had just failed.
 *
 * `app/alerts/page.tsx` was the worst of them: the test was whether the message mentioned the word
 * "symbol", and that panel has no success message at all, so its green branch was unreachable by any
 * correct behaviour. It only ever painted a failure.
 *
 * ## Why this walks the whole app
 *
 * The first version of this guard read one file and found six of the eight. The two on other pages
 * only turned up when the same shape match was run across `app/` and `components/` — a guard scoped
 * to the file you happen to be editing is a guard scoped to your luck.
 *
 * ## Why it matches on shape, not on a variable name
 *
 * The first version looked for `msg.includes(`. A mutation writing
 * `msg.text.includes('expired') ? red : green` sailed straight through it. What matters is that a
 * colour is chosen by a substring test, whoever the receiver is called.
 *
 * ## What this deliberately does NOT assert
 *
 * An earlier draft also forbade bare-string message state. That was wrong in principle, not just
 * awkward: `app/settings/page.tsx` and `app/account/page.tsx` keep severity in a **sibling** state
 * (`setPwMsgType('error')`), which is the correct pattern, and the heuristic flagged 27 call sites
 * across four files because a file containing `useState('')` for something unrelated — a search box —
 * made all of its message setters look bare. A guard that produces 27 false positives is worse than no
 * guard, so it was deleted rather than tuned. The single assertion below is the one that is actually
 * a defect, and it is the one that found the eight.
 */

const ROOT = process.cwd();
const SEARCH_DIRS = ["app", "components"];

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) {
      walk(full, out);
    } else if (/\.tsx$/.test(entry)) {
      out.push(full);
    }
  }
  return out;
}

/** Comments are stripped so a historical explanation cannot satisfy — or trip — an assertion. */
function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "")
    .replace(/\/\/[^\n]*$/gm, "");
}

const files = SEARCH_DIRS.filter((d) => {
  try {
    statSync(path.join(ROOT, d));
    return true;
  } catch {
    return false;
  }
}).flatMap((d) => walk(path.join(ROOT, d)));

/**
 * A colour token chosen by a substring test.
 *
 * `[\s\S]{0,120}?` rather than `[^\n]` because the pattern spans lines in several of the original
 * sites — `e.action` chose its colour across five lines of ternaries. Bounding it keeps the match
 * from reaching an unrelated colour further down the file.
 */
const COLOUR_FROM_SUBSTRING =
  /\.includes\([^)]*\)[\s\S]{0,120}?\?[\s\S]{0,80}?['"`]var\(--(red|green|amber|yellow|orange|text-red|text-green|text-amber)/;

describe("message severity is never inferred from wording", () => {
  it("found the app-wide sources to scan", () => {
    assert.ok(files.length > 40, `expected a real tree, found ${files.length} .tsx files`);
  });

  it("no colour is chosen by a substring test on a message", () => {
    const offenders: string[] = [];
    for (const file of files) {
      stripComments(readFileSync(file, "utf8"))
        .split("\n")
        .forEach((line, i) => {
          if (COLOUR_FROM_SUBSTRING.test(line)) {
            offenders.push(`${path.relative(ROOT, file)}:${i + 1}: ${line.trim().slice(0, 120)}`);
          }
        });
    }
    assert.deepEqual(
      offenders,
      [],
      "a colour decided by substring paints a failure green whenever the server words it differently",
    );
  });

  it("the five message panels in admin-content carry their tone in the state type", () => {
    // msg ×3, batchMsg, assignMsg. Kept as a specific count because that file held six of the eight
    // sites and this is the fact that would catch one of them being reverted to a bare string.
    const code = stripComments(readFileSync(path.join(ROOT, "app/dashboard/admin-content.tsx"), "utf8"));
    const typed = code.match(/const \[\w*[Mm]sg, set\w+\] = useState<\{ text: string; tone:/g) || [];
    assert.equal(typed.length, 5, `expected 5 tone-typed message states, found ${typed.length}`);
    const bare = code.match(/const \[\w*[Mm]sg, set\w+\] = useState\(''\)/g) || [];
    assert.deepEqual(bare, [], "a message state reverted to a bare string cannot carry severity");
  });
});
