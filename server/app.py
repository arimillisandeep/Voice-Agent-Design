#!/usr/bin/env python3
"""Webhook server that Retell / Vapi call for every tool invocation.

The LLM only *reports* what it heard; this server owns every threshold decision and
tells the model what to say next. That split is what makes the eligibility rules
auditable and immune to model drift.

Run:
    pip install -r requirements.txt
    python server/app.py --port 8080

Retell: point each custom tool's webhook at  POST /retell/tool/{name}
Vapi:   set each function's server.url    to POST /vapi/tool/{name}

Call state lives in memory keyed by call id so a call can span many tool calls.
Swap `InMemoryStore` for Redis in production.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from homecredit_lap.runtime import CallSession                     # noqa: E402
from homecredit_lap.state import MAX_LOAN_AMOUNT                   # noqa: E402
from homecredit_lap.tools import LapAgentTools                     # noqa: E402

log = logging.getLogger("lap.webhook")

# --------------------------------------------------------------------------- #
# Session store
# --------------------------------------------------------------------------- #
class InMemoryStore:
    """Per-call session storage. Replace with Redis/DynamoDB for multi-instance deploys."""

    def __init__(self, ttl_seconds: int = 3600) -> None:
        self._sessions: dict[str, CallSession] = {}
        self._tools: dict[str, LapAgentTools] = {}
        self._seen: dict[str, float] = {}
        self.ttl = ttl_seconds

    def session(self, call_id: str, **kwargs: Any) -> CallSession:
        self._evict()
        if call_id not in self._sessions:
            self._sessions[call_id] = CallSession(**kwargs)
            self._tools[call_id] = LapAgentTools(
                self._sessions[call_id].state,
                customer_name=kwargs.get("customer_name", "the customer"),
                language=kwargs.get("language", "en-IN"),
            )
        self._seen[call_id] = time.time()
        return self._sessions[call_id]

    def tools(self, call_id: str) -> LapAgentTools:
        return self._tools[call_id]

    def drop(self, call_id: str) -> Optional[dict[str, Any]]:
        """Return the lead payload and forget the call."""
        tools = self._tools.pop(call_id, None)
        session = self._sessions.pop(call_id, None)
        self._seen.pop(call_id, None)
        if session is None:
            return None
        payload = session.lead_payload()
        if tools is not None:
            payload["notes"] = tools.notes
        return payload

    def _evict(self) -> None:
        now = time.time()
        for cid in [c for c, t in self._seen.items() if now - t > self.ttl]:
            self._sessions.pop(cid, None)
            self._tools.pop(cid, None)
            self._seen.pop(cid, None)


STORE = InMemoryStore()

# --------------------------------------------------------------------------- #
# Request normalisation
# --------------------------------------------------------------------------- #
def _call_context(body: dict[str, Any]) -> dict[str, Any]:
    """Pull the call id and injected variables out of either platform's payload."""
    retell = body.get("retell", {}) or {}
    vapi_meta = (body.get("tool_call") or {}).get("metadata") or {}
    variables = (
        body.get("variables")
        or retell.get("variables")
        or vapi_meta.get("variables")
        or {}
    )
    call_id = (
        body.get("call_id")
        or retell.get("call_id")
        or (body.get("tool_call") or {}).get("callId")
        or "unknown"
    )
    return {
        "call_id": str(call_id),
        "customer_name": str(variables.get("customer_name", "the customer")),
        "language": str(variables.get("language_code", variables.get("language_to_speak", "en-IN"))),
        "agent_name": str(variables.get("agent_name", "Agent")),
        "company_name": str(variables.get("company_name", "the company")),
    }


# Tool argument types, by key. Platforms deliver every argument as a JSON string, so
# coercion must be driven by the FIELD, not by the string: a blanket "yes"->True would
# turn documents_original="yes" into True and silently defeat the disqualification rule
# (which tests for the literal strings "yes"/"no").
BOOLEAN_KEYS = frozenset({
    "customer_verified", "wrong_person", "cap_offer_accepted", "existing_property_loan",
    "emi_reduction_request", "busy", "declined", "do_not_call", "requested_human",
    "ended_by_customer",
})
STRING_KEYS = frozenset({
    "property_type", "ownership_status", "documents_original", "occupation",
    "income_mode", "callback_time",
})
INT_KEYS = frozenset({"loan_amount", "market_value"})
FLOAT_KEYS = frozenset({"tenure_years"})


def _coerce(key: str, value: Any) -> Any:
    """Normalise one tool argument to the Python type its state field expects."""
    if key in BOOLEAN_KEYS:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"true", "yes", "1", "y"}
    if key in STRING_KEYS:
        if value is None:
            return None
        return str(value).strip().lower() or None
    if key in INT_KEYS or key in FLOAT_KEYS:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return int(value) if key in INT_KEYS else float(value)
        s = str(value).strip().lower().replace(",", "").replace("\u20b9", "")
        try:
            num = float(s)
        except ValueError:
            return None                 # unparsable -> leave UNKNOWN, agent must re-ask
        return int(num) if key in INT_KEYS else num
    return value


def _coerce_args(args: dict[str, Any]) -> dict[str, Any]:
    """Coerce a whole argument dict; nested `facts` payloads are coerced per key too."""
    out: dict[str, Any] = {}
    for key, value in args.items():
        if key == "facts" and isinstance(value, dict):
            out[key] = {k: _coerce(k, v) for k, v in value.items()}
        elif key == "value" and isinstance(args.get("key"), str):
            out[key] = _coerce(args["key"], value)
        else:
            out[key] = value
    return out


# --------------------------------------------------------------------------- #
# Tool dispatch
# --------------------------------------------------------------------------- #
def handle_tool(name: str, args: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    """Execute one tool call and return the instruction payload for the model."""
    ctx = _call_context(body)
    session = STORE.session(ctx["call_id"], **{k: v for k, v in ctx.items() if k != "call_id"})
    tools = STORE.tools(ctx["call_id"])
    args = _coerce_args(args)
    log.info("call=%s tool=%s args=%s", ctx["call_id"], name, args)

    if name == "record_eligibility_fact":
        result = tools.record_eligibility_fact(args["key"], args.get("value"))

    elif name == "record_facts":
        result = tools.record_facts(args.get("facts") or {})

    elif name == "submit_eligibility_facts":
        result = tools.submit_eligibility_facts()

    elif name == "transfer_lead":
        result = tools.transfer_lead(args.get("specialist", "loan_transfer"))

    elif name == "schedule_callback":
        result = tools.schedule_callback(str(args.get("preferred_time", "")))

    elif name == "mark_do_not_call":
        result = tools.mark_do_not_call(str(args.get("reason", "customer_request")))

    elif name == "log_note":
        result = tools.log_note(str(args.get("note", "")), str(args.get("tag", "general")))

    elif name == "end_call":
        result = tools.end_call(str(args.get("reason", "completed")))

    elif name == "get_state":
        return {"state": session.state.to_dict(), "missing_items": session.state.missing_items()}

    else:
        return {"error": f"unknown tool: {name}"}

    # A `submit` action is an instruction to call submit_eligibility_facts, not the end
    # of the call, so the session must survive it. Only a real end_call releases state.
    if result.get("end_call"):
        payload = STORE.drop(ctx["call_id"])
        if payload:
            result["lead"] = payload
            log.info("call=%s finished status=%s", ctx["call_id"], payload["lead_status"])
    return result


# --------------------------------------------------------------------------- #
# Chat endpoint (drives the engine from raw text, for the browser demo)
# --------------------------------------------------------------------------- #
DEMO_HTML = (Path(__file__).resolve().parent / "demo.html")


def handle_chat(body: dict[str, Any]) -> dict[str, Any]:
    """Run one raw customer utterance through the engine and return everything the UI needs.

    No LLM is involved: the utterance goes through the regex parsing layer, which is what
    makes this endpoint free, offline and deterministic. In production the model supplies
    normalised facts via `record_eligibility_fact` instead.
    """
    call_id = str(body.get("call_id") or "demo")
    text = str(body.get("text") or "")
    # Coerce each fact by its own key: `_coerce_args` keys off a sibling "key" field,
    # which a bare facts dict does not have.
    facts = body.get("facts") or None
    if isinstance(facts, dict):
        facts = {k: _coerce(k, v) for k, v in facts.items()}
    elif facts:
        facts = None

    session = STORE.session(call_id, customer_name=str(body.get("customer_name", "Rajesh Kumar")),
                            language=str(body.get("language", "en-IN")))
    result = session.handle(text, facts=facts)

    payload = session.lead_payload()
    out = result.as_tool_result()
    out["state"] = {
        **session.state.to_dict(),
        "missing_items": session.state.missing_items(),
    }
    out["lead"] = {k: v for k, v in payload.items() if k not in ("transcript", "audit_trail")}

    # A terminal turn releases the call, exactly as the tool webhook does.
    if result.end_call or (session.state.terminal and result.action != "submit"):
        STORE.drop(call_id)
    return out


def handle_reset(body: dict[str, Any]) -> dict[str, Any]:
    call_id = str(body.get("call_id") or "demo")
    dropped = STORE.drop(call_id)
    return {"reset": True, "call_id": call_id, "previous_lead_status":
            (dropped or {}).get("lead_status")}


# --------------------------------------------------------------------------- #
# HTTP layer (stdlib only; works with no dependencies installed)
# --------------------------------------------------------------------------- #
def _respond(handler: Any, status: int, payload: dict[str, Any]) -> None:
    import json
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(raw)


class Handler:
    """Tiny request handler shared by the stdlib server."""

    def __init__(self, http_handler: Any) -> None:
        self.h = http_handler

    def route(self) -> tuple[str, str]:
        path = self.h.path.split("?", 1)[0].rstrip("/")
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 3 and parts[0] in ("retell", "vapi") and parts[1] == "tool":
            return parts[0], parts[2]
        return "", ""

    def do_POST(self) -> None:  # noqa: N802
        import json
        length = int(self.h.headers.get("Content-Length") or 0)
        raw_body = self.h.rfile.read(length) or b"{}"
        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError:
            return _respond(self.h, 400, {"error": "invalid JSON body"})

        path = self.h.path.split("?", 1)[0].rstrip("/")
        if path == "/chat":
            try:
                return _respond(self.h, 200, handle_chat(body))
            except Exception as exc:
                log.exception("chat failed")
                return _respond(self.h, 200, {"error": "internal_error", "detail": str(exc),
                                              "action": "continue", "end_call": False})
        if path == "/reset":
            return _respond(self.h, 200, handle_reset(body))

        platform, name = self.route()
        if not name:
            return _respond(self.h, 404, {"error": "unknown route"})
        args = self._extract_args(platform, body)
        try:
            result = handle_tool(name, args, body)
        except KeyError as exc:
            return _respond(self.h, 400, {"error": f"missing required argument: {exc}"})
        except Exception as exc:  # never let a 500 hang a live call
            log.exception("tool %s failed", name)
            return _respond(self.h, 200, {
                "error": "internal_error",
                "say": "I'm sorry, let me continue. Could you repeat that?",
                "action": "continue",
                "end_call": False,
                "detail": str(exc),
            })
        return _respond(self.h, 200, self._wrap(platform, result))

    def do_GET(self) -> None:  # noqa: N802
        path = self.h.path.split("?", 1)[0].rstrip("/")
        if path in ("", "/"):
            return self._serve_demo()
        if path == "/health":
            return _respond(self.h, 200, {
                "status": "ok",
                "service": "homecredit-lap-agent",
                "max_loan_amount": MAX_LOAN_AMOUNT,
                "routes": ["/", "/chat", "/reset", "/retell/tool/<name>",
                           "/vapi/tool/<name>", "/health"],
            })
        return _respond(self.h, 404, {"error": "not found"})

    def _serve_demo(self) -> None:
        """Serve the browser demo. Inline assets only: the preview iframe has no CDN access."""
        try:
            html = DEMO_HTML.read_text(encoding="utf-8")
        except OSError:
            return _respond(self.h, 500, {"error": "demo.html missing"})
        raw = html.encode("utf-8")
        self.h.send_response(200)
        self.h.send_header("Content-Type", "text/html; charset=utf-8")
        self.h.send_header("Content-Length", str(len(raw)))
        self.h.send_header("Cache-Control", "no-store")
        self.h.end_headers()
        self.h.wfile.write(raw)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.h.send_response(204)
        self.h.send_header("Access-Control-Allow-Origin", "*")
        self.h.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.h.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.h.end_headers()

    # -- platform payload shapes ------------------------------------------- #
    @staticmethod
    def _extract_args(platform: str, body: dict[str, Any]) -> dict[str, Any]:
        """Both platforms nest arguments differently; flatten to a plain dict."""
        if platform == "vapi":
            call = body.get("tool_call") or body
            args = call.get("function", {}).get("arguments") or call.get("arguments") or {}
            if isinstance(args, str):
                import json
                args = json.loads(args or "{}")
            return args
        # Retell sends the arguments at the top level, or under "params"/"arguments".
        for key in ("params", "arguments", "tool_input"):
            if isinstance(body.get(key), dict):
                return body[key]
        return {k: v for k, v in body.items() if k not in ("retell", "call_id", "variables")}

    @staticmethod
    def _wrap(platform: str, result: dict[str, Any]) -> dict[str, Any]:
        """Shape the response the way each platform expects to hand it to the model."""
        if platform == "vapi":
            return {
                "results": [{
                    "tool_call_id": result.pop("tool_call_id", None),
                    "result": result,
                }],
                **result,
            }
        return result


def serve(host: str, port: int) -> None:
    from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

    class _H(BaseHTTPRequestHandler):
        def do_POST(self):      Handler(self).do_POST()
        def do_GET(self):       Handler(self).do_GET()
        def do_OPTIONS(self):   Handler(self).do_OPTIONS()

        def log_message(self, fmt, *a):   # route access logs through logging
            log.info("%s - %s", self.address_string(), fmt % a)

    # Bind 0.0.0.0 so the sandbox preview / container port mapping can reach it.
    httpd = ThreadingHTTPServer((host, port), _H)
    log.info("LAP webhook listening on http://%s:%d", host, port)
    log.info("  POST /retell/tool/<name>   POST /vapi/tool/<name>   GET /health")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log.info("shutting down")
        httpd.shutdown()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    serve(args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
