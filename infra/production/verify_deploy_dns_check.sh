#!/usr/bin/env bash
# Does the deploy.sh DNS check stop crying wolf?
#
# The check it replaces compared one address to one address:
#
#     VPS_IP=$(curl ifconfig.me)                  # whichever family the socket picked
#     RESOLVED=$(getent hosts "$sub" | head -1)    # the A record
#
# On the previous IPv6-only host that printed a hard [ERR] for a domain whose DNS was entirely
# correct, because `ifconfig.me` answered `2a02:...::1` and `getent` answered the IPv4 record.
# The replacement host is IPv4-only and hit the mirror image. A deployment advisory that fires
# on correct DNS trains people to ignore it, which is how a real DNS break gets missed.
#
# So this exercises the matching itself against the cases that matter, with `curl` and `getent`
# stubbed. The stubs are deliberately faithful: `curl -4`/`-6` each return only their own
# family, and `ahostsv4`/`ahostsv6` are separate queries -- faking those wrongly is the bug
# being guarded against, so faking them correctly here is the whole point.
#
# Run:  bash infra/production/verify_deploy_dns_check.sh
set -uo pipefail

PASS=0
FAIL=0
OK_IF="infra/production/deploy.sh"

# The block under test, extracted from deploy.sh by content so it cannot drift into a copy that
# always passes. Terminator is the outer `fi` at column 0 -- every nested `fi` is indented, and
# matching `^}$` instead runs the extraction 80 lines past the block and silently stops testing
# anything, which is what the first version of this harness did.
extract_check() {
  sed -n '/^VPS_IPV4=/,/^fi$/p' "$OK_IF"
}

info() { :; }
ok()   { :; }
err()  { :; }

# deploy.sh defines these near the top; the extracted block uses them, and `set -u` turns a
# missing one into an error rather than an empty loop.
DOMAIN="ai.trademetrix.tech"
API_DOMAIN="api.ai.trademetrix.tech"

# Scenario knobs, set per case.
STUB_V4=""      # what `curl -4` reports for this host
STUB_V6=""      # what `curl -6` reports for this host
DNS_V4=""       # what the domain's A records are
DNS_V6=""       # what the domain's AAAA records are

curl() {
  # The real call is `curl -s -4 ...` / `curl -s -6 ...`.
  for a in "$@"; do
    case "$a" in
      -4) echo "$STUB_V4"; return ;;
      -6) echo "$STUB_V6"; return ;;
    esac
  done
  echo ""
}

getent() {
  # The address printed must be the one the case configured. A stub that always answers with a
  # fixed address makes every case look like a match -- which is exactly what happened the first
  # time this was written, and it reported "correct DNS" for a host whose DNS pointed elsewhere.
  case "$1" in
    ahostsv4) [ -n "$DNS_V4" ] && printf '%s   STREAM ai.trademetrix.tech\n' "$DNS_V4" ;;
    ahostsv6) [ -n "$DNS_V6" ] && printf '%s   STREAM ai.trademetrix.tech\n' "$DNS_V6" ;;
    hosts)    printf '%s   STREAM ai.trademetrix.tech\n' "${DNS_V4:-$DNS_V6}" ;;
    *) : ;;
  esac
  return 0
}

run_case() {
  # $1 label, $2 expected, $3 host v4, $4 host v6, $5 dns v4, $6 dns v6
  STUB_V4="$3"; STUB_V6="$4"; DNS_V4="$5"; DNS_V6="$6"
  local verdict
  # `\${MATCHED:-}` is escaped on purpose. Written plainly inside the double-quoted string it is
  # expanded by THIS shell while the argument is being built -- before the block has run, so the
  # verdict reflected a stale MATCHED and every case reported the same answer. It must be
  # expanded by the eval, once the block has actually set it.
  verdict=$( eval "$(extract_check)
        if [ -n \"\${MATCHED:-}\" ]; then echo MATCH; else echo MISMATCH; fi" 2>/dev/null | tail -1 )
  if [ "$verdict" = "$2" ]; then
    printf '  %-52s %s\n' "$1" "$verdict"
    PASS=$((PASS + 1))
  else
    printf '  %-52s got %s, expected %s   <-- FAIL\n' "$1" "${verdict:-<none>}" "$2"
    FAIL=$((FAIL + 1))
  fi
}

echo "  the block under test, extracted from $OK_IF:"
extract_check | sed 's/^/    /' | sed -n '1,3p'
echo

echo "  case                                                verdict"
echo "  --------------------------------------------------  -------"

# In every MATCH case the DNS record must point AT the host, not merely be a well-formed
# address. The first version of this file used the real production A record as the "correct"
# value against a host of 148.135.138.27 -- two different addresses -- so the case it labelled a
# match was a mismatch, and the harness correctly failed it.
V4=148.135.138.27
V6=2a02:4780:12:dae1::1

# IPv4-only host, A record correct -> the normal case.
run_case "IPv4-only host, DNS correct"            MATCH    "$V4" "" "$V4" ""
# The exact host that produced the original false alarm: IPv6-only, AAAA correct.
run_case "IPv6-only host, AAAA correct"           MATCH    "" "$V6" "" "$V6"
# Dual-stack host publishing only one family is still correct.
run_case "Dual-stack host, only AAAA published"    MATCH    "$V4" "$V6" "" "$V6"
run_case "Dual-stack host, both families published" MATCH   "$V4" "$V6" "$V4" "$V6"
# Genuinely wrong DNS must still be reported. This is the case that matters most: a check that
# cannot fail is worse than no check at all.
run_case "DNS points somewhere else entirely"     MISMATCH "$V4" "" "203.0.113.9" ""
run_case "IPv6 host, DNS still points to old v4"  MISMATCH "" "$V6" "140.82.121.4" ""
# The subtler one: the same address as a substring of a different address.
run_case "host is a prefix of the published record" MISMATCH "10.0.0.1" "" "10.0.0.10" ""

echo
if [ "$FAIL" -gt 0 ]; then
  echo "  $FAIL case(s) wrong"
  exit 1
fi
echo "  $PASS/$PASS cases correct, and real DNS mismatches are still caught"