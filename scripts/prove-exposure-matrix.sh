#!/usr/bin/env bash
# Drive the WHOLE exposure matrix against a rendered service over a REAL socket, from a REAL
# non-loopback address, and require every cell to refuse or to refuse to boot.
#
# The matrix is the profile variable's states crossed with the S2S secret's states, each probed
# with and without the seeded-persona header:
#
#             PROFILE: unset | empty | Local (mis-capitalised) | local | gcp | onprem
#   <PREFIX>_S2S_TOKEN: unset | empty | set
#       X-Dev-Persona: absent | approver
#
# Why the whole matrix rather than the two cases this file used to cover: both defects it has
# found so far lived in a cell nobody had run. The first was profile UNSET with the token SET,
# where the missing profile made `local` the inherited posture and the PRESENT token switched
# the exposure guard off. The second, found by an adversarial verifier against a zero-hand-edit
# render from a LAN peer, was profile `local` chosen DELIBERATELY with the token SET: the guard
# only ever covered the ZERO-SECRET demo, so setting a service credential disabled the bound on
# the END-USER routes it was protecting, and GET /v1/personas answered a stranger with the
# seeded approver persona (groups and tenant included) while POST /v1/triage answered with a
# real escalated decision and wrote a review_ref to the outbox.
#
# The fix is not a wider boolean. The guard now asks the IDENTITY ADAPTER the active binding
# names whether it verifies the end user (`ports/identity.py`), so a service credential cannot
# speak for end-user routes at all. This script is the standing proof of that, cell by cell.
#
# `tests/unit/test_serving_path_exposure.py` covers the same ground with a TestClient, which is
# faster and runs in every repo's gate. This runs uvicorn and a socket, because a TestClient
# proves what the app OBJECT does and only a bound server proves what a stranger gets.
#
# EXPECTED, per cell: either the process refuses to BOOT (the profile is empty or unknown), or
# every route answers the LAN peer 503. The one profile with a verifying end-user identity
# adapter, `gcp`, is the deliberate exception and is asserted separately at the bottom: its
# end-user route must answer 401 with no IAP assertion and its S2S route 503, while `/healthz`
# and the discovery card stay reachable because the platform fronts that deployment and those
# two carry no per-caller data.
#
# THE GCP SECTION IS THE THIRD REFUTATION, and the widest. An adversarial verifier ran the same
# zero-hand-edit render under `gcp` from a LAN peer and found the verifying declaration was not
# earned and the refusal was not a refusal:
#
#   * `id_token.verify_token(assertion, Request())` was called with NO `audience=` and NO
#     `certs_url=`. google-auth documents `audience=None` as "the audience is not verified", so
#     ANY Google-signed OIDC token, from any project or app, became a verified principal;
#   * the call was not wrapped, so `X-Goog-IAP-JWT-Assertion: not-a-jwt` raised
#     `MalformedError` (a ValueError, NOT an IdentityError) straight out of the route and
#     FastAPI answered a BARE 500. Proved twice, once with google-auth absent and once present;
#   * `/docs` and `/openapi.json` answered an uncredentialed LAN peer 200: the whole route
#     inventory and every schema, handed to a caller who can reach none of those routes.
#
# So the gcp section below probes the assertion header itself, with a malformed value, a
# well-formed value carrying a signature no IAP key produced, and one minted for a DIFFERENT
# audience; it probes the interactive docs; and it probes the deployment states that can
# authenticate nobody (audience unconfigured, verifier not installed), each of which must answer
# a refusal WITH A REASON rather than a bare 500. NO CELL ANYWHERE MAY ANSWER 500.
#
# The assertion strings are built here with the standard library alone. Whether the verifier can
# reach Google's key set decides only WHICH check fires, never the verdict: unreachable, the
# fetch fails and the wrap turns it into 401; reachable, the signature or the audience fails and
# the wrap turns THAT into 401. The proof is therefore the same offline and online. Which check
# fires for which malformed input is proved separately, against a locally minted key with no
# network at all, in the rendered `tests/unit/test_iap_crypto_matrix.py`.
#
# bash 3.2 compatible on purpose (that is what macOS ships): no arrays, because `set -u` plus an
# empty array expansion is an error there and a proof script that cannot run is worth nothing.
#
# Offline: the address used is this machine's own primary LAN address, discovered from the local
# routing table. Nothing is sent anywhere but to this host.
#
#   scripts/prove-exposure-matrix.sh <rendered-repo-dir>
set -euo pipefail

DIR="${1:?usage: prove-exposure-matrix.sh <rendered-repo-dir>}"
cd "$DIR"

PORT="${PROVE_PORT:-8123}"
LOG=/tmp/prove-exposure-server.log
BODY=/tmp/prove-exposure-body
PAYLOAD='{"subject":"Acme Holdings (FICTIONAL)","text":"urgent data breach"}'

# This machine's primary non-loopback IPv4 address. connect() on a UDP socket sends no packet; it
# only selects a route and therefore a source address.
LAN_IP="$(python3 -c '
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    s.connect(("192.0.2.1", 9))
    print(s.getsockname()[0])
finally:
    s.close()
')"
case "$LAN_IP" in
  ""|127.*) echo "no non-loopback address on this host; cannot prove the LAN refusal" >&2; exit 1 ;;
esac

# Read the package name and the env prefix out of the rendered repo, so this script carries no
# copy of either and works for any repo the template produces.
PACKAGE="$(python3 -c '
import pathlib, tomllib
data = tomllib.loads(pathlib.Path("pyproject.toml").read_text())
print(data["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"][0].rsplit("/", 1)[-1])
')"
PREFIX="$(python3 -c '
import pathlib, re
text = pathlib.Path(".env.example").read_text()
print(re.search(r"^([A-Z0-9]+)_PROFILE=", text, re.M).group(1))
')"
echo "   package=$PACKAGE prefix=$PREFIX lan=$LAN_IP port=$PORT"

# The three assertion strings the gcp cells present, built with the standard library only so this
# script needs nothing installed to mint them. The second and third are WELL FORMED JWTs (correct
# header, correct claim shape, a `kid`, an unexpired `exp`) whose signature bytes are random, so
# no key in IAP's published set produced them; the third additionally names a different audience.
# A random signature is a wrong-key signature in the only sense a verifier cares about.
MALFORMED_ASSERTION="not-a-jwt"
WRONG_KEY_ASSERTION="$(python3 -c '
import base64, json, os, time
def seg(obj):
    raw = json.dumps(obj, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
now = int(time.time())
head = seg({"alg": "RS256", "typ": "JWT", "kid": "not-an-iap-key"})
body = seg({
    "iss": "https://cloud.google.com/iap",
    "aud": "/projects/000000000000/global/backendServices/1111111111111111111",
    "sub": "accounts.google.com:100000000000000000001",
    "email": "attacker@evil.example",
    "hd": "evil.example",
    "iat": now - 30,
    "exp": now + 600,
})
sig = base64.urlsafe_b64encode(os.urandom(256)).rstrip(b"=").decode()
print(head + "." + body + "." + sig)
')"
WRONG_AUDIENCE_ASSERTION="$(python3 -c '
import base64, json, os, time
def seg(obj):
    raw = json.dumps(obj, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
now = int(time.time())
head = seg({"alg": "RS256", "typ": "JWT", "kid": "not-an-iap-key"})
body = seg({
    "iss": "https://cloud.google.com/iap",
    "aud": "/projects/999999999999/global/backendServices/2222222222222222222",
    "sub": "accounts.google.com:100000000000000000001",
    "email": "attacker@evil.example",
    "iat": now - 30,
    "exp": now + 600,
})
sig = base64.urlsafe_b64encode(os.urandom(256)).rstrip(b"=").decode()
print(head + "." + body + "." + sig)
')"

#: The IAP-protected resource the gcp cells configure. Obviously fictional.
IAP_AUDIENCE="/projects/000000000000/global/backendServices/1111111111111111111"

# What a BAD assertion must answer depends on whether this interpreter can import the verifier at
# all, and the difference is asserted rather than tolerated. With google-auth present the
# assertion is verified and REJECTED, which is a 401. Without it the deployment can verify nobody
# at all, which is a 503 naming the missing extra. Neither is a 500, which is the rule; the mode
# is printed so a reader knows which claim this run made.
if python -c 'import google.oauth2.id_token' >/dev/null 2>&1; then
  BAD_ASSERTION_CODE=401
  VERIFIER_MODE="google-auth IS importable: a bad assertion must be VERIFIED and rejected (401)"
else
  BAD_ASSERTION_CODE=503
  VERIFIER_MODE="google-auth is NOT importable: a bad assertion must be refused with a reason (503)"
fi

# Read by start_server. Globals rather than more positional parameters because this script is
# bash 3.2 (no arrays), and a fifth positional argument nobody can name at the call site is how a
# proof script starts lying about which cell it ran.
CELL_AUDIENCE="UNSET"     # value, or the literal word UNSET to remove the variable
CELL_PYPATH_PREFIX=""     # prepended to PYTHONPATH, to shadow an installed package

SERVER_PID=""
stop_server() {
  [ -n "$SERVER_PID" ] || return 0
  kill "$SERVER_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
  SERVER_PID=""
}
trap stop_server EXIT

# Nothing may be listening on the port when a cell starts. A server left over from the previous
# cell would answer the next cell's probes from the PREVIOUS cell's environment, and every cell
# would report the first cell's posture: a whole matrix of green ticks about one configuration.
# That is not hypothetical. It is what this script did until the launch below gained its `exec`,
# because `eval "... &"` put a shell between the job id and the process, so `kill` killed the
# wrapper and left uvicorn holding the socket.
wait_for_port_closed() {
  for _ in $(seq 1 100); do
    curl -s --max-time 1 -o /dev/null "http://127.0.0.1:$PORT/healthz" || return 0
    sleep 0.1
  done
  return 1
}

# $1 = the profile value, or the literal word UNSET to remove the variable.
# $2 = the token value, or the literal word UNSET to remove it.
#
# The command is assembled as a string and `eval`ed because every -u flag must precede the first
# NAME=VALUE (BSD env stops parsing options at the first assignment, so `env VAR= -u OTHER cmd`
# silently tries to run a command called "-u") and because an EMPTY value has to survive as a
# present-but-empty assignment. Every fragment below is a literal from this file or a name read
# out of the rendered repo; nothing here comes from the network.
start_server() {
  if ! wait_for_port_closed; then
    echo "     FAILED: port $PORT is still serving; a previous cell's process would answer" >&2
    exit 1
  fi
  : >"$LOG"
  flags="-u ${PREFIX}_ALLOW_INSECURE_DEMO"
  if [ -n "$CELL_PYPATH_PREFIX" ]; then
    assignments="PYTHONPATH='$CELL_PYPATH_PREFIX:src'"
  else
    assignments="PYTHONPATH=src"
  fi
  if [ "$CELL_AUDIENCE" = "UNSET" ]; then
    flags="$flags -u ${PREFIX}_IAP_AUDIENCE"
  else
    assignments="$assignments ${PREFIX}_IAP_AUDIENCE='$CELL_AUDIENCE'"
  fi
  if [ "$1" = "UNSET" ]; then
    flags="$flags -u ${PREFIX}_PROFILE"
  else
    assignments="$assignments ${PREFIX}_PROFILE='$1'"
  fi
  if [ "$2" = "UNSET" ]; then
    flags="$flags -u ${PREFIX}_S2S_TOKEN"
  else
    assignments="$assignments ${PREFIX}_S2S_TOKEN='$2'"
  fi
  # `exec`, so the background job IS uvicorn rather than a shell wrapping it. Without it `kill`
  # reaps the wrapper and leaves the server holding the port. See wait_for_port_closed above.
  eval "exec env $flags $assignments python -m uvicorn '$PACKAGE.api.app:app' \
        --host 0.0.0.0 --port '$PORT'" >"$LOG" 2>&1 &
  SERVER_PID=$!
  for _ in $(seq 1 60); do
    kill -0 "$SERVER_PID" 2>/dev/null || return 1
    curl -s --max-time 1 -o /dev/null "http://127.0.0.1:$PORT/healthz" && return 0
    sleep 0.2
  done
  return 0
}

# $1 method, $2 path, $3 "persona" to send X-Dev-Persona: approver, "bare" to send nothing.
# Leaves the status in CODE and the body in $BODY. Written as four explicit branches rather than
# an assembled argument list: this is the file that decides whether a refusal happened, so it
# stays readable at a glance.
CODE=""
request() {
  url="http://$LAN_IP:$PORT$2"
  if [ "$1" = "GET" ]; then
    if [ "$3" = "persona" ]; then
      CODE="$(curl -s -o "$BODY" -w '%{http_code}' --max-time 5 \
        -H 'X-Dev-Persona: approver' "$url" || echo 000)"
    else
      CODE="$(curl -s -o "$BODY" -w '%{http_code}' --max-time 5 "$url" || echo 000)"
    fi
  else
    if [ "$3" = "persona" ]; then
      CODE="$(curl -s -o "$BODY" -w '%{http_code}' --max-time 5 -X POST \
        -H 'Content-Type: application/json' -H 'X-Dev-Persona: approver' \
        -d "$PAYLOAD" "$url" || echo 000)"
    else
      CODE="$(curl -s -o "$BODY" -w '%{http_code}' --max-time 5 -X POST \
        -H 'Content-Type: application/json' -d "$PAYLOAD" "$url" || echo 000)"
    fi
  fi
  printf '     %-4s %-32s %-7s -> %s  %s\n' "$1" "$2" "$3" "$CODE" "$(head -c 110 "$BODY")"
}

# $1 method, $2 path, $3 the X-Goog-IAP-JWT-Assertion value, $4 a short label for the printout.
# Same shape as `request`, kept separate so the assertion cells are legible as their own list.
request_assertion() {
  url="http://$LAN_IP:$PORT$2"
  if [ "$1" = "GET" ]; then
    CODE="$(curl -s -o "$BODY" -w '%{http_code}' --max-time 15 \
      -H "X-Goog-IAP-JWT-Assertion: $3" "$url" || echo 000)"
  else
    CODE="$(curl -s -o "$BODY" -w '%{http_code}' --max-time 15 -X POST \
      -H 'Content-Type: application/json' -H "X-Goog-IAP-JWT-Assertion: $3" \
      -d "$PAYLOAD" "$url" || echo 000)"
  fi
  printf '     %-4s %-32s %-18s -> %s  %s\n' "$1" "$2" "$4" "$CODE" "$(head -c 110 "$BODY")"
}

# $1 the expected status, $2 the label. Records a failure, and records a SEPARATE, louder one for
# a 500: "no cell may answer a bare 500" is the rule the gcp section exists to hold, and a 500
# reported only as "not the expected status" reads like a threshold argument.
expect_code() {
  if [ "$CODE" = "500" ]; then
    echo "     FAILED: $2 answered a BARE 500. A crash is not a refusal."
    FAILURES=$((FAILURES + 1))
    return 0
  fi
  if [ "$CODE" != "$1" ]; then
    echo "     FAILED: $2 answered $CODE, expected $1"
    FAILURES=$((FAILURES + 1))
  fi
}

# Every route the app serves, including the two that need no identity at all: a deployment that
# can authenticate nobody has no business answering a stranger even about its own health. Each
# is probed twice, with and without the seeded-persona header.
probe_every_route() {
  want="$1"
  failed=0
  for persona in bare persona; do
    request GET  /healthz                       "$persona"; [ "$CODE" = "$want" ] || failed=1
    request GET  /v1/personas                   "$persona"; [ "$CODE" = "$want" ] || failed=1
    request GET  /.well-known/agent-card.json   "$persona"; [ "$CODE" = "$want" ] || failed=1
    request GET  /docs                          "$persona"; [ "$CODE" = "$want" ] || failed=1
    request GET  /openapi.json                  "$persona"; [ "$CODE" = "$want" ] || failed=1
    request POST /v1/triage                     "$persona"; [ "$CODE" = "$want" ] || failed=1
    request POST /v1/audit/ping                 "$persona"; [ "$CODE" = "$want" ] || failed=1
  done
  return "$failed"
}

FAILURES=0

# One matrix cell: profile $2, token $3. Every route must answer 503, or the process must have
# refused to boot for a reason that names the profile variable.
run_cell() {
  echo "-- $1 --"
  if ! start_server "$2" "$3"; then
    echo "     the process REFUSED TO BOOT, which is a stronger refusal than a 503:"
    # pipefail is on, so a grep that matches nothing would kill the script; never let the
    # DIAGNOSTIC decide the verdict.
    { grep -E 'Error|Exception|refus' "$LOG" || tail -5 "$LOG"; } | tail -2 | sed 's/^/       /'
    stop_server
    # A crash is only a REFUSAL if it is the refusal we claimed. Anything else (a port clash, a
    # typo in this script, a missing dependency) would otherwise be reported as a pass, which is
    # exactly the kind of falsely-green proof this whole exercise exists to remove. An earlier
    # draft of this script did precisely that: `env VAR= -u OTHER` made BSD env fail with
    # "env: -u: No such file or directory" and the run reported PROVED.
    if ! grep -q "${PREFIX}_PROFILE" "$LOG"; then
      echo "     FAILED: the process died, but not because of ${PREFIX}_PROFILE. See $LOG."
      FAILURES=$((FAILURES + 1))
    fi
    return 0
  fi
  if probe_every_route 503; then
    echo "     every route refused the LAN peer"
  else
    echo "     FAILED: a route answered something other than 503 to a non-loopback peer"
    FAILURES=$((FAILURES + 1))
  fi
  stop_server
}

echo "== the exposure matrix: profile x S2S token x persona header, from $LAN_IP =="
for token_label in UNSET EMPTY SET; do
  case "$token_label" in
    UNSET) token=UNSET ;;
    EMPTY) token="" ;;
    *)     token="not-a-real-secret" ;;
  esac
  run_cell "profile UNSET,               token $token_label" UNSET   "$token"
  run_cell "profile EMPTY,               token $token_label" ""      "$token"
  run_cell "profile 'Local' (typo),      token $token_label" "Local" "$token"
  run_cell "profile local (DELIBERATE),  token $token_label" local   "$token"
  run_cell "profile onprem,              token $token_label" onprem  "$token"
done

# ------------------------------------------------------------------------------------------ #
# The deliberate exception, asserted rather than assumed: `gcp` binds an identity adapter that
# VERIFIES a signed IAP assertion, so its end-user routes authenticate themselves and the
# exposure guard stands down. That is only defensible if the end-user route actually refuses an
# uncredentialed peer, so prove it rather than taking the declaration's word for it. This is the
# one profile whose process really does bind 0.0.0.0, so every probe below is a stranger on the
# LAN reaching a real deployment.
# ------------------------------------------------------------------------------------------ #
CELL_AUDIENCE="$IAP_AUDIENCE"
echo "-- profile gcp, audience CONFIGURED: guard stands down, the ROUTES refuse --"
if ! start_server gcp "not-a-real-secret"; then
  echo "     FAILED: the gcp profile did not boot"
  FAILURES=$((FAILURES + 1))
else
  request POST /v1/triage persona
  expect_code 401 "/v1/triage with no IAP assertion"
  request POST /v1/audit/ping persona
  expect_code 503 "/v1/audit/ping with no S2S identity policy"
  request GET /v1/personas persona
  expect_code 200 "/v1/personas"
  if [ "$(cat "$BODY")" != "[]" ]; then
    echo "     FAILED: /v1/personas must be empty outside the seeded-persona profile"
    FAILURES=$((FAILURES + 1))
  fi
  request GET /healthz bare
  expect_code 200 "/healthz (a fronted deployment must stay health-checkable)"

  # The docs decision, on the wire. These answered 200 to this same peer: the complete route
  # inventory and every request/response schema, handed to a caller who can reach none of them.
  request GET /docs bare
  expect_code 404 "/docs (interactive docs are a local-profile affordance)"
  request GET /openapi.json bare
  expect_code 404 "/openapi.json (the schema is not served off the offline profile)"
  request GET /redoc bare
  expect_code 404 "/redoc"

  # The assertion header itself. Every one of these produced a BARE 500 before the verifier call
  # was wrapped, and the second and third were ACCEPTED as verified identities before the
  # audience and the key set were pinned.
  echo "     $VERIFIER_MODE"
  request_assertion POST /v1/triage "$MALFORMED_ASSERTION" "malformed"
  expect_code "$BAD_ASSERTION_CODE" "/v1/triage with a malformed assertion"
  request_assertion POST /v1/triage "$WRONG_KEY_ASSERTION" "wrong signing key"
  expect_code "$BAD_ASSERTION_CODE" "/v1/triage with an assertion no IAP key signed"
  request_assertion POST /v1/triage "$WRONG_AUDIENCE_ASSERTION" "wrong audience"
  expect_code "$BAD_ASSERTION_CODE" "/v1/triage with an assertion minted for another service"
  request_assertion GET /v1/personas "$MALFORMED_ASSERTION" "malformed"
  expect_code 200 "/v1/personas with a malformed assertion"
  echo "     no end-user result reached the uncredentialed peer, and nothing answered 500"
  stop_server
fi

# The deployment that can authenticate NOBODY, in its two shapes. Both must refuse with a status
# and a REASON naming what to fix, because an operator reading a bare 500 (or a bare 401 inviting
# a credential that would never work) goes looking in the wrong place.
CELL_AUDIENCE="UNSET"
echo "-- profile gcp, audience UNCONFIGURED: refuses with a reason, never verifies without one --"
if ! start_server gcp "not-a-real-secret"; then
  echo "     FAILED: the gcp profile did not boot with no audience configured"
  FAILURES=$((FAILURES + 1))
else
  request_assertion POST /v1/triage "$WRONG_AUDIENCE_ASSERTION" "unconfigured aud"
  expect_code 503 "/v1/triage with no audience configured"
  case "$(cat "$BODY")" in
    *"${PREFIX}_IAP_AUDIENCE"*) echo "     the refusal names ${PREFIX}_IAP_AUDIENCE" ;;
    *) echo "     FAILED: the refusal does not name the variable to set"
       FAILURES=$((FAILURES + 1)) ;;
  esac
  stop_server
fi

# The same deployment with the verifier library missing. `google/__init__.py` on an earlier
# sys.path entry shadows the installed namespace package, so the lazy import raises ImportError
# exactly as it does where the [gcp] extra was never installed. This is the second shape the
# bare 500 was proved in.
CELL_AUDIENCE="$IAP_AUDIENCE"
NO_SDK_DIR="$(mktemp -d)"
mkdir -p "$NO_SDK_DIR/google"
printf 'raise ImportError("google-auth is not installed in this deployment")\n' \
  >"$NO_SDK_DIR/google/__init__.py"
CELL_PYPATH_PREFIX="$NO_SDK_DIR"
echo "-- profile gcp, VERIFIER NOT INSTALLED: a missing import is a refusal, not a crash --"
if ! start_server gcp "not-a-real-secret"; then
  echo "     FAILED: the gcp profile did not boot with google-auth unimportable"
  FAILURES=$((FAILURES + 1))
else
  request_assertion POST /v1/triage "$MALFORMED_ASSERTION" "no google-auth"
  expect_code 503 "/v1/triage with the verifier uninstalled"
  request POST /v1/triage bare
  expect_code 401 "/v1/triage with no assertion (refused before the import is reached)"
  stop_server
fi
CELL_PYPATH_PREFIX=""
CELL_AUDIENCE="UNSET"
rm -rf "$NO_SDK_DIR"

if [ "$FAILURES" -ne 0 ]; then
  echo "== EXPOSURE MATRIX: $FAILURES FAILING CELLS =="
  exit 1
fi
echo "== EXPOSURE MATRIX: EVERY CELL REFUSED =="
