#!/usr/bin/env bash
# Run the whole project: verify everything, then start the demo server.
#
#   ./run.sh            # tests + scenarios + render check, then serve on :8080
#   ./run.sh --check    # verify only, do not start the server
#   ./run.sh --serve    # skip verification, just start the server
#   PORT=9000 ./run.sh  # serve on a different port
set -uo pipefail

cd "$(dirname "$0")"
PORT="${PORT:-8080}"
export PYTHONPATH="$PWD/src"
PY="${PYTHON:-python3}"
MODE="all"
case "${1:-}" in
  --check) MODE="check" ;;
  --serve) MODE="serve" ;;
esac

hr() { printf '\n\033[1m== %s\033[0m\n' "$1"; }
fail=0

if [[ "$MODE" != "serve" ]]; then
  hr "1/7  dependencies"
  $PY -c "import yaml" 2>/dev/null || { echo "  installing pyyaml..."; $PY -m pip install -q pyyaml || fail=1; }
  echo "  python: $($PY -V 2>&1)"

  hr "2/7  unit + scenario + config-sync tests"
  if $PY -m pytest tests/ -q; then echo "  PASS"; else echo "  FAIL"; fail=1; fi

  hr "3/7  doctests (parser examples embedded in docstrings)"
  if $PY -m doctest src/homecredit_lap/parsing.py -v 2>&1 | tail -2; then echo "  PASS"; else echo "  FAIL"; fail=1; fi

  hr "4/7  call scenarios (12 scripted conversations)"
  if $PY tools/simulate.py --all-scenarios | tail -3; then :; else echo "  FAIL"; fail=1; fi

  hr "5/7  rendered prompts in sync with config"
  if $PY tools/render_prompts.py --check; then :; else echo "  FAIL — run: $PY tools/render_prompts.py"; fail=1; fi

  hr "6/7  traceability: all 64 original instructions accounted for"
  if $PY tools/verify_coverage.py; then :; else echo "  FAIL — docs/traceability.yaml has stale references"; fail=1; fi

  hr "7/7  regenerate the coverage report"
  if PYTHONPATH="$PWD/src:$PWD/tools" $PY tools/make_coverage_report.py >/dev/null; then
    echo "  docs/COVERAGE.md up to date"
  else echo "  FAIL"; fail=1; fi

  hr "result"
  if [[ $fail -eq 0 ]]; then
    echo -e "  \033[32mALL CHECKS PASSED\033[0m"
  else
    echo -e "  \033[31mONE OR MORE CHECKS FAILED\033[0m"
  fi
  [[ "$MODE" == "check" ]] && exit $fail
  [[ $fail -ne 0 ]] && { echo "  refusing to serve with failing checks (use --serve to override)"; exit $fail; }
fi

hr "starting demo server on 0.0.0.0:$PORT"
echo "  UI:       GET  /"
echo "  chat:     POST /chat        {call_id, text}"
echo "  retell:   POST /retell/tool/<name>"
echo "  vapi:     POST /vapi/tool/<name>"
echo "  health:   GET  /health"
echo "  (Ctrl-C to stop)"
exec $PY server/app.py --port "$PORT"
