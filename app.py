from dotenv import load_dotenv
load_dotenv()
from flask import Flask, render_template, request, jsonify, g
import json, os, traceback, io, contextlib, re, ast, sys, time, threading, subprocess, tempfile, uuid, random
from concurrent.futures import ThreadPoolExecutor
from typing import List, Tuple, Optional, Any, Dict

__version__ = "0.8.0"
from rapidfuzz import fuzz
from google import genai
from google.genai import types as genai_types
from structure_parser import CodeAnalyzer
from intent_parser import parse_intent
from sandboxed_fs import get_sandbox

# ---------------------------------------------------------------------------
# Interactive run (Mechanism B) state
# ---------------------------------------------------------------------------
# Each live run gets a UUID. The state dict holds the subprocess handle,
# FIFO path, output buffer, completion flag, and a queue.Queue that the SSE
# generator reads chunks from. Cleanup happens on subprocess exit OR when
# the SSE client disconnects (whichever comes first).
import queue as _queue_mod

_active_runs = {}  # run_id -> dict
_active_runs_lock = threading.Lock()

# Voice macros: per-session named code snippets the student can recall by name.
# Stored on disk alongside snippets but in a separate file so they don't clutter
# the snippet list. Keyed by sanitized session id.
_voice_macros_lock = threading.Lock()

# Output bookmarks: per-session list of {label, position, timestamp, output_id}.
# In-memory only (cheap, ephemeral, scoped to session).
_output_bookmarks = {}  # session_id -> list[dict]
_output_bookmarks_lock = threading.Lock()

# Thread-local storage for per-request Gemini API key.
# (_trace_context was removed along with run_with_trace — session storage handles traces.)
_api_context = threading.local()

# Session-based trace storage (prevents concurrent user interference)
# Keys: session_id (UUID), Values: {last_trace, current_trace_index, trace_timestamp, trace_duration_ms, last_voice_action}
_session_traces = {}  # dict[str, dict]
_session_traces_lock = threading.Lock()

# Tunable limits — kept together at module top so deployment can tweak via env
SESSION_TTL_SECONDS = int(os.environ.get("CODEUP_SESSION_TTL", "3600"))
_session_ttl = SESSION_TTL_SECONDS  # back-compat alias

# Background cleanup thread for old sessions
def _session_cleanup_worker():
    """Background thread that periodically cleans up expired sessions and
    bounded structures that would otherwise leak in long-running deployments."""
    while True:
        time.sleep(300)  # Run cleanup every 5 minutes
        try:
            cleanup_old_sessions()
        except Exception as e:
            print(f"Session cleanup error: {e}", file=sys.stderr)
        try:
            cleanup_stale_runs()
        except Exception as e:
            print(f"Stale runs cleanup error: {e}", file=sys.stderr)
        try:
            cleanup_orphan_bookmarks_and_telemetry()
        except Exception as e:
            print(f"Bookmark/telemetry cleanup error: {e}", file=sys.stderr)


def cleanup_stale_runs():
    """Reap _active_runs whose subprocess has exited or whose started_at
    is older than 5 minutes. Live runs are capped at 60s server-side, so
    anything older is definitely abandoned."""
    now = time.time()
    stale_ids = []
    with _active_runs_lock:
        for run_id, state in list(_active_runs.items()):
            proc = state.get("proc")
            started = state.get("started_at", now)
            if (proc is not None and proc.poll() is not None) or (now - started > 300):
                stale_ids.append(run_id)
    for run_id in stale_ids:
        try:
            _cleanup_run(run_id)
        except Exception:
            pass


def cleanup_orphan_bookmarks_and_telemetry():
    """Drop bookmarks for sessions no longer in _session_traces, and trim
    voice telemetry to its cap. Bounded by session count so this never
    grows past O(active_sessions)."""
    with _session_traces_lock:
        live_sessions = set(_session_traces.keys())
    with _output_bookmarks_lock:
        for sid in list(_output_bookmarks.keys()):
            if sid not in live_sessions:
                del _output_bookmarks[sid]
    # Telemetry already self-trims on insert, but guarantee the cap here too
    with _voice_telemetry_lock:
        if len(_voice_telemetry) > _VOICE_TELEMETRY_CAP:
            del _voice_telemetry[:len(_voice_telemetry) - _VOICE_TELEMETRY_CAP]
_cleanup_thread = threading.Thread(target=_session_cleanup_worker, daemon=True)
_cleanup_thread.start()

# Bounded ThreadPoolExecutor for Gemini API calls (prevents resource exhaustion)
# Max 3 concurrent requests with queue size limit
_gemini_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="gemini")

# FIX H-1: Track active+queued requests with a thread-safe counter instead of
# accessing private ThreadPoolExecutor internals (_threads, _work_queue).
_gemini_active_requests = 0
_gemini_active_lock = threading.Lock()
_gemini_queued_requests = 0  # separate counter for submitted-but-not-started tasks

# lock used to serialize tracer installation to avoid cross-thread interference
_tracer_lock = threading.Lock()

# Subprocess resource limits — POSIX only. Defined at module scope so each
# subprocess.Popen call doesn't pay the cost of redefining + importing.
if sys.platform != "win32":
    import resource as _resource

    def _set_subprocess_limits():
        try:
            _resource.setrlimit(_resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
            _resource.setrlimit(_resource.RLIMIT_CPU, (10, 10))
            try:
                _resource.setrlimit(_resource.RLIMIT_NPROC, (64, 64))
            except (ValueError, OSError):
                pass
        except Exception:
            pass
else:
    def _set_subprocess_limits():
        pass

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')

# Session configuration
SESSION_COOKIE_NAME = 'codeup_session'
SESSION_COOKIE_MAX_AGE = 3600 * 24 * 7  # 7 days
# FIX H-4: Drive SESSION_COOKIE_SECURE from environment so TLS deployments are
# protected without requiring a manual code change.
SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = None if os.environ.get("FLASK_TESTING", "false").lower() == "true" else 'Lax'

# FIX C-1: Register ONE module-level after_request handler instead of
# registering a new permanent handler on every new-session request.
# Previously get_session_id() contained @app.after_request inside its body,
# causing an unbounded accumulation of handlers and duplicate Set-Cookie headers.
@app.after_request
def set_session_cookie(response):
    """Set session cookie if not already present.

    Uses the same session_id that get_session_id() generated during this
    request (stashed on flask.g) so storage and cookie always agree.
    """
    if not request.cookies.get(SESSION_COOKIE_NAME):
        session_id = getattr(g, 'session_id', None) or str(uuid.uuid4())
        response.set_cookie(
            SESSION_COOKIE_NAME,
            session_id,
            max_age=SESSION_COOKIE_MAX_AGE,
            secure=SESSION_COOKIE_SECURE,
            httponly=SESSION_COOKIE_HTTPONLY,
            samesite=SESSION_COOKIE_SAMESITE,
        )
    return response


def get_session_id():
    """Get or create a persistent session ID using cookies.

    Caches the generated ID on flask.g so set_session_cookie can reuse the
    same value. Otherwise storage gets keyed under one UUID and the cookie
    sent to the client is a different UUID.
    """
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id:
        return session_id
    cached = getattr(g, 'session_id', None)
    if cached:
        return cached
    session_id = str(uuid.uuid4())
    g.session_id = session_id
    return session_id


def _make_session_storage():
    """Single source of truth for the shape of per-session trace storage."""
    now = time.time()
    return {
        'last_trace': [],
        'current_trace_index': -1,
        'trace_timestamp': now,
        'trace_duration_ms': 0,
        'last_voice_action': None,
        'created_at': now,
        'last_accessed': now,
    }


def get_trace_storage():
    """Get the trace storage dict for current session."""
    session_id = get_session_id()
    with _session_traces_lock:
        if session_id not in _session_traces:
            _session_traces[session_id] = _make_session_storage()
        else:
            _session_traces[session_id]['last_accessed'] = time.time()
        return _session_traces[session_id]


def cleanup_old_sessions():
    """Clean up sessions that have been idle longer than _session_ttl."""
    now = time.time()
    with _session_traces_lock:
        # FIX H-2 (continued): expire based on last_accessed, not created_at.
        expired = [sid for sid, data in _session_traces.items()
                   if now - data.get('last_accessed', 0) > _session_ttl]
        for sid in expired:
            del _session_traces[sid]


# ==========================
# REQUEST SIZE VALIDATION
# ==========================
# Hard limits to prevent resource exhaustion
MAX_REQUEST_SIZE = 1_000_000  # 1 MB max request body
MAX_CODE_SIZE = 100_000       # 100 KB max code
MAX_GEMINI_TIMEOUT = 30       # 30 second timeout for LLM calls

# Per-session rate limiting for /run
# Allows at most RUN_RATE_LIMIT executions per RUN_RATE_WINDOW seconds per session.
RUN_RATE_LIMIT  = 10   # max runs
RUN_RATE_WINDOW = 60   # per this many seconds
_run_timestamps: dict = {}   # session_id -> list[float]
_run_rate_lock = threading.Lock()

def _check_run_rate_limit(session_id: str) -> bool:
    """Return True if the session is within the rate limit, False if throttled.

    Also opportunistically sweeps stale entries so _run_timestamps doesn't
    grow without bound on long-running deployments. We sweep on roughly 1 in
    every 50 calls to amortize the cost.
    """
    now = time.time()
    with _run_rate_lock:
        # Opportunistic cleanup: drop session entries that have no live timestamps
        if len(_run_timestamps) > 100 and random.random() < 0.02:
            stale = [sid for sid, ts in _run_timestamps.items()
                     if not any(now - t < RUN_RATE_WINDOW for t in ts)]
            for sid in stale:
                del _run_timestamps[sid]

        timestamps = _run_timestamps.get(session_id, [])
        # Drop entries outside the window
        timestamps = [t for t in timestamps if now - t < RUN_RATE_WINDOW]
        if len(timestamps) >= RUN_RATE_LIMIT:
            _run_timestamps[session_id] = timestamps
            return False
        timestamps.append(now)
        _run_timestamps[session_id] = timestamps
        return True
    
    
# Threshold for fuzzy voice command matching. Raised from 40 to 55 because
# 40 was permissive enough that ambient speech ("no thanks", "what was that")
# would fuzzy-match command keywords and trigger spurious confirm prompts.
# 55 still allows for typos and partial commands but rejects genuinely
# unrelated phrases. Below this threshold the input falls through to "unknown".
VOICE_FUZZY_THRESHOLD = 55

@app.before_request
def validate_request_size():
    """Reject oversized requests before processing."""
    if request.content_length and request.content_length > MAX_REQUEST_SIZE:
        return jsonify({"success": False, "error": "Request too large (max 1MB)"}), 413


# Parse allowlist once at import time
_ALLOWED_ORIGINS = {
    o.strip().lower()
    for o in os.environ.get("ALLOWED_ORIGINS", "").split(",")
    if o.strip()
}
_TESTING_MODE = os.environ.get("FLASK_TESTING", "false").lower() == "true"


@app.before_request
def enforce_same_origin():
    """Block cross-origin POST/PUT/DELETE requests.

    Policy:
      - Same-origin (Origin host == Host) is allowed.
      - Origin in ALLOWED_ORIGINS env var (comma-separated) is allowed.
      - In FLASK_TESTING=true mode, headerless requests (test client, curl) are allowed.
      - Outside testing mode, a request with neither Origin nor Referer is REJECTED.
    """
    if request.method not in ("POST", "PUT", "DELETE", "PATCH"):
        return None

    origin = request.headers.get("Origin")
    referer = request.headers.get("Referer")
    host = request.headers.get("Host", "").lower()

    # No Origin and no Referer
    if not origin and not referer:
        if _TESTING_MODE:
            return None
        return jsonify({"success": False, "error": "Missing Origin/Referer header"}), 403

    # Check Origin first (more reliable)
    if origin:
        origin_lower = origin.lower()
        origin_host = origin_lower.split("://", 1)[-1]
        if origin_host == host:
            return None
        if origin_lower in _ALLOWED_ORIGINS:
            return None
        return jsonify({"success": False, "error": "Cross-origin request blocked"}), 403

    # Fall back to Referer
    if referer:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(referer)
            referer_host = parsed.netloc.lower()
            referer_origin = f"{parsed.scheme}://{parsed.netloc}".lower()
            if referer_host == host:
                return None
            if referer_origin in _ALLOWED_ORIGINS:
                return None
        except Exception:
            pass
        return jsonify({"success": False, "error": "Cross-origin request blocked"}), 403

    return None

SNIPPETS_FILE = os.environ.get("SNIPPETS_FILE", "snippets.json")
DATA_DIR = os.environ.get("DATA_DIR", ".")

def _snippets_path(session_id: str = None) -> str:
    """Return the absolute path to the snippets file for a given session.

    Each session gets its own snippets file so students sharing a lab
    machine don't see each other's saved code. The session_id is
    sanitized to a UUID-safe filename.
    """
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except Exception:
        pass

    if session_id is None:
        session_id = get_session_id()

    # Sanitize: only allow hex chars and dashes (UUID format)
    safe_id = re.sub(r'[^a-fA-F0-9\-]', '', session_id)[:64]
    if not safe_id:
        safe_id = "default"

    filename = f"snippets_{safe_id}.json"
    return os.path.join(DATA_DIR, filename)

# ==========================
# BASIC HELPERS
# ==========================

def safejson() -> dict:
    """Safely parse JSON from the request, returning a dict."""
    d = request.get_json(silent=True)
    if isinstance(d, dict):
        return d
    return {}

def safe(v: Any, d: Any = "") -> Any:
    """Return `v` when not None, otherwise return default `d`."""
    return v if v is not None else d

def load_snippets() -> dict:
    """Load snippets from disk and return a dict with key `snippets`."""
    path = _snippets_path()
    if not os.path.exists(path):
        return {"snippets": []}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict) and "snippets" in data:
                return data
    except Exception:
        pass
    return {"snippets": []}

_snippets_lock = threading.Lock()

def save_snippets(d: dict) -> None:
    """Save snippets atomically using temp-then-move to prevent corruption.
    On POSIX, also fsyncs the directory so the rename is durable across power loss."""
    path = _snippets_path()
    dirpath = os.path.dirname(path) or "."

    with _snippets_lock:
        temp_path = None
        try:
            fd, temp_path = tempfile.mkstemp(suffix=".json", prefix="snippets_", dir=dirpath)
            try:
                with os.fdopen(fd, 'w', encoding="utf-8") as f:
                    json.dump(d, f, indent=4)
                    f.flush()
                    try:
                        os.fsync(f.fileno())
                    except OSError:
                        pass
            except:
                try:
                    os.close(fd)
                except OSError:
                    pass
                raise
            os.replace(temp_path, path)
            # Fsync the directory so the rename itself is durable
            if sys.platform != "win32":
                try:
                    dir_fd = os.open(dirpath, os.O_RDONLY)
                    try:
                        os.fsync(dir_fd)
                    finally:
                        os.close(dir_fd)
                except OSError:
                    pass
        except Exception:
            try:
                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass
            raise

# ==========================
# GEMINI API CONFIG
# ==========================

# FIX L-2: `from typing import Any` moved to top-of-file import (already present above).
# The original file had it buried at line 140 after helper function definitions.

# default global fallback key (will only be used if session key missing)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "Insert_API_Key_Here")

# FIX L-3: Updated deprecated "gemini-pro" model name to a current model identifier.
GEMINI_MODEL = "llama-3.3-70b-versatile"

# helper to retrieve current API key (session overrides global)
def _current_api_key():
    return getattr(_api_context, 'gemini_key', GEMINI_API_KEY)

def _call_ollama(system_prompt, user_prompt, temperature=0.2):
    """Call local Ollama instance. Returns response string or None on failure."""
    if os.environ.get("OLLAMA_ENABLED", "0") != "1":
        return None
    try:
        import requests
        url = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
        model = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
        resp = requests.post(
            f"{url}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "options": {"temperature": temperature, "num_predict": 1024},
                "stream": False,
            },
            timeout=MAX_GEMINI_TIMEOUT,
        )
        if resp.status_code != 200:
            print(f"Ollama returned HTTP {resp.status_code}", file=sys.stderr)
            return None
        data = resp.json()
        content = (data.get("message") or {}).get("content", "").strip()
        return content if content else None
    except Exception as e:
        print(f"Ollama call failed: {e}", file=sys.stderr)
        return None


def call_gemini(system_prompt, user_prompt, temperature=0.2, language="en"):
    """Call Groq API with hard timeout, falling back to local Ollama if Groq fails.

    Function name kept as call_gemini for backward compat with all callers.
    Order: Groq cloud → Ollama local → friendly error message.
    """
    if os.environ.get("GEMINI_ENABLED", "1") != "1":
        # Cloud disabled — try Ollama directly
        sp = system_prompt
        if language == "hi":
            sp = f"आप एक सहायक हैं जो हिंदी में सहायता प्रदान करते हैं। {system_prompt}"
        local = _call_ollama(sp, user_prompt, temperature)
        if local:
            return local
        return "AI service disabled"

    global _gemini_queued_requests

    key = os.environ.get("GROQ_API_KEY", "")

    def _try_ollama_fallback():
        """Try the local Ollama fallback. Returns response or None."""
        sp = system_prompt
        if language == "hi":
            sp = f"आप एक सहायक हैं जो हिंदी में सहायता प्रदान करते हैं। {system_prompt}"
        return _call_ollama(sp, user_prompt, temperature)

    if not key:
        local = _try_ollama_fallback()
        if local:
            return local
        return (
            "AI service not configured. Please ask your teacher to set the GROQ_API_KEY, "
            "or install Ollama locally for offline AI."
        )

    def _do_call():
        global _gemini_active_requests, _gemini_queued_requests
        with _gemini_active_lock:
            _gemini_queued_requests = max(0, _gemini_queued_requests - 1)
            _gemini_active_requests += 1
        try:
            sp = system_prompt
            if language == "hi":
                sp = f"आप एक सहायक हैं जो हिंदी में सहायता प्रदान करते हैं। {system_prompt}"

            from groq import Groq
            client = Groq(api_key=key)
            response = client.chat.completions.create(
                model=GEMINI_MODEL,
                messages=[
                    {"role": "system", "content": sp},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=1024,
            )
            content = response.choices[0].message.content
            return content.strip() if content else "No response generated"
        except Exception as e:
            err_str = str(e).lower()
            # Try Ollama before returning a user-facing error
            local = _try_ollama_fallback()
            if local:
                return f"[offline mode] {local}"
            if "rate" in err_str or "quota" in err_str or "429" in err_str:
                return "The cloud AI is busy and offline AI is not available. Please wait a moment and try again."
            if "auth" in err_str or "invalid" in err_str or "401" in err_str:
                return "Cloud AI authentication failed and offline AI is not available. Please ask your teacher to check the API key."
            if "timeout" in err_str or "timed out" in err_str:
                return "The cloud AI took too long to respond and offline AI is not available. Try a shorter request."
            if "connection" in err_str or "network" in err_str or "dns" in err_str:
                return "No internet connection and offline AI is not available. Ask your teacher to install Ollama for offline mode."
            return f"AI service had a problem: {str(e)[:100]}. Offline AI is also not available."
        finally:
            with _gemini_active_lock:
                _gemini_active_requests -= 1

    with _gemini_active_lock:
        current_active = _gemini_active_requests
        current_queued = _gemini_queued_requests

    if current_active + current_queued >= 8:
        local = _try_ollama_fallback()
        if local:
            return f"[offline mode] {local}"
        return "AI service is busy and offline AI is not available. Please try again later."

    with _gemini_active_lock:
        _gemini_queued_requests += 1

    try:
        future = _gemini_executor.submit(_do_call)
    except Exception as e:
        with _gemini_active_lock:
            _gemini_queued_requests = max(0, _gemini_queued_requests - 1)
        local = _try_ollama_fallback()
        if local:
            return f"[offline mode] {local}"
        return f"AI service is currently unavailable: {str(e)}"

    try:
        return future.result(timeout=MAX_GEMINI_TIMEOUT + 1)
    except Exception as e:
        local = _try_ollama_fallback()
        if local:
            return f"[offline mode] {local}"
        return f"AI service is currently unavailable: {str(e)}"    

def extract_code(text: str):
    m = re.search(r"```(?:python)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if not m:
        return ""
    raw = m.group(1).strip()
    lines = []
    for line in raw.splitlines():
        low = line.strip().lower()
        if low.startswith("here is") or low.startswith("fixed code") or low.startswith("the corrected"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()

# ==========================
# MAIN PAGE
# ==========================

@app.route("/")
def landing():
    return render_template('landing.html')

@app.route("/ide")
def ide():
    return render_template('index.html')


@app.route("/healthz", methods=["GET"])
def healthz():
    """Simple liveness probe for deployment monitoring."""
    return jsonify({"status": "ok", "version": __version__}), 200

# ==========================
# DEMO PRESETS
# ==========================

DEMO_PRESETS = {
    "hello": {
        "title": "Hello World",
        "description": "Your very first Python program. Print text to the screen.",
        "code": 'print("Hello, CodeUp!")\nprint("Welcome to Python.")\n',
    },
    "fibonacci": {
        "title": "Fibonacci Sequence",
        "description": "Generate the first 10 numbers in the Fibonacci sequence using a loop.",
        "code": (
            "# First 10 Fibonacci numbers\n"
            "a, b = 0, 1\n"
            "for i in range(10):\n"
            "    print(a)\n"
            "    a, b = b, a + b\n"
        ),
    },
    "primes": {
        "title": "Prime Numbers",
        "description": "Find all prime numbers between 2 and 30.",
        "code": (
            "# Primes between 2 and 30\n"
            "for n in range(2, 31):\n"
            "    is_prime = True\n"
            "    for d in range(2, n):\n"
            "        if n % d == 0:\n"
            "            is_prime = False\n"
            "            break\n"
            "    if is_prime:\n"
            "        print(n)\n"
        ),
    },
    "calculator": {
        "title": "Simple Calculator",
        "description": "Perform basic arithmetic with hardcoded values.",
        "code": (
            "# Change these values to try different calculations\n"
            "a = 15\n"
            "b = 4\n"
            "\n"
            'print("Sum:", a + b)\n'
            'print("Difference:", a - b)\n'
            'print("Product:", a * b)\n'
            'print("Quotient:", a / b)\n'
            'print("Remainder:", a % b)\n'
        ),
    },
    "wordcount": {
        "title": "Word Counter",
        "description": "Count words in a sentence using string methods.",
        "code": (
            'sentence = "The quick brown fox jumps over the lazy dog"\n'
            "words = sentence.split()\n"
            'print("Sentence:", sentence)\n'
            'print("Word count:", len(words))\n'
            'print("First word:", words[0])\n'
            'print("Last word:", words[-1])\n'
        ),
    },
    "guess": {
        "title": "Number Guessing",
        "description": "A simple guessing game with hardcoded guess (no input() needed).",
        "code": (
            "import random\n"
            "\n"
            "secret = random.randint(1, 10)\n"
            "guess = 5  # change this to test different guesses\n"
            "\n"
            'print("The secret number was:", secret)\n'
            'print("Your guess was:", guess)\n'
            "\n"
            "if guess == secret:\n"
            '    print("Correct! You win!")\n'
            "elif guess < secret:\n"
            '    print("Too low. Try a higher number.")\n'
            "else:\n"
            '    print("Too high. Try a lower number.")\n'
        ),
    },
}


@app.route("/demo-presets", methods=["GET"])
def list_demo_presets():
    """Return list of available demo presets (id, title, description)."""
    return jsonify({
        "success": True,
        "presets": [
            {"id": k, "title": v["title"], "description": v["description"]}
            for k, v in DEMO_PRESETS.items()
        ]
    })


@app.route("/demo-presets/<preset_id>", methods=["GET"])
def get_demo_preset(preset_id):
    """Return a single preset's code by id."""
    preset = DEMO_PRESETS.get(preset_id)
    if not preset:
        return jsonify({"success": False, "error": "Preset not found"}), 404
    return jsonify({
        "success": True,
        "id": preset_id,
        "title": preset["title"],
        "description": preset["description"],
        "code": preset["code"],
    })

# ==========================
# API KEY CONFIGURATION
# ==========================

def set_gemini_api_key(key):
    """Configure the Gemini API key for the current request/session.

    Stores the key in thread-local storage so concurrent sessions can each
    use a different key without interfering with one another.
    Note: genai.configure() call removed here to avoid the global-mutation
    race described in C-2; per-call clients are used in call_gemini() instead.
    """
    _api_context.gemini_key = key

@app.route("/api-config", methods=["POST"])
def api_config():
    """Set the Gemini API key for the session."""
    body = safejson()
    api_key = safe(body.get("api_key"), "")

    if not api_key or api_key == "Insert_API_Key_Here":
        return jsonify({"success": False, "error": "Invalid API key"}), 400

    try:
        set_gemini_api_key(api_key)
        test_response = call_gemini("Say 'OK'", "Test", language="en")
        if test_response.startswith("AI service error:") or \
           test_response.startswith("AI service is currently unavailable:") or \
           test_response == "AI service not configured. Please set GEMINI_API_KEY environment variable or configure via /api-config." or \
           test_response == "AI service disabled":
            return jsonify({"success": False, "error": "API key is invalid or Gemini API is unavailable"}), 401
        return jsonify({"success": True, "message": "API key configured successfully"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ==========================
# ERROR EXPLAINER
# ==========================

def sanitize_traceback(traceback_str: str) -> str:
    """Remove sensitive information from traceback before sending to LLM."""
    lines = traceback_str.split('\n')
    sanitized = []
    for line in lines:
        line = re.sub(r'[A-Za-z]:[/\\][^:\n]*', '<path>', line)   # Windows paths
        line = re.sub(r'/home/[^:]*', '<path>', line)              # Linux /home
        line = re.sub(r'/Users/[^:]*', '<path>', line)             # macOS /Users
        line = re.sub(r'/var/[^:]*', '<path>', line)               # Linux /var
        # FIX M-1: Also sanitize /tmp/ paths so subprocess temp-script paths
        # (e.g. /tmp/tmpXXXX.py) are not leaked to the Gemini LLM or the client.
        line = re.sub(r'/tmp/[^:]*', '<path>', line)               # Linux /tmp
        sanitized.append(line)
    return '\n'.join(sanitized)

def explain_error(code: str, err_text: str, language="en", beginner=False) -> str:
    if beginner:
        if language == "hi":
            system = (
                "आप एक धैर्यवान शिक्षक हैं जो बिल्कुल नए पायथन सीखने वाले को समझा रहे हैं।\n"
                "मान लें कि उन्होंने पहले कभी programming नहीं की है।\n"
                "Technical jargon use न करें — 'NameError' या 'TypeError' न कहें।\n"
                "Real-life analogy दें। फिर बताएं कि कौन सी line में problem है और exact क्या type करना है।\n"
                "अधिकतम 5 बहुत simple वाक्य।"
            )
        else:
            system = (
                "You are a patient teacher explaining an error to someone brand new to "
                "Python — assume they have never coded before.\n"
                "Avoid jargon entirely. Do not say 'NameError' or 'TypeError'. Say what "
                "happened in plain English, like you are talking to a friend.\n"
                "Use a real-life analogy if it helps. Then tell them which line has the "
                "problem and exactly what to type to fix it.\n"
                "Maximum 5 very simple sentences. Be warm and encouraging."
            )
    elif language == "hi":
        system = (
            "आप एक पायथन ट्यूटर हैं जो एक दृष्टिबाधित-केंद्रित IDE में काम करते हैं।\n"
            "उपयोगकर्ता के कोड और त्रुटि को देखते हुए, समझाएं:\n"
            "- क्या त्रुटि हुई\n"
            "- किस पंक्ति पर (यदि दृश्यमान हो)\n"
            "- इसका सरल शब्दों में क्या अर्थ है\n"
            "- इसे कैसे ठीक करें\n"
            "अगर error में input() का mention है, समझाएं कि CodeUp में inputs को पहले "
            "declare करना होता है — magic comment '# inputs: मान1, मान2' से या inputs panel से।\n"
            "अधिकतम 6 छोटी पंक्तियां। सीधे रहें।"
        )
    else:
        system = (
            "You are a Python tutor in a blind-first IDE.\n"
            "Given the user's code and the error, explain:\n"
            "- What error happened\n"
            "- On which line (if visible)\n"
            "- What it means in simple terms\n"
            "- How to fix it\n"
            "If the error mentions input() needing pre-flight values, explain that "
            "CodeUp uses a pre-flight input queue: declare values with a magic comment "
            "like '# inputs: Alice, 17' at the top, or fill the inputs panel, or "
            "switch to live input mode.\n"
            "Max 6 short lines. Be direct."
        )
    safe_error = sanitize_traceback(err_text)
    user = f"Code:\n```python\n{code}\n```\n\nError:\n```\n{safe_error}\n```"
    return call_gemini(system, user, language=language)


@app.route("/explain-error-beginner", methods=["POST"])
def explain_error_beginner():
    """Beginner-friendly error explanation. Same input as /run's error path
    but uses the gentle-tutor system prompt."""
    body = safejson()
    code = safe(body.get("code"), "")
    error_text = safe(body.get("error"), "")
    language = safe(body.get("language"), "en")
    if len(code) > MAX_CODE_SIZE:
        return jsonify({"success": False, "error": f"Code too large"}), 413
    if not error_text.strip():
        return jsonify({"success": False, "error": "No error provided"}), 400
    explanation = explain_error(code, error_text, language=language, beginner=True)
    return jsonify({"success": True, "explanation": explanation})

# ==========================
# RUN CODE (WITH AI ERROR EXPLANATION)
# ==========================

# Note: in-process execution (run_with_trace, SAFE_GLOBALS, SafeModule, etc.)
# was removed. All user code runs in the subprocess sandbox below.

def classify_semantic_errors(trace):
    """
    ⚠️ HEURISTIC DETECTION (Assistance Signal, Not Guaranteed)

    These are heuristic patterns, not rigorous analysis. The real safety
    limits are the subprocess timeout, the MAX_TRACE_EVENTS cap, and the
    POSIX RLIMIT_AS / RLIMIT_CPU caps applied via preexec_fn.
    """
    issues = []
    execution_count = {}
    truncated = False

    for event in trace:
        if event.get("type") == "overflow":
            truncated = True
            continue
        if event.get("type") in ("state_change", "line_exec"):
            line = event["line"]
            execution_count[line] = execution_count.get(line, 0) + 1

    # 2000 is the sweet spot:
    #   - Catches genuinely runaway code: tight loops with no termination,
    #     recursion that's clearly wrong, accidental infinite-ish iteration.
    #   - Stays above legitimate classroom exercises: a range(100) loop,
    #     a nested 30x30, a prime sieve to 100 — all comfortably below.
    #   - Sits below the 5000 trace cap so the warning can actually fire
    #     before truncation makes the count meaningless.
    # Previous 4500 was dead code (above truncation); 800 fired on legit
    # nested-loop demos. 2000 was tuned against the bundled demo presets.
    HIGH_ITERATION_THRESHOLD = 2000
    for line, count in execution_count.items():
        if count > HIGH_ITERATION_THRESHOLD:
            note = (f"Line {line} executed {count} times. The program completed "
                    f"successfully, but if this looks higher than you expected, "
                    f"check whether your loop terminates correctly.")
            if truncated:
                note += " (Trace was truncated — actual count may be higher.)"
            issues.append({
                "category": "High iteration count",
                "line": line,
                "message": note,
            })

    return issues


def save_execution_trace(trace, duration_ms=0):
    """Store trace in session storage for replay features.

    FIX H-3: All mutations to the session dict now happen inside the lock so
    that two concurrent requests for the same session cannot race on
    storage['last_trace'] etc. Previously get_trace_storage() released the
    lock before returning, leaving mutations unprotected.
    """
    session_id = get_session_id()
    with _session_traces_lock:
        if session_id not in _session_traces:
            _session_traces[session_id] = _make_session_storage()
        storage = _session_traces[session_id]
        storage['last_trace'] = trace or []
        storage['current_trace_index'] = -1
        storage['trace_timestamp'] = time.time()
        storage['trace_duration_ms'] = duration_ms
        storage['last_accessed'] = time.time()
    cleanup_old_sessions()



# Magic comment parser for `# inputs: foo, bar, baz` declared at top of code
_INPUT_MAGIC_RE = re.compile(r'^\s*#\s*inputs?\s*:\s*(.+)$', re.IGNORECASE | re.MULTILINE)

def _parse_magic_inputs(code: str):
    """Look for `# inputs: a, b, c` near the top of the file (first 5 lines).

    Returns a list of input strings, or [] if no magic comment found.
    Comma-separated; whitespace stripped per item.
    """
    head = '\n'.join(code.splitlines()[:5])
    m = _INPUT_MAGIC_RE.search(head)
    if not m:
        return []
    raw = m.group(1).strip()
    if not raw:
        return []
    return [item.strip() for item in raw.split(',') if item.strip()]


# Track last output per session so we can narrate diffs on next run
_last_outputs = {}  # session_id -> {"output": str, "timestamp": float}
_last_outputs_lock = threading.Lock()


def _compute_output_diff(prev: str, curr: str) -> dict:
    """Return a structured diff between two outputs suitable for narration.

    Returns dict with: identical (bool), summary (str), changed_lines (list of
    {line_no, before, after, kind}). Kind is 'added', 'removed', or 'changed'.
    """
    if prev == curr:
        return {"identical": True, "summary": "Output is identical to the previous run.", "changed_lines": []}
    if not prev:
        return {"identical": False, "summary": "First run — no previous output to compare.", "changed_lines": []}

    import difflib
    prev_lines = prev.splitlines()
    curr_lines = curr.splitlines()
    matcher = difflib.SequenceMatcher(None, prev_lines, curr_lines)
    changes = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            continue
        if tag == 'replace':
            # Split unequal-length replace into a paired "changed" region
            # plus a trailing add or delete. Pairing past min() drifts the
            # line numbers because we're indexing into curr while the extra
            # rows belong to prev (or vice versa).
            paired = min(i2 - i1, j2 - j1)
            for k in range(paired):
                changes.append({
                    "line_no": j1 + k + 1,
                    "before": prev_lines[i1 + k],
                    "after": curr_lines[j1 + k],
                    "kind": "changed",
                })
            # Extra rows in prev → removed
            for k in range(paired, i2 - i1):
                changes.append({
                    "line_no": j1 + paired + 1,
                    "before": prev_lines[i1 + k],
                    "after": "",
                    "kind": "removed",
                })
            # Extra rows in curr → added
            for k in range(paired, j2 - j1):
                changes.append({
                    "line_no": j1 + k + 1,
                    "before": "",
                    "after": curr_lines[j1 + k],
                    "kind": "added",
                })
        elif tag == 'delete':
            for k in range(i1, i2):
                changes.append({
                    "line_no": k + 1,
                    "before": prev_lines[k],
                    "after": "",
                    "kind": "removed",
                })
        elif tag == 'insert':
            for k in range(j1, j2):
                changes.append({
                    "line_no": k + 1,
                    "before": "",
                    "after": curr_lines[k],
                    "kind": "added",
                })

    # Cap at first 5 changes to avoid speech overload
    capped = changes[:5]
    if len(changes) <= 1:
        summary = f"{len(changes)} line changed since last run."
    else:
        more = f" (and {len(changes) - 5} more)" if len(changes) > 5 else ""
        summary = f"{len(changes)} lines changed since last run{more}."
    return {
        "identical": False,
        "summary": summary,
        "changed_lines": capped,
        "total_changes": len(changes),
    }


@app.route("/run", methods=["POST"])
def run_code():
    body = safejson()
    code = safe(body.get("code"), "")
    # Mechanism A: pre-flight inputs. List of strings. Body wins; magic
    # comment is the fallback so students can ship reproducible examples.
    inputs_from_body = body.get("inputs")
    if not isinstance(inputs_from_body, list):
        inputs_from_body = None
    inputs = inputs_from_body if inputs_from_body is not None else _parse_magic_inputs(code)
    # Sanitize: stringify, cap length per item and total count
    inputs = [str(x)[:1000] for x in inputs[:50]]

    if not _check_run_rate_limit(get_session_id()):
        return jsonify({
            "success": False,
            "error": f"Rate limit exceeded. Max {RUN_RATE_LIMIT} runs per {RUN_RATE_WINDOW} seconds."
        }), 429

    if len(code) > MAX_CODE_SIZE:
        return jsonify({"success": False, "error": f"Code too large (max {MAX_CODE_SIZE} bytes)"}), 413

    if not code.strip():
        return jsonify({"success": False, "error": "Code cannot be empty"}), 400

    # Heuristic: detect input() use without provided inputs and surface a
    # friendly hint up front. The subprocess will still raise the canonical
    # error if it actually hits input() with an empty queue, but this helps
    # catch the common case before the user waits for execution.
    uses_input = bool(re.search(r'\binput\s*\(', code))
    inputs_hint = None
    if uses_input and not inputs:
        inputs_hint = (
            "Your code uses input(), but you did not provide any pre-flight "
            "inputs. The first input() call will fail with a clear error "
            "telling you what to do. To fix: open the inputs panel and add "
            "values, or add a magic comment like '# inputs: Alice, 17' at "
            "the top of your code, or switch to live input mode."
        )

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    try:
        execution_start = time.time()
        sandbox = get_sandbox(get_session_id())
        workspace_dir = sandbox.workspace_dir
        trace_file = os.path.join(workspace_dir, f"trace_{uuid.uuid4().hex}.json")

        _runner_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sandbox_runner.py')

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False,
                                          encoding='utf-8', dir=workspace_dir) as code_file:
            code_file.write(code)
            code_file_path = code_file.name

        # Write inputs queue to its own file. Empty file if no inputs — the
        # subprocess handles that gracefully.
        inputs_file_path = None
        if inputs:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False,
                                              encoding='utf-8', dir=workspace_dir) as if_handle:
                for item in inputs:
                    # Strip newlines from each input — they're line-delimited
                    if_handle.write(item.replace('\n', ' ').replace('\r', ' ') + '\n')
                inputs_file_path = if_handle.name

        time_limit = 5
        try:
            env = os.environ.copy()
            env['CODEUP_CODE_FILE'] = code_file_path
            env['CODEUP_TRACE_FILE'] = trace_file
            if inputs_file_path:
                env['CODEUP_INPUTS_FILE'] = inputs_file_path
            # Make sure interactive mode is OFF for the standard /run path
            env.pop('CODEUP_INTERACTIVE', None)
            env.pop('CODEUP_INPUT_FIFO', None)
            env.pop('CODEUP_EXEC_CODE', None)

            preexec = None
            if sys.platform != "win32":
                preexec = _set_subprocess_limits

            popen_kwargs = dict(
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                cwd=workspace_dir,
                text=True,
            )
            if sys.platform != "win32":
                popen_kwargs["preexec_fn"] = preexec
                popen_kwargs["start_new_session"] = True
            proc_handle = subprocess.Popen([sys.executable, _runner_path], **popen_kwargs)
            try:
                proc_stdout, proc_stderr = proc_handle.communicate(timeout=max(1, int(time_limit)))
                stdout_buf.write(proc_stdout or "")
                stderr_buf.write(proc_stderr or "")
            except subprocess.TimeoutExpired:
                try:
                    if sys.platform != "win32":
                        import signal as _signal
                        os.killpg(os.getpgid(proc_handle.pid), _signal.SIGKILL)
                    else:
                        proc_handle.kill()
                except Exception:
                    pass
                try:
                    proc_handle.communicate(timeout=2)
                except Exception:
                    pass
                stderr_buf.write(f"Execution timed out after {time_limit}s (subprocess)")
        finally:
            for _tmp in (code_file_path, inputs_file_path):
                if _tmp:
                    try:
                        os.unlink(_tmp)
                    except OSError:
                        pass

        trace = []
        trace_error = None
        try:
            if os.path.exists(trace_file):
                with open(trace_file, 'r', encoding='utf-8') as tfh:
                    data = json.load(tfh)
                    trace = data.get('trace', [])
            else:
                trace_error = 'Trace file not found in workspace'
        except json.JSONDecodeError:
            trace_error = 'Trace data was corrupted or incomplete'
        except Exception as e:
            trace_error = f'Error reading trace: {str(e)}'
        finally:
            try:
                if os.path.exists(trace_file):
                    os.unlink(trace_file)
            except OSError:
                pass

        if not trace:
            msg = trace_error or 'No detailed trace available from subprocess (likely timed out or crashed)'
            trace = [{'type': 'subprocess_exec', 'note': msg}]

        semantic_issues = classify_semantic_errors(trace) if trace else []
        duration_ms = int((time.time() - execution_start) * 1000)
        save_execution_trace(trace, duration_ms)

        output = stdout_buf.getvalue()
        error = stderr_buf.getvalue()

        # Compute output diff vs last run (only on success — error states aren't
        # comparable in a useful way)
        diff_info = None
        if not error.strip():
            session_id = get_session_id()
            with _last_outputs_lock:
                prev_record = _last_outputs.get(session_id)
                prev_output = prev_record["output"] if prev_record else ""
                _last_outputs[session_id] = {"output": output, "timestamp": time.time()}
            diff_info = _compute_output_diff(prev_output, output)

        if error.strip():
            explanation = explain_error(code, error, language=safe(body.get("language"), "en"))
            return jsonify({
                "success": False,
                "error": error,
                "explanation": explanation,
                "inputs_hint": inputs_hint,
            })

        return jsonify({
            "success": True,
            "output": output or "Program finished with no output.",
            "trace": trace,
            "semantic_issues": semantic_issues,
            "diff": diff_info,
            "inputs_consumed": len(inputs),
            "inputs_provided": len(inputs),
            "inputs_hint": inputs_hint,
        })

    except Exception:
        tb = traceback.format_exc()
        explanation = explain_error(code, tb, language=safe(body.get("language"), "en"))
        return jsonify({
            "success": False,
            "error": tb,
            "explanation": explanation,
            "inputs_hint": inputs_hint,
        })


# ==========================
# ANALYZE
# ==========================

@app.route("/analyze", methods=["POST"])
def analyze():
    body = safejson()
    code = safe(body.get("code"), "")
    language = safe(body.get("language"), "en")

    if len(code) > MAX_CODE_SIZE:
        return jsonify({"success": False, "error": f"Code too large (max {MAX_CODE_SIZE} bytes)"}), 413
    if not code.strip():
        return jsonify({"success": False, "error": "Code cannot be empty"}), 400

    if language == "hi":
        system = (
            "आप blind student के लिए conversational Python tutor हैं।\n"
            "Code का BRIEF analysis दें — 4 से 5 छोटी lines में:\n"
            "1. यह code overall क्या करता है\n"
            "2. कौन सी 2-3 main techniques use हुई हैं\n"
            "3. कोई obvious bug या edge case (अगर हो)\n\n"
            "End में पूछें: 'क्या आप line by line deeper explanation सुनना चाहते हैं? बोलें: analyze deeper'\n"
            "Markdown headers न use करें। Spoken Hindi/English में लिखें।"
        )
    else:
        system = (
            "You are a conversational Python tutor for a blind student.\n"
            "Give a BRIEF analysis in 4 to 5 short lines:\n"
            "1. What this code does overall (one line)\n"
            "2. The 2 or 3 main techniques used (e.g., 'uses a for loop with range', 'recursive function')\n"
            "3. Any obvious bug or edge case (if any)\n\n"
            "End with: 'Want a deeper line by line walkthrough? Just say: analyze deeper.'\n"
            "No markdown headers. No bullet points. Spoken English only."
        )

    user = f"Python code:\n```python\n{code}\n```"
    analysis = call_gemini(system, user, language=language)

    analyzer = CodeAnalyzer()
    structure = analyzer.analyze(code)
    param_info = []

    if structure.get("functions"):
        for func in structure["functions"]:
            if func.get("params"):
                typed_params = []
                for param in func["params"]:
                    if isinstance(param, dict) and param.get("type"):
                        typed_params.append(f"{param['name']} ({param['type']})")
                    elif isinstance(param, dict):
                        typed_params.append(param.get("name", "unknown"))
                    else:
                        typed_params.append(str(param))
                if typed_params:
                    param_info.append(f"Function {func['name']} takes: {', '.join(typed_params)}")

    speech_text = analysis
    if param_info:
        speech_text = analysis + "\n" + "Parameters: " + " ".join(param_info)

    return jsonify({"analysis": analysis, "param_info": param_info, "speech": speech_text, "auto_speak": True})

@app.route("/analyze-deep", methods=["POST"])
def analyze_deep():
    body = safejson()
    code = safe(body.get("code"), "")
    language = safe(body.get("language"), "en")

    if len(code) > MAX_CODE_SIZE:
        return jsonify({"success": False, "error": f"Code too large (max {MAX_CODE_SIZE} bytes)"}), 413
    if not code.strip():
        return jsonify({"success": False, "error": "Code cannot be empty"}), 400

    if language == "hi":
        system = (
            "आप blind student के लिए expert Python tutor हैं। Code का DETAILED line-by-line analysis दें:\n"
            "हर logical block (loop, function, condition) को explain करें।\n"
            "हर built-in function (print, range, len, int, str, etc.) का नाम लें और बताएं वो क्या करता है।\n"
            "Variables का role बताएं।\n"
            "Symbols को words में लिखें: == 'equals equals', != 'not equals'।\n"
            "Format: 'Lines X to Y: explanation'। Plain text paragraphs। कोई markdown नहीं।"
        )
    else:
        system = (
            "You are an expert Python tutor for a blind student. Give a DETAILED line-by-line walkthrough:\n"
            "Walk through each logical block (loop, function, conditional, etc.).\n"
            "Name every built-in function used (print, range, len, int, str, etc.) and explain what each does.\n"
            "Name variables and explain their role.\n"
            "For symbols use words: == as 'equals equals', != as 'not equals', <= as 'less than or equal'.\n"
            "Format: 'Lines X to Y: explanation'. Plain text paragraphs. No markdown."
        )

    user = f"Python code:\n```python\n{code}\n```"
    analysis = call_gemini(system, user, language=language)
    return jsonify({"analysis": analysis, "speech": analysis, "auto_speak": True})

# ==========================
# ADVISE (FEATURE / IMPROVEMENT SUGGESTIONS)
# ==========================

@app.route("/advise", methods=["POST"])
def advise():
    body = safejson()
    code = safe(body.get("code"), "")
    language = safe(body.get("language"), "en")

    if len(code) > MAX_CODE_SIZE:
        return jsonify({"success": False, "error": f"Code too large (max {MAX_CODE_SIZE} bytes)"}), 413
    if not code.strip():
        return jsonify({"success": False, "error": "Code cannot be empty"}), 400

    if language == "hi":
        system = (
            "आप एक शुरुआती को मार्गदर्शन देने वाले वरिष्ठ पायथन इंजीनियर हैं।\n"
            "उनके कोड को देखते हुए, 3-7 ठोस सुधार सुझाएं:\n"
            "- नई सुविधाएं जो वे जोड़ सकते हैं\n"
            "- इसे साफ करने के लिए रीफैक्टर\n"
            "- संभालने के लिए edge cases\n"
            "स्पष्ट बुलेट पॉइंट्स लौटाएं। संक्षिप्त, सीधा।"
        )
    else:
        system = (
            "You are a senior Python engineer mentoring a beginner.\n"
            "Given their code, suggest 3–7 concrete improvements:\n"
            "- New features they could add\n"
            "- Refactors to make it cleaner\n"
            "- Edge cases to handle\n"
            "Return clear bullet points. Short, direct."
        )

    user = f"Code:\n```python\n{code}\n```"
    advice = call_gemini(system, user, language=language)
    return jsonify({"advice": advice})

# ==========================
# INLINE DEBUG SUGGESTIONS
# ==========================

@app.route("/debug-suggestions", methods=["POST"])
def debug_suggestions():
    body = safejson()
    code = safe(body.get("code"), "")
    language = safe(body.get("language"), "en")

    if len(code) > MAX_CODE_SIZE:
        return jsonify({"success": False, "error": f"Code too large (max {MAX_CODE_SIZE} bytes)"}), 413
    if not code.strip():
        return jsonify({"success": True, "suggestions": []})

    if language == "hi":
        system = (
            "आप एक पायथन डीबगर सहायक हैं।\n"
            "कोड को देखें और सुधार के लिए विशिष्ट सुझाव दें।\n"
            "प्रत्येक सुझाव अलग लाइन पर हो:\n"
            "⚠️ [समस्या description]\n"
            "💡 [सुझाव]\n"
            "केवल वास्तविक समस्याओं को सूचीबद्ध करें।"
        )
    else:
        system = (
            "You are a Python debugging assistant.\n"
            "Review the code and suggest specific improvements.\n"
            "Each suggestion on a separate line:\n"
            "⚠️ [issue description]\n"
            "💡 [suggestion]\n"
            "Only list actual problems."
        )

    user = f"Code:\n```python\n{code}\n```"
    suggestions = call_gemini(system, user, language=language)

    lines = suggestions.split('\n')
    parsed_suggestions = []

    for line in lines:
        line = line.strip()
        if line.startswith('⚠️'):
            parsed_suggestions.append({"type": "warning", "icon": "⚠️", "text": line[2:].strip()})
        elif line.startswith('💡'):
            parsed_suggestions.append({"type": "suggestion", "icon": "💡", "text": line[2:].strip()})

    return jsonify({"success": True, "suggestions": parsed_suggestions})

# ==========================
# DESCRIBE LINE
# ==========================

@app.route("/describe", methods=["POST"])
def describe():
    body = safejson()
    code = safe(body.get("code"), "")

    # FIX M-2: Added MAX_CODE_SIZE check (was missing from this endpoint).
    if len(code) > MAX_CODE_SIZE:
        return jsonify({"success": False, "error": f"Code too large (max {MAX_CODE_SIZE} bytes)"}), 413

    # FIX C-4: Wrap int() cast in try/except so non-numeric "line" values
    # return a 400 instead of an unhandled 500 ValueError/TypeError.
    try:
        line = int(body.get("line", 1))
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "Invalid line number"}), 400

    language = safe(body.get("language"), "en")

    lines = code.splitlines()
    if not lines or line < 1 or line > len(lines):
        return jsonify({"success": False, "message": "Invalid line number."})

    start = max(1, line - 3)
    end = min(len(lines), line + 3)
    context = "\n".join(f"{i+1}: {lines[i]}" for i in range(start - 1, end))

    if language == "hi":
        system = (
            "आप एक दृष्टिबाधित डेवलपर के लिए केवल TARGET Python पंक्ति की व्याख्या करते हैं।\n"
            "सरल भाषा का प्रयोग करें। अधिकतम 3 छोटी पंक्तियां।"
        )
    else:
        system = (
            "You explain ONLY the target Python line for a blind developer.\n"
            "Use simple language. Max 3 short lines."
        )

    user = f"Code context:\n{context}\nTarget line: {line}"
    desc = call_gemini(system, user, language=language)
    return jsonify({"success": True, "description": desc})

# ==========================
# STRUCTURE PANEL (CODE NAVIGATION)
# ==========================

@app.route("/structure", methods=["POST"])
def structure():
    body = safejson()
    code = safe(body.get("code"), "")

    if len(code) > MAX_CODE_SIZE:
        return jsonify({"success": False, "error": f"Code too large (max {MAX_CODE_SIZE} bytes)"}), 413
    if not code.strip():
        return jsonify({"success": True, "structure": {
            "imports": [], "functions": [], "classes": [], "loops": []
        }})

    analyzer = CodeAnalyzer()
    structure_data = analyzer.analyze(code)

    if "error" in structure_data:
        return jsonify({"success": False, "error": structure_data["error"]})

    return jsonify({"success": True, "structure": structure_data})

# ==========================
# READ LINE WITH CONTEXT
# ==========================

@app.route("/read-line-context", methods=["POST"])
def read_line_context():
    body = safejson()
    code = safe(body.get("code"), "")

    # FIX M-2: Added MAX_CODE_SIZE check (was missing from this endpoint).
    if len(code) > MAX_CODE_SIZE:
        return jsonify({"success": False, "error": f"Code too large (max {MAX_CODE_SIZE} bytes)"}), 413

    # FIX C-4: Wrap int() cast to return 400 on bad input.
    try:
        line = int(body.get("line", 1))
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "Invalid line number"}), 400

    lines = code.splitlines()
    if not lines or line < 1 or line > len(lines):
        return jsonify({"success": False, "message": "Invalid line number."})

    current_line = lines[line - 1]
    expanded_line = current_line.expandtabs(tabsize=4)
    indent_level = (len(expanded_line) - len(expanded_line.lstrip())) // 4

    context = "top level"
    if line > 1:
        for i in range(line - 2, -1, -1):
            prev = lines[i].strip()
            func_match = re.match(r'^def\s+(\w+)\s*\(', prev)
            if func_match:
                context = f"inside function {func_match.group(1)}"
                break
            class_match = re.match(r'^class\s+(\w+)\s*[\(:]', prev)
            if class_match:
                context = f"inside class {class_match.group(1)}"
                break
            elif prev.startswith("if ") or prev.startswith("elif "):
                context = "inside if block"
                break
            elif prev.startswith("for "):
                context = "inside for loop"
                break
            elif prev.startswith("while "):
                context = "inside while loop"
                break

    if not current_line.strip():
        response = f"Line {line}: blank line, {context}, indentation level {indent_level}"
    else:
        line_type = "code"
        if current_line.strip().startswith("#"):
            line_type = "comment"
        elif current_line.strip().startswith("def "):
            line_type = "function definition"
        elif current_line.strip().startswith("class "):
            line_type = "class definition"
        elif current_line.strip().startswith("return"):
            line_type = "return statement"
        elif current_line.strip().startswith("import ") or current_line.strip().startswith("from "):
            line_type = "import statement"

        response = (
            f"Line {line}, {context}, indentation level {indent_level}, "
            f"{line_type}: {current_line.strip()}"
        )

    return jsonify({
        "success": True,
        "response": response,
        "line": line,
        "indent_level": indent_level,
        "context": context,
        "content": current_line.strip()
    })

# ==========================
# VARIABLE TRACKING
# ==========================

@app.route("/track-variables", methods=["POST"])
def track_variables():
    body = safejson()
    code = safe(body.get("code"), "")

    # FIX M-2: Added MAX_CODE_SIZE check (was missing from this endpoint).
    if len(code) > MAX_CODE_SIZE:
        return jsonify({"success": False, "error": f"Code too large (max {MAX_CODE_SIZE} bytes)"}), 413

    # FIX C-4: Wrap int() cast to return 400 on bad input.
    try:
        line = int(body.get("line", 1))
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "Invalid line number"}), 400

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return jsonify({"success": False, "message": f"Syntax error: {e}"})

    class VariableTracker(ast.NodeVisitor):
        def __init__(self):
            self.variables = {}
            self.scope_stack: List[Tuple[str, Optional[str], int]] = [("global", None, 1)]
            self.scopes: List[dict] = []

        def current_scope(self):
            for kind, name, start in reversed(self.scope_stack):
                if kind != 'global' and name:
                    return name
            return 'global'

        def _record_var(self, name, lineno, is_store=True):
            scope = self.current_scope()
            if name not in self.variables:
                self.variables[name] = {
                    'name': name,
                    'phonetic': pronounce_variable(name),
                    'scope': scope,
                    'first_line': lineno,
                    'usage_count': 0
                }
            if is_store:
                self.variables[name]['usage_count'] += 1

        def _handle_target(self, target, lineno):
            if isinstance(target, ast.Name):
                self._record_var(target.id, lineno, is_store=True)
            elif isinstance(target, (ast.Tuple, ast.List)):
                for elt in target.elts:
                    self._handle_target(elt, lineno)

        def visit_FunctionDef(self, node):
            name = node.name
            start = node.lineno
            end = self._max_lineno(node)
            self.scopes.append({'name': name, 'kind': 'function', 'start': start, 'end': end})
            self.scope_stack.append(('function', name, start))
            for arg in node.args.args:
                self._record_var(arg.arg, node.lineno, is_store=True)
            self.generic_visit(node)
            self.scope_stack.pop()

        def visit_Global(self, node):
            for n in node.names:
                if n in self.variables:
                    self.variables[n]['scope'] = 'global'

        def visit_Nonlocal(self, node):
            for n in node.names:
                if n in self.variables:
                    self.variables[n]['scope'] = 'nonlocal'

        def visit_ListComp(self, node):
            for gen in node.generators:
                self._handle_target(gen.target, getattr(gen, 'lineno', node.lineno))
            self.generic_visit(node)

        def visit_DictComp(self, node):
            for gen in node.generators:
                self._handle_target(gen.target, getattr(gen, 'lineno', node.lineno))
            self.generic_visit(node)

        def visit_SetComp(self, node):
            for gen in node.generators:
                self._handle_target(gen.target, getattr(gen, 'lineno', node.lineno))
            self.generic_visit(node)

        def visit_GeneratorExp(self, node):
            for gen in node.generators:
                self._handle_target(gen.target, getattr(gen, 'lineno', node.lineno))
            self.generic_visit(node)

        def visit_ClassDef(self, node):
            name = node.name
            start = node.lineno
            end = self._max_lineno(node)
            self.scopes.append({'name': name, 'kind': 'class', 'start': start, 'end': end})
            self.scope_stack.append(('class', name, start))
            self.generic_visit(node)
            self.scope_stack.pop()

        def visit_Assign(self, node):
            for target in node.targets:
                self._handle_target(target, node.lineno)
            self.generic_visit(node)

        def visit_AnnAssign(self, node):
            if isinstance(node.target, ast.Name):
                self._record_var(node.target.id, node.lineno, is_store=True)
            else:
                self._handle_target(node.target, node.lineno)
            self.generic_visit(node)

        def visit_For(self, node):
            self._handle_target(node.target, node.lineno)
            self.generic_visit(node)

        def visit_With(self, node):
            for item in node.items:
                if item.optional_vars is not None:
                    self._handle_target(item.optional_vars, node.lineno)
            self.generic_visit(node)

        def visit_Name(self, node):
            if isinstance(node.ctx, ast.Load):
                if node.id in self.variables:
                    self.variables[node.id]['usage_count'] += 1
            elif isinstance(node.ctx, ast.Store):
                if node.id not in self.variables:
                    self._record_var(node.id, node.lineno, is_store=True)

        def _max_lineno(self, node):
            maxn = getattr(node, 'lineno', -1)
            for n in ast.walk(node):
                if hasattr(n, 'lineno'):
                    maxn = max(maxn, getattr(n, 'lineno', -1))
            return maxn

    tracker = VariableTracker()
    tracker.visit(tree)

    current_scope = 'global'
    best_start = -1
    for s in tracker.scopes:
        if s['start'] <= line <= s['end'] and s['start'] > best_start:
            current_scope = s['name']
            best_start = s['start']

    scope_vars = [v for v in tracker.variables.values()
                  if v['scope'] == current_scope or v['scope'] == 'global']

    return jsonify({
        'success': True,
        'current_scope': current_scope,
        'variables': scope_vars,
        'total_count': len(scope_vars)
    })


# Single-letter variable names get NATO-phonetic expansion so screen readers
# don't mangle them ("x" → "ks" or "ex" depending on the engine).
_SINGLE_LETTER_PRONUNCIATION = {
    'a': 'a', 'b': 'bee', 'c': 'see', 'd': 'dee', 'e': 'ee',
    'f': 'eff', 'g': 'gee', 'h': 'aitch', 'i': 'eye', 'j': 'jay',
    'k': 'kay', 'l': 'ell', 'm': 'em', 'n': 'en', 'o': 'oh',
    'p': 'pee', 'q': 'cue', 'r': 'arr', 's': 'ess', 't': 'tee',
    'u': 'you', 'v': 'vee', 'w': 'double-you', 'x': 'ex', 'y': 'why', 'z': 'zee',
}


def pronounce_variable(var_name: str) -> str:
    """Convert variable name to phonetic pronunciation for screen readers."""
    if not var_name or not isinstance(var_name, str):
        return "unknown variable"

    var_name = var_name.strip()
    if not var_name:
        return "unknown variable"

    # Single character — use phonetic spelling to avoid TTS ambiguity
    if len(var_name) == 1:
        return _SINGLE_LETTER_PRONUNCIATION.get(var_name.lower(), var_name)

    if "_" in var_name:
        # Special case for dunders: __init__, __name__, __main__ etc.
        # Pronounce as "dunder X" rather than "underscore underscore X underscore underscore"
        if var_name.startswith("__") and var_name.endswith("__") and len(var_name) > 4:
            inner = var_name[2:-2]
            return f"dunder {inner}"
        segments = var_name.split("_")
        parts = [seg for seg in segments if seg]
        if not parts:
            return "underscore"
        return " underscore ".join(parts)

    camel_parts = []
    current = ""
    for char in var_name:
        if char.isupper() and current:
            camel_parts.append(current)
            current = char.lower()
        else:
            current += char
    if current:
        camel_parts.append(current)

    if len(camel_parts) > 1:
        return " camel case ".join(camel_parts)

    return var_name


@app.route("/find-variable-usage", methods=["POST"])
def find_variable_usage():
    body = safejson()
    code = safe(body.get("code"), "")

    # FIX M-2: Added MAX_CODE_SIZE check (was missing from this endpoint).
    if len(code) > MAX_CODE_SIZE:
        return jsonify({"success": False, "error": f"Code too large (max {MAX_CODE_SIZE} bytes)"}), 413

    var_name = safe(body.get("variable"), "")
    if not var_name:
        return jsonify({"success": False, "message": "No variable specified."})

    lines = code.splitlines()
    usages = []

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return jsonify({
            "success": False,
            "message": "Code has syntax errors; cannot parse variable usage."
        })

    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == var_name:
            line_no = node.lineno
            line_content = lines[line_no - 1] if line_no <= len(lines) else ""

            if isinstance(node.ctx, ast.Store):
                usage_type = "assignment"
            elif isinstance(node.ctx, ast.Load):
                usage_type = "read"
            else:
                usage_type = "usage"

            usages.append({"line": line_no, "content": line_content.strip(), "type": usage_type})

    if not usages:
        return jsonify({"success": False, "message": f"Variable '{var_name}' not found in code."})

    unique_usages = {}
    for u in usages:
        key = (u["line"], u["type"])
        if key not in unique_usages:
            unique_usages[key] = u

    sorted_usages = sorted(unique_usages.values(), key=lambda x: x["line"])

    return jsonify({
        "success": True,
        "variable": var_name,
        "phonetic": pronounce_variable(var_name),
        "usages": sorted_usages,
        "count": len(sorted_usages)
    })


# ==========================
# ERROR LOCATION BEACON
# ==========================

@app.route("/check-syntax", methods=["POST"])
def check_syntax():
    body = safejson()
    code = safe(body.get("code"), "")

    if not code.strip():
        return jsonify({"success": True, "has_errors": False, "message": "Code is empty."})

    errors = []

    try:
        compile(code, "<syntax_check>", "exec")
        return jsonify({"success": True, "has_errors": False, "message": "No syntax errors detected."})
    except IndentationError as e:
        errors.append({
            "line": e.lineno or 1,
            "type": "IndentationError",
            "message": str(e.msg or "Indentation error"),
            "severity": "high"
        })
    except SyntaxError as e:
        error_type = "SyntaxError"
        if "unexpected EOF" in str(e).lower():
            error_type = "MissingClosing"
        elif "invalid syntax" in str(e).lower():
            error_type = "InvalidSyntax"

        errors.append({
            "line": e.lineno or 1,
            "type": error_type,
            "message": str(e.msg or "Syntax error"),
            "severity": "high"
        })
    except Exception as e:
        errors.append({"line": 1, "type": "UnknownError", "message": str(e), "severity": "medium"})

    # FIX M-3: Only run the heuristic undefined-variable ast.parse() block when
    # errors is empty (i.e. compile() succeeded). Previously the code fell through
    # to ast.parse() even after a SyntaxError from compile(), causing a redundant
    # and wasteful re-parse of known-invalid code.
    if not errors:
        try:
            tree = ast.parse(code)
            defined = set()
            used_module_level = set()
            params = set()

            class UseCollector(ast.NodeVisitor):
                def __init__(self):
                    self.current_function = None

                def visit_FunctionDef(self, node):
                    for a in node.args.args:
                        params.add(a.arg)
                    prev = self.current_function
                    self.current_function = node
                    self.generic_visit(node)
                    self.current_function = prev

                def visit_For(self, node):
                    if isinstance(node.target, ast.Name):
                        params.add(node.target.id)
                    self.generic_visit(node)

                def visit_Assign(self, node):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            defined.add(target.id)
                    self.generic_visit(node)

                def visit_Name(self, node):
                    if isinstance(node.ctx, ast.Load):
                        if self.current_function is None:
                            used_module_level.add(node.id)

            UseCollector().visit(tree)

            builtins = {
                "abs", "all", "any", "ascii", "bin", "bool", "bytearray", "bytes",
                "chr", "classmethod", "compile", "complex", "delattr", "dict", "dir",
                "divmod", "enumerate", "eval", "exec", "filter", "float", "format",
                "frozenset", "getattr", "globals", "hasattr", "hash", "help", "hex",
                "id", "input", "int", "isinstance", "issubclass", "iter", "len",
                "list", "locals", "map", "max", "memoryview", "min", "next", "object",
                "oct", "open", "ord", "pow", "print", "property", "range", "repr",
                "reversed", "round", "set", "setattr", "slice", "sorted",
                "staticmethod", "str", "sum", "super", "tuple", "type", "vars", "zip",
                "BaseException", "Exception", "ArithmeticError", "AssertionError",
                "AttributeError", "EOFError", "ImportError", "IndexError", "KeyError",
                "KeyboardInterrupt", "MemoryError", "NameError", "NotImplementedError",
                "OSError", "RuntimeError", "SyntaxError", "SystemError", "SystemExit",
                "TypeError", "ValueError", "ZeroDivisionError",
                "True", "False", "None", "NotImplemented", "Ellipsis", "__debug__"
            }
            undefined = used_module_level - defined - builtins - params

            for var in sorted(undefined):
                errors.append({
                    "line": 0,
                    "type": "Potential undefined variable (heuristic)",
                    "message": f"Variable '{var}' may be used before assignment at module level",
                    "severity": "low"
                })
        except Exception:
            pass

    return jsonify({
        "success": True,
        "has_errors": len(errors) > 0,
        "errors": errors,
        "error_count": len(errors)
    })

# ==========================
# FIX
# ==========================

@app.route("/fix", methods=["POST"])
def fix():
    body = safejson()
    code = safe(body.get("code"), "")
    language = safe(body.get("language"), "en")

    if len(code) > MAX_CODE_SIZE:
        return jsonify({"success": False, "error": f"Code too large (max {MAX_CODE_SIZE} bytes)"}), 413
    if not code.strip():
        return jsonify({"success": False, "error": "Code cannot be empty"}), 400

    if language == "hi":
        system = (
            "आप एक expert Python debugger हैं जो blind-first IDE में काम करते हैं।\n"
            "नीचे दिए गए कोड में हर तरह की समस्या ढूंढें और ठीक करें:\n"
            "1. Syntax errors (missing colons, unmatched parentheses, indentation)\n"
            "2. Runtime errors (NameError, TypeError, IndexError, ZeroDivisionError, KeyError)\n"
            "3. Logic bugs (off-by-one, wrong comparison operator, wrong variable used, missing return)\n"
            "4. CodeUp-specific: input() function BLOCKED है — इसे hardcoded values से replace करें (e.g. name = 'Alice')\n"
            "5. Edge cases (empty list, division by zero, negative numbers जहां positive expected)\n"
            "6. Bad practices (mutable default arguments, comparing with == None instead of is None)\n\n"
            "CRITICAL: केवल actual bugs ठीक करें। नए features या type checks add NA करें।\n"
            "अगर code पहले से ठीक है तो उसे वैसा ही return करें।\n"
            "isinstance() या type() जैसी checks केवल तब add करें जब आप 100% sure हैं कि second argument एक valid type है।\n"
            "हर महत्वपूर्ण fix के ऊपर एक comment add करें।\n"
            "Original intent maintain करें — completely re-write न करें।\n"
            "केवल valid Python code लौटाएं। कोई markdown fences नहीं।"
        )
    else:
        system = (
            "You are an expert Python debugger for a blind-first IDE.\n"
            "Find and fix EVERY type of problem in the code below:\n"
            "1. Syntax errors (missing colons, unmatched parens, bad indentation)\n"
            "2. Runtime errors (NameError, TypeError, IndexError, ZeroDivisionError, KeyError)\n"
            "3. Logic bugs (off-by-one, wrong comparison operator, wrong variable, missing return)\n"
            "4. CodeUp-specific: the input() function is BLOCKED in this sandbox. Replace any input() call with a hardcoded sample value (e.g. name = 'Alice'  instead of  name = input('Your name? '))\n"
            "5. Edge cases (empty list, division by zero, negative numbers where positive expected)\n"
            "6. Bad practices (mutable default args, comparing with == None instead of is None, bare except clauses)\n\n"
            "Add a brief comment above each meaningful fix explaining WHAT changed and WHY. A blind student will hear these comments via screen reader.\n"
            "Preserve original intent — do not rewrite from scratch.\n"
            "Return only valid Python code. NO markdown fences. NO prose outside code comments."
        )

    user = f"Fix this code:\n```python\n{code}\n```"
    raw = call_gemini(system, user, temperature=0.1, language=language)
    fixed = extract_code(raw)
    if not fixed and raw and not raw.startswith("AI service"):
        fixed = raw.strip()

    # Reject suspicious "fixes" that bear no resemblance to the original. The LLM
    # sometimes ignores "do not rewrite from scratch" and ships an unrelated
    # solution, which is dangerous because the student loses their work.
    if fixed and code:
        import difflib
        ratio = difflib.SequenceMatcher(None, code, fixed).ratio()
        if ratio < 0.3:
            retry_system = system + "\n\nCRITICAL: Your previous answer was rejected because it was too different from the user's original code. Make MINIMAL changes — preserve variable names, structure, and overall approach. Only fix the specific bugs."
            raw_retry = call_gemini(retry_system, user, temperature=0.05, language=language)
            retry_fixed = extract_code(raw_retry) or (raw_retry.strip() if raw_retry and not raw_retry.startswith("AI service") else "")
            if retry_fixed:
                retry_ratio = difflib.SequenceMatcher(None, code, retry_fixed).ratio()
                if retry_ratio >= 0.3:
                    fixed = retry_fixed
    return jsonify({"success": True, "code": fixed})

# ==========================
# GENERATE CODE (NL → CODE)
# ==========================

@app.route("/generate-code", methods=["POST"])
def generate_code():
    body = safejson()
    prompt = safe(body.get("prompt"), "")
    language = safe(body.get("language"), "en")

    if len(prompt) > MAX_CODE_SIZE:
        return jsonify({"success": False, "error": f"Prompt too large (max {MAX_CODE_SIZE} bytes)"}), 413
    if not prompt.strip():
        return jsonify({"success": False, "error": "Prompt cannot be empty"}), 400

    if language == "hi":
        system = (
            "आप एक beginner-friendly, blind-first Python IDE (CodeUp) के लिए code generator हैं।\n"
            "User प्राकृतिक भाषा में task बताएगा। आप उसे हल करने वाला Python code generate करें।\n\n"
            "महत्वपूर्ण constraints:\n"
            "1. input() function का use NEVER करें। यह CodeUp sandbox में blocked है।\n"
            "   Instead: variables को hardcoded sample values दें (e.g. length = 10, width = 5, name = 'Alice')\n"
            "   जब user input की जरूरत हो तो उन values को directly assign करें।\n"
            "2. केवल इन modules का use कर सकते हैं: math, random, string, datetime। बाकी कुछ blocked है।\n"
            "3. open(), eval(), exec(), __import__() का NEVER use करें — सब blocked हैं।\n"
            "4. हर महत्वपूर्ण line के ऊपर एक छोटी comment add करें जो शुरुआती समझ सकें।\n"
            "5. Code के end में print() statements add करें ताकि user output देख सके।\n\n"
            "केवल Python code लौटाएं। Markdown fences न डालें। कोई prose explanation नहीं।"
        )
    else:
        system = (
            "You are a Python code generator for CodeUp, a beginner-friendly, blind-first IDE.\n"
            "The user will describe a task in natural language. Generate Python code that solves it.\n\n"
            "CRITICAL CONSTRAINTS:\n"
            "1. NEVER use input() — it is BLOCKED in the CodeUp sandbox.\n"
            "   Instead, hardcode sample values directly into variables.\n"
            "   Example: instead of `length = float(input('length?'))` write `length = 10  # sample value, change this to test`\n"
            "   Choose realistic sample values that make the program produce visible output.\n"
            "2. Only these modules are available: math, random, string, datetime. Do NOT import anything else.\n"
            "3. NEVER use open(), eval(), exec(), or __import__() — all blocked.\n"
            "4. Add a brief comment above each non-trivial line explaining what it does, written for a beginner. A blind student will hear these via screen reader.\n"
            "5. Always include print() statements at the end so the user can see the result when they run it.\n"
            "6. For interactive-feeling tasks (menus, calculators, games), use hardcoded sample inputs and explain in a comment how to change them.\n\n"
            "Return ONLY Python code. No markdown fences. No prose outside code comments."
        )

    user = f"Task description:\n{prompt}"
    raw = call_gemini(system, user, temperature=0.2, language=language)
    code = extract_code(raw)
    # Llama sometimes returns code without ``` fences. If extract_code came back empty,
    # try using the raw response directly (assuming it's already plain code).
    if not code and raw and not raw.startswith("AI service"):
        code = raw.strip()
    if not code:
        return jsonify({"success": False, "error": "AI returned empty response. Try rephrasing.", "code": ""})

    # Verify the result actually parses as Python before shipping it to the editor.
    # If the LLM returned an explanation paragraph by mistake, this catches it.
    try:
        compile(code, "<generated>", "exec")
    except SyntaxError:
        # One retry with a stricter system message
        retry_system = system + "\n\nIMPORTANT: Return ONLY syntactically valid Python. No prose. No markdown."
        raw_retry = call_gemini(retry_system, user, temperature=0.1, language=language)
        retry_code = extract_code(raw_retry) or (raw_retry.strip() if raw_retry and not raw_retry.startswith("AI service") else "")
        try:
            compile(retry_code, "<generated>", "exec")
            code = retry_code
        except SyntaxError:
            return jsonify({"success": False, "error": "AI returned invalid Python code. Please try rephrasing your request.", "code": ""})
    return jsonify({"success": True, "code": code})

# ==========================
# SNIPPETS
# ==========================

@app.route("/snippets", methods=["GET", "POST"])
def snippets():
    if request.method == "GET":
        data = load_snippets()
        snippets_list = data.get("snippets", [])

        speech_text = None
        if snippets_list:
            names = [s.get("name", f"Snippet {i+1}") for i, s in enumerate(snippets_list)]
            if len(names) == 1:
                speech_text = f"You have 1 snippet: {names[0]}."
            else:
                speech_text = f"You have {len(names)} snippets: {', '.join(names[:-1])}, and {names[-1]}."
        else:
            speech_text = "You have no saved snippets."

        data["speech"] = speech_text
        return jsonify(data)

    data = load_snippets()
    body = safejson()

    name = str(safe(body.get("name"), "Untitled"))
    code = str(safe(body.get("code"), ""))

    if len(code) > MAX_CODE_SIZE:
        return jsonify({"success": False, "error": f"Code too large (max {MAX_CODE_SIZE} bytes)"}), 413
    if len(name) > 256:
        return jsonify({"success": False, "error": "Name too long (max 256 chars)"}), 400

    new_id = str(uuid.uuid4())
    data["snippets"].append({"id": new_id, "name": name, "code": code})
    save_snippets(data)
    return jsonify({"success": True, "id": new_id, "speech": f"Saved snippet: {name}"})

@app.route("/snippets/<sid>", methods=["PUT", "DELETE"])
def snippet_detail(sid):
    data = load_snippets()

    if request.method == "DELETE":
        deleted_name = None
        for s in data["snippets"]:
            if str(s["id"]) == str(sid):
                deleted_name = s.get("name", f"Snippet {sid}")
                break

        data["snippets"] = [s for s in data["snippets"] if str(s["id"]) != str(sid)]
        save_snippets(data)
        speech = f"Deleted snippet: {deleted_name}." if deleted_name else "Snippet deleted."
        return jsonify({"success": True, "speech": speech})

    body = safejson()
    found = False
    snippet_name = None
    for s in data["snippets"]:
        if str(s["id"]) == str(sid):
            found = True
            snippet_name = s.get("name", "Snippet")
            if "name" in body:
                new_name = str(body["name"])
                if len(new_name) > 256:
                    return jsonify({"success": False, "error": "Name too long (max 256 chars)"}), 400
                s["name"] = new_name
                snippet_name = new_name
            if "code" in body:
                new_code = str(body["code"])
                if len(new_code) > MAX_CODE_SIZE:
                    return jsonify({"success": False, "error": f"Code too large (max {MAX_CODE_SIZE} bytes)"}), 413
                s["code"] = new_code
    if not found:
        return jsonify({"success": False, "error": "Snippet not found"}), 404
    save_snippets(data)
    speech = f"Updated snippet: {snippet_name}." if snippet_name else "Snippet updated."
    return jsonify({"success": True, "speech": speech})

# ==========================
# VOICE COMMANDS
# ==========================

COMMANDS = {
    "run": [
        "run", "execute", "run code", "execute code", "start code", "start program",
        "चलाओ", "कोड चलाओ", "रन करो", "रन",
    ],
    "analyze": [
        "analyze", "analyse", "analyze code", "analyse code", "explain code", "check code", "review code",
        "विश्लेषण करो", "कोड का विश्लेषण", "कोड समझाओ", "कोड जांचो",
    ],
    "speak": [
        "speak output", "read output", "read the output", "say the output",
        "आउटपुट पढ़ो", "आउटपुट बोलो", "output बताओ",
    ],
    "fix": [
        "fix", "fix code", "auto fix", "repair code", "correct code",
        "ठीक करो", "कोड ठीक करो", "गलती ठीक करो", "सही करो",
    ],
    "repeat_last_action": [
        "repeat", "do that again", "again", "repeat last",
        "दोहराओ", "फिर से करो", "वापस",
    ],
    "repeat_last_speech": [
        "repeat that", "say that again", "repeat message", "repeat output",
        "फिर से बोलो", "वही दोहराओ",
    ],
    "advise": [
        "advise on code", "advice on code", "improve code", "how to improve code",
        "सुझाव दो", "कोड सुधारो", "improve करो",
    ],
    "generate_code": [
        "generate code", "write code", "create code", "make code",
        "कोड बनाओ", "कोड लिखो", "code बनाओ",
    ],
    "clear_editor": [
        "clear editor", "clear code", "clear file", "reset code",
        "एडिटर साफ करो", "कोड हटाओ", "कोड मिटाओ",
    ],    "read_line_enhanced": ["read line with context", "enhanced read line", "describe line position", "where am i", "line context"],
    "sonify_block": ["sonify block", "sonify", "audio structure", "hear structure", "play code structure", "sound out code", "play this", "play code"],
    "read_line_enhanced": ["read line", "read current line", "read this line", "what is this line", "describe this line"],
    "list_variables": ["what variables", "list variables", "show variables", "what variables are available", "variables in scope"],
    "check_errors": ["check for errors", "check syntax", "find errors", "are there errors", "syntax check"],
    "locate_error": ["where is the error", "where is error", "find error", "jump to error", "go to error"],
    "stop_beacon": ["stop error beacon", "stop beacon", "turn off beacon", "disable beacon"],
    "go_back": ["go back", "navigate back", "back", "previous position"],
    "go_forward": ["go forward", "navigate forward", "forward", "next position"],
    "show_history": ["show history", "navigation history", "where have i been"],
    "help": ["help", "show help", "what can you do", "list commands"],
    "walk_through": ["walk through", "walk to", "walk through code", "walk me through", "walk through the code", "explain line by line", "narrate each line", "go through code", "explain the code line by line"],
    "file_stats": ["file stats", "how many lines", "file statistics", "code stats"],
    "go_to_top": ["go to top", "jump to top", "top of file"],
    "go_to_bottom": ["go to bottom", "jump to bottom", "bottom of file", "end of file"],
    "copy_code": ["copy code", "copy to clipboard", "copy this"],
    "paste_code": ["paste code", "paste from clipboard", "paste"],
    "start_tutorial":     ["start tutorial", "open tutorial", "begin tutorial", "tutorial"],
    "skip_tutorial":    ["skip tutorial", "close tutorial", "exit tutorial", "stop tutorial"],
    "toggle_dyslexia":  ["dyslexia mode", "toggle dyslexia", "turn on dyslexia", "turn off dyslexia"],
    "toggle_motion":    ["reduce motion", "reduced motion", "toggle motion", "motion mode"],
    "toggle_night":     ["night mode", "dark mode", "toggle night", "toggle dark mode"],
    "cycle_color_mode": ["color mode", "colour mode", "color blind mode", "colour blind mode", "cycle color mode", "next color mode"],
    "list_variables_voice": ["what are my variables", "show me variables", "list my variables", "what variables do i have", "what variables are declared"],
    "story_mode":       ["tell the story", "narrate execution", "execution story", "what happened", "story mode", "कहानी बताओ"],
    "mentor_mode":      ["learning mode", "mentor mode", "tutor mode", "teach me", "मुझे सिखाओ"],
    "quiz_me":          ["quiz me", "test me", "challenge me", "quiz करो", "test करो"],
    "bug_challenge":    ["bug challenge", "debug challenge", "give me a bug", "bug ढूंढो"],
    "clear_breakpoints":["clear breakpoints", "remove breakpoints", "delete breakpoints"],
    "stop_everything": ["stop", "stop it", "shut up", "be quiet", "silence", "stop talking", "cancel", "रुको", "बंद करो", "चुप", "रुक"],
}


def best_two_commands(text: str):
    """Return the top two DISTINCT command names by fuzzy score.

    Bug fix: previously this scored every phrase independently, so a command
    with multiple similar phrases could occupy both the best AND second slot
    (e.g. "walk to" → ["walk through", "walk through"]). Now we collapse to
    the best score per command name first, then pick the top two distinct
    commands.
    """
    text = text.lower().strip()

    # Best score per command name
    per_command_best = {}
    for name, phrases in COMMANDS.items():
        top = 0
        for p in phrases:
            s = fuzz.ratio(text, p)
            if s > top:
                top = s
        per_command_best[name] = top

    # Sort commands by best score, take top two distinct names
    ranked = sorted(per_command_best.items(), key=lambda kv: kv[1], reverse=True)

    best_name, best_score = (None, 0)
    second_name, second_score = (None, 0)
    if len(ranked) >= 1:
        best_name, best_score = ranked[0]
    if len(ranked) >= 2:
        second_name, second_score = ranked[1]

    return best_name, best_score, second_name, second_score

# ==========================
# FULL FILE NARRATION
# ==========================

@app.route("/narrate-file", methods=["POST"])
def narrate_file():
    """Narrate the entire file line-by-line in conversational, screen-reader-friendly form.

    Unlike /analyze (brief summary) or /analyze-deep (line-by-line technical),
    this produces a continuous spoken narrative meant to be played from start to finish.
    """
    body = safejson()
    code = safe(body.get("code"), "")
    language = safe(body.get("language"), "en")

    if len(code) > MAX_CODE_SIZE:
        return jsonify({"success": False, "error": f"Code too large (max {MAX_CODE_SIZE} bytes)"}), 413
    if not code.strip():
        return jsonify({"success": False, "error": "Code is empty"}), 400

    # Cap at 5KB OR 50 lines, whichever comes first, to keep LLM input in budget.
    NARRATE_CHAR_CAP = 5000
    NARRATE_LINE_CAP = 50
    code_lines_full = code.splitlines()
    if len(code) > NARRATE_CHAR_CAP or len(code_lines_full) > NARRATE_LINE_CAP:
        truncated_code = "\n".join(code_lines_full[:NARRATE_LINE_CAP])
        if len(truncated_code) > NARRATE_CHAR_CAP:
            truncated_code = truncated_code[:NARRATE_CHAR_CAP]
        code_to_narrate = truncated_code
        was_truncated = True
    else:
        code_to_narrate = code
        was_truncated = False

    if language == "hi":
        system = (
            "आप एक blind learner के लिए Python code का पूरा narration बनाते हैं।\n"
            "Code को शुरू से अंत तक पढ़ें और हर line को conversational tone में explain करें।\n"
            "Format: 'Line 1: print statement है जो hello print करता है।'\n"
            "Symbols को words में: == 'equals equals', != 'not equals'।\n"
            "हर line का अलग वाक्य। कोई markdown, bullet points, या headers नहीं।\n"
            "अधिकतम 50 lines। अगर file बड़ी है तो पहली 50 lines narrate करें।"
        )
    else:
        system = (
            "You are narrating Python code from start to finish for a blind learner.\n"
            "Walk through every line in order and explain it conversationally.\n"
            "Format: 'Line 1: a print statement that prints hello.'\n"
            "Spell out symbols as words: == as 'equals equals', != as 'not equals'.\n"
            "One sentence per line. No markdown, bullets, or headers.\n"
            "Maximum 50 lines. If the file is longer, narrate the first 50 and note the truncation at the end.\n"
            "Keep each sentence short — this will be played aloud."
        )

    user = f"Narrate this code:\n```python\n{code_to_narrate}\n```"
    narration = call_gemini(system, user, temperature=0.2, language=language)

    line_count = len(code_lines_full)

    return jsonify({
        "success": True,
        "narration": narration,
        "line_count": line_count,
        "truncated": was_truncated,
    })

# ==========================
# FILE SUMMARY
# ==========================

@app.route("/summarize", methods=["POST"])
def summarize():
    body = safejson()
    code = safe(body.get("code"), "")

    # FIX M-2: Added MAX_CODE_SIZE check (was missing from this endpoint).
    if len(code) > MAX_CODE_SIZE:
        return jsonify({"success": False, "error": f"Code too large (max {MAX_CODE_SIZE} bytes)"}), 413

    language = safe(body.get("language"), "en")

    if language == "hi":
        system = (
            "आप एक दृष्टिबाधित शुरुआती के लिए पायथन कोड को सारांशित करते हैं।\n"
            "4 से 7 छोटे बुलेट पॉइंट्स में समझाएं:\n"
            "- उद्देश्य\n"
            "- इनपुट\n"
            "- आउटपुट\n"
            "- मुख्य तर्क\n"
            "- कोई जोखिम\n"
            "कोई मार्कडाउन नहीं, कोई इमोजी नहीं।"
        )
    else:
        system = (
            "You summarize Python code for a blind beginner.\n"
            "Explain in 4 to 7 short bullet points:\n"
            "- Purpose\n"
            "- Inputs\n"
            "- Outputs\n"
            "- Main logic\n"
            "- Any risks\n"
            "No markdown, no emojis."
        )

    user = f"Code:\n```python\n{code}\n```"
    summary = call_gemini(system, user, language=language)
    return jsonify({"summary": summary})

# ==========================
# DIFF EXPLAIN
# ==========================

@app.route("/diff-explain", methods=["POST"])
def diff_explain():
    body = safejson()
    before = safe(body.get("before"), "")
    after = safe(body.get("after"), "")

    # FIX M-2: Added MAX_CODE_SIZE check (was missing from this endpoint).
    if len(before) > MAX_CODE_SIZE or len(after) > MAX_CODE_SIZE:
        return jsonify({"success": False, "error": f"Code too large (max {MAX_CODE_SIZE} bytes)"}), 413

    language = safe(body.get("language"), "en")

    if language == "hi":
        system = (
            "आप Python कोड के दो संस्करणों के बीच क्या बदला है यह समझाते हैं।\n"
            "एक दृष्टिबाधित छात्र के लिए सरल शब्दों में समझाएं।\n"
            "उल्लेख करें कि क्या ठीक किया गया और क्यों।\n"
            "अधिकतम 6 छोटी पंक्तियां।"
        )
    else:
        system = (
            "You explain what changed between two versions of Python code.\n"
            "Explain in simple terms for a blind student.\n"
            "Mention what was fixed and why.\n"
            "Max 6 short lines."
        )

    user = f"BEFORE:\n```python\n{before}\n```\n\nAFTER:\n```python\n{after}\n```"
    explanation = call_gemini(system, user, language=language)
    return jsonify({"explanation": explanation})

# ==========================
# SUGGEST NEXT LINE
# ==========================

@app.route("/suggest-next", methods=["POST"])
def suggest_next():
    body = safejson()
    code = safe(body.get("code"), "")
    line = body.get("line", 1)
    language = safe(body.get("language"), "en")

    if len(code) > MAX_CODE_SIZE:
        return jsonify({"success": False, "error": "Code too large"}), 413
    if not code.strip():
        return jsonify({"success": False, "suggestions": [], "error": "Code is empty"})

    lines = code.splitlines()
    current_line = lines[min(int(line) - 1, len(lines) - 1)] if lines else ""
    context_start = max(0, int(line) - 5)
    context = "\n".join(f"{i+1}: {l}" for i, l in enumerate(lines[context_start:int(line)]))

    if language == "hi":
        system = (
            "आप एक Python code completion assistant हैं।\n"
            "दिए गए code context को देखकर अगली 3 possible lines suggest करें।\n"
            "JSON format में respond करें:\n"
            "{\"suggestions\": [\"line1\", \"line2\", \"line3\"]}\n"
            "केवल valid Python lines। कोई explanation नहीं। केवल JSON।"
        )
    else:
        system = (
            "You are a Python code completion assistant.\n"
            "Given the code context, suggest the 3 most likely next lines.\n"
            "Respond ONLY with JSON in this exact format:\n"
            "{\"suggestions\": [\"line1\", \"line2\", \"line3\"]}\n"
            "Only valid Python lines. No explanation. JSON only."
        )

    user = f"Code context (cursor after line {line}):\n{context}\nCurrent line: {current_line}"

    try:
        raw = call_gemini(system, user, temperature=0.2, language=language)
        clean = re.sub(r'```(?:json)?\s*|\s*```', '', raw).strip()
        parsed = json.loads(clean)
        suggestions = parsed.get("suggestions", [])[:3]
        return jsonify({"success": True, "suggestions": suggestions})
    except Exception as e:
        return jsonify({"success": False, "suggestions": [], "error": str(e)})

def _trace_playback(direction):
    """Advance, rewind, or report the current trace step. All reads and the
    follow-up write happen under the same lock so a concurrent session
    cleanup cannot delete the dict between fetch and mutation."""
    session_id = get_session_id()
    with _session_traces_lock:
        storage = _session_traces.get(session_id)
        if storage is None:
            # Cleanup happened or session never ran code
            return "No execution trace available."
        storage['last_accessed'] = time.time()
        trace = list(storage.get('last_trace', []) or [])
        if not trace:
            return "No execution trace available."

        idx = storage.get('current_trace_index', -1)
        if direction == 'next':
            idx = min(len(trace) - 1, idx + 1)
        elif direction == 'prev':
            idx = max(0, idx - 1)
        elif direction == 'current_change':
            if idx < 0:
                return "No current trace step selected. Say 'next step' to begin."
        else:
            return "Unknown trace navigation command."

        storage['current_trace_index'] = idx
        event = trace[idx] if 0 <= idx < len(trace) else None

    return _event_to_speech(event, idx, len(trace))


# Telemetry: log unrecognized voice commands so we can grow the vocabulary
# from real usage instead of guessing. Stored per-session, capped, opt-out via env.
_voice_telemetry_lock = threading.Lock()
_voice_telemetry: List[Dict[str, Any]] = []
_VOICE_TELEMETRY_CAP = 1000  # rotate after this many entries

def _log_unrecognized_command(text: str, session_id: str):
    """Record a command that the parser couldn't match. Used to identify
    phrasings real users employ that the patterns don't yet cover.
    Default-OFF — set VOICE_TELEMETRY=1 to enable."""
    if os.environ.get("VOICE_TELEMETRY", "0") != "1":
        return
    if not text or len(text) > 500:
        return
    with _voice_telemetry_lock:
        _voice_telemetry.append({
            "text": text,
            "session": session_id[:8],  # truncated for privacy
            "timestamp": time.time(),
        })
        # Keep only the most recent N entries
        if len(_voice_telemetry) > _VOICE_TELEMETRY_CAP:
            del _voice_telemetry[:len(_voice_telemetry) - _VOICE_TELEMETRY_CAP]


@app.route("/voice-telemetry", methods=["GET"])
def get_voice_telemetry():
    """Return logged unrecognized commands for analysis. Auth-gated via
    VOICE_TELEMETRY_TOKEN env var. Default-OFF: telemetry must be explicitly
    enabled with VOICE_TELEMETRY=1 AND a token must be set and supplied."""
    if os.environ.get("VOICE_TELEMETRY", "0") != "1":
        return jsonify({"success": False, "error": "Telemetry disabled"}), 404
    expected_token = os.environ.get("VOICE_TELEMETRY_TOKEN", "")
    if not expected_token:
        return jsonify({"success": False, "error": "Telemetry not configured"}), 404
    supplied = request.headers.get("X-Telemetry-Token", "") or request.args.get("token", "")
    if supplied != expected_token:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    with _voice_telemetry_lock:
        return jsonify({
            "success": True,
            "count": len(_voice_telemetry),
            "entries": list(_voice_telemetry),
        })


@app.route("/voice-command", methods=["POST"])
def voice():
    text = safe(safejson().get("text"), "")
    parsed = parse_intent(text)
    intent = parsed.get("intent")
    slots = parsed.get("slots", {})
    confidence = parsed.get("confidence", 0.0)

    storage = get_trace_storage()

    # Handle repeat command
    if intent == "repeat":
        last_action = storage.get('last_voice_action', None)
        if not last_action:
            return jsonify({"success": True, "action": "unknown", "heard": "repeat", "message": "No previous command to repeat"})
        # FIX M-4: Store last_voice_action as a (dict, status_code) tuple so that
        # repeating preserves the original HTTP status code. Previously it was stored
        # as response.get_json() (a plain dict) and returned directly, causing Flask
        # to auto-serialize it as 200 OK regardless of the original status.
        return jsonify(last_action[0]), last_action[1]

    def _store_and_return(response_dict, status_code=200):
        """Helper: save action for repeat, then return the response."""
        with _session_traces_lock:
            storage['last_voice_action'] = (response_dict, status_code)
        return jsonify(response_dict), status_code

    if intent and confidence >= 0.75:
        if intent == "goto_line":
            return _store_and_return({"success": True, "action": "goto_line", "line": slots.get("line_number", 1), "confidence": confidence})
        if intent == "read_line":
            return _store_and_return({"success": True, "action": "read_line", "line": slots.get("line_number", 1), "confidence": confidence})
        if intent == "describe_line":
            return _store_and_return({"success": True, "action": "describe_line", "line": slots.get("line_number", 1), "confidence": confidence})
        if intent == "delete_line":
            return _store_and_return({"success": True, "action": "delete_line", "line": slots.get("line_number", 1), "confidence": confidence})
        if intent == "read_function":
            return _store_and_return({"success": True, "action": "read_function", "function_name": slots.get("function_name"), "confidence": confidence})
        if intent == "find_function":
            return _store_and_return({"success": True, "action": "find_function", "function_name": slots.get("function_name"), "confidence": confidence})
        if intent == "find_class":
            return _store_and_return({"success": True, "action": "find_class", "class_name": slots.get("class_name"), "confidence": confidence})
        if intent == "sonify_function":
            return _store_and_return({"success": True, "action": "sonify_function", "function_name": slots.get("function_name"), "confidence": confidence})
        if intent == "sonify_class":
            return _store_and_return({"success": True, "action": "sonify_class", "class_name": slots.get("class_name"), "confidence": confidence})
        if intent == "show_structure":
            return _store_and_return({"success": True, "action": "show_structure", "confidence": confidence})
        if intent == "run":
            return _store_and_return({"success": True, "action": "run", "confidence": confidence})
        if intent == "analyze_deep":
            return _store_and_return({"success": True, "action": "analyze_deep", "confidence": confidence})
        if intent == "analyze":
            return _store_and_return({"success": True, "action": "analyze", "confidence": confidence})
        if intent == "fix":
            return _store_and_return({"success": True, "action": "fix", "confidence": confidence})
        if intent == "advise":
            return _store_and_return({"success": True, "action": "advise", "confidence": confidence})
        if intent == "summarize":
            return _store_and_return({"success": True, "action": "summarize", "confidence": confidence})
        if intent == "narrate_file":
            return _store_and_return({"success": True, "action": "narrate_file", "confidence": confidence})
        if intent == "demo_list":
            return _store_and_return({"success": True, "action": "demo_list", "confidence": confidence})
        if intent == "demo_run":
            return _store_and_return({"success": True, "action": "demo_run", "preset": slots.get("preset", ""), "confidence": confidence})
        if intent == "pause_voice":
            return _store_and_return({"success": True, "action": "pause_voice", "confidence": confidence})
        if intent == "resume_voice":
            return _store_and_return({"success": True, "action": "resume_voice", "confidence": confidence})
        if intent == "generate_code":
            return _store_and_return({"success": True, "action": "generate_code", "prompt": slots.get("prompt", ""), "confidence": confidence})
        if intent == "rename_snippet":
            return _store_and_return({"success": True, "action": "rename_snippet", "id": slots.get("id"), "new_name": slots.get("new_name"), "confidence": confidence})
        if intent == "save_snippet_named":
            return _store_and_return({"success": True, "action": "save_snippet_named", "name": slots.get("name", "Untitled"), "confidence": confidence})
        if intent == "preview_snippet":
            return _store_and_return({"success": True, "action": "preview_snippet", "snippet_id": slots.get("snippet_id"), "confidence": confidence})
        if intent == "insert_function":
            return _store_and_return({"success": True, "action": "insert_function", "function_name": slots.get("function_name", "my_function"), "confidence": confidence})
        if intent == "insert_class":
            return _store_and_return({"success": True, "action": "insert_class", "class_name": slots.get("class_name", "MyClass"), "confidence": confidence})
        if intent == "insert_loop":
            return _store_and_return({"success": True, "action": "insert_loop", "loop_var": slots.get("loop_var", "i"), "iterable": slots.get("iterable", "range(10)"), "confidence": confidence})
        if intent == "insert_if":
            return _store_and_return({"success": True, "action": "insert_if", "condition": slots.get("condition", "True"), "confidence": confidence})
        if intent == "append_line":
            return _store_and_return({"success": True, "action": "append_line", "text": slots.get("text", ""), "confidence": confidence})
        if intent == "replace_line":
            return _store_and_return({"success": True, "action": "replace_line", "line_number": slots.get("line_number", 1), "text": slots.get("text", ""), "confidence": confidence})
        if intent == "insert_line":
            return _store_and_return({"success": True, "action": "insert_line", "line_number": slots.get("line_number", 1), "text": slots.get("text", ""), "confidence": confidence})
        if intent == "add_parameter":
            return _store_and_return({"success": True, "action": "add_parameter", "param_name": slots.get("param_name", "param"), "function_name": slots.get("function_name"), "confidence": confidence})
        if intent == "suggest_next":
            return _store_and_return({"success": True, "action": "suggest_next", "confidence": confidence})
        if intent == "choose_suggestion":
            return _store_and_return({"success": True, "action": "choose_suggestion", "choice": slots.get("choice", 1), "confidence": confidence})
        if intent == "story_mode":
            return _store_and_return({"success": True, "action": "story_mode", "confidence": confidence})
        if intent == "more_help":
            return _store_and_return({"success": True, "action": "more_help", "confidence": confidence})
        if intent == "set_breakpoint":
            return _store_and_return({"success": True, "action": "set_breakpoint", "line_number": slots.get("line_number", 1), "confidence": confidence})
        if intent == "clear_breakpoints":
            return _store_and_return({"success": True, "action": "clear_breakpoints", "confidence": confidence})
        if intent == "watch_variable":
            return _store_and_return({"success": True, "action": "watch_variable", "variable": slots.get("variable", ""), "confidence": confidence})
        if intent == "debug_continue":
            return _store_and_return({"success": True, "action": "debug_continue", "confidence": confidence})
        if intent == "debug_step_in":
            return _store_and_return({"success": True, "action": "debug_step_in", "confidence": confidence})
        if intent == "debug_step_out":
            return _store_and_return({"success": True, "action": "debug_step_out", "confidence": confidence})
        if intent == "mentor_mode":
            return _store_and_return({"success": True, "action": "mentor_mode", "confidence": confidence})
        if intent == "quiz_me":
            return _store_and_return({"success": True, "action": "quiz_me", "topic": slots.get("topic", "Python basics"), "confidence": confidence})
        if intent == "explain_concept":
            return _store_and_return({"success": True, "action": "explain_concept", "concept": slots.get("concept", "variables"), "confidence": confidence})
        if intent == "bug_challenge":
            return _store_and_return({"success": True, "action": "bug_challenge", "confidence": confidence})
        if intent == "clear_editor":
            return _store_and_return({"success": True, "action": "clear_editor", "confidence": confidence})
        if intent == "read_output":
            return _store_and_return({"success": True, "action": "read_output", "confidence": confidence})
        if intent == "next_step":
            return _store_and_return({"success": True, "action": "next_step", "speech": _trace_playback("next"), "confidence": confidence})
        if intent == "previous_step":
            return _store_and_return({"success": True, "action": "previous_step", "speech": _trace_playback("prev"), "confidence": confidence})
        if intent == "what_changed":
            return _store_and_return({"success": True, "action": "what_changed", "speech": _trace_playback("current_change"), "confidence": confidence})
        if intent == "set_inputs":
            return _store_and_return({"success": True, "action": "set_inputs", "values": slots.get("values", []), "confidence": confidence})
        if intent == "clear_inputs":
            return _store_and_return({"success": True, "action": "clear_inputs", "confidence": confidence})
        if intent == "list_inputs":
            return _store_and_return({"success": True, "action": "list_inputs", "confidence": confidence})
        if intent == "live_input_mode":
            return _store_and_return({"success": True, "action": "live_input_mode", "confidence": confidence})
        if intent == "preflight_input_mode":
            return _store_and_return({"success": True, "action": "preflight_input_mode", "confidence": confidence})
        if intent == "save_macro":
            return _store_and_return({"success": True, "action": "save_macro", "name": slots.get("name", ""), "confidence": confidence})
        if intent == "use_macro":
            return _store_and_return({"success": True, "action": "use_macro", "name": slots.get("name", ""), "confidence": confidence})
        if intent == "list_macros":
            return _store_and_return({"success": True, "action": "list_macros", "confidence": confidence})
        if intent == "bookmark_output":
            return _store_and_return({"success": True, "action": "bookmark_output", "label": slots.get("label", ""), "confidence": confidence})
        if intent == "read_bookmark":
            return _store_and_return({"success": True, "action": "read_bookmark", "label": slots.get("label", ""), "confidence": confidence})
        if intent == "list_bookmarks":
            return _store_and_return({"success": True, "action": "list_bookmarks", "confidence": confidence})
        if intent == "where_am_i":
            return _store_and_return({"success": True, "action": "where_am_i", "confidence": confidence})
        if intent == "explain_simply":
            return _store_and_return({"success": True, "action": "explain_simply", "confidence": confidence})
        if intent == "narrate_diff":
            return _store_and_return({"success": True, "action": "narrate_diff", "confidence": confidence})
        if intent == "set_color_mode":
            return _store_and_return({"success": True, "action": "set_color_mode", "mode": slots.get("mode", "default"), "confidence": confidence})

    # Fallback: fuzzy matching on COMMANDS
    lower_text = text.lower().strip()
    best, bscore, second, sscore = best_two_commands(lower_text)

    # High-frequency commands skip the confirm prompt even at moderate confidence,
    # because in a noisy classroom getting "did you mean run or fix?" on every
    # command is more frustrating than occasionally running the wrong simple action.
    HIGH_FREQUENCY_COMMANDS = {"run", "analyze", "fix", "help", "speak", "read_output", "walk_through", "sonify_block", "stop_everything", "pause_voice", "resume_voice"}

    if best and bscore >= VOICE_FUZZY_THRESHOLD:
        is_clear_winner = bscore >= 75 and (not second or (bscore - sscore) >= 15)
        is_high_freq = best in HIGH_FREQUENCY_COMMANDS and bscore >= 65

        if is_clear_winner or is_high_freq:
            return jsonify({"success": True, "action": best, "confidence": bscore / 100.0})

        options = [best, second] if second else [best]
        return jsonify({
            "success": True,
            "action": "confirm",
            "options": options,
            "heard": text,
            "confidence": bscore / 100.0
        })

    # Log unrecognized commands so we can iterate the vocabulary from real data
    _log_unrecognized_command(text, get_session_id())
    return jsonify({"success": True, "action": "unknown", "heard": text, "confidence": 0.0})

# ==========================
# CODE STRUCTURE BREADCRUMBS
# ==========================

@app.route("/breadcrumbs", methods=["POST"])
def breadcrumbs():
    """Return the nested-structure breadcrumb at a given line.

    Walks the AST from the file root down, tracking which functions/classes/
    loops/conditionals contain the target line. Returns a human-readable
    string like 'function calculate, inside for loop, line 15'.
    """
    body = safejson()
    code = safe(body.get("code"), "")
    if len(code) > MAX_CODE_SIZE:
        return jsonify({"success": False, "error": "Code too large"}), 413
    try:
        line = int(body.get("line", 1))
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "Invalid line"}), 400

    if not code.strip():
        return jsonify({"success": True, "breadcrumb": "empty file", "trail": []})

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return jsonify({"success": False, "message": f"Cannot parse: {e}"})

    trail = []  # list of (kind, name, start_line, end_line)

    def end_line(node):
        return getattr(node, 'end_lineno', None) or max(
            (getattr(n, 'lineno', 0) for n in ast.walk(node)), default=node.lineno
        )

    def walk(node, depth=0):
        for child in ast.iter_child_nodes(node):
            start = getattr(child, 'lineno', None)
            stop = end_line(child)
            if start is None or stop is None:
                continue
            if not (start <= line <= stop):
                continue
            kind = None
            name = None
            if isinstance(child, ast.FunctionDef):
                kind, name = "function", child.name
            elif isinstance(child, ast.AsyncFunctionDef):
                kind, name = "async function", child.name
            elif isinstance(child, ast.ClassDef):
                kind, name = "class", child.name
            elif isinstance(child, ast.For):
                kind, name = "for loop", None
            elif isinstance(child, ast.While):
                kind, name = "while loop", None
            elif isinstance(child, ast.If):
                kind, name = "if block", None
            elif isinstance(child, ast.With):
                kind, name = "with block", None
            elif isinstance(child, ast.Try):
                kind, name = "try block", None
            if kind:
                trail.append({"kind": kind, "name": name, "line": start})
            walk(child, depth + 1)

    walk(tree)

    if not trail:
        breadcrumb = f"line {line}, top level of file"
    else:
        parts = []
        for item in trail:
            if item["name"]:
                parts.append(f"{item['kind']} {item['name']}")
            else:
                parts.append(item["kind"])
        breadcrumb = ", inside ".join(parts) + f", line {line}"

    return jsonify({"success": True, "breadcrumb": breadcrumb, "trail": trail})


# ==========================
# OUTPUT BOOKMARKS
# ==========================

@app.route("/bookmarks", methods=["GET", "POST", "DELETE"])
def bookmarks():
    """Per-session output bookmarks.

    POST {label, position} → save bookmark at that output offset
    GET → list all bookmarks for this session
    DELETE → clear all bookmarks for this session
    """
    session_id = get_session_id()
    if request.method == "GET":
        with _output_bookmarks_lock:
            marks = list(_output_bookmarks.get(session_id, []))
        return jsonify({"success": True, "bookmarks": marks})

    if request.method == "DELETE":
        with _output_bookmarks_lock:
            _output_bookmarks.pop(session_id, None)
        return jsonify({"success": True, "speech": "All bookmarks cleared."})

    body = safejson()
    label = str(safe(body.get("label"), "")).strip()[:80]
    try:
        position = int(body.get("position", 0))
    except (ValueError, TypeError):
        position = 0
    if not label:
        # Auto-name based on count
        with _output_bookmarks_lock:
            count = len(_output_bookmarks.get(session_id, []))
        label = f"bookmark {count + 1}"

    with _output_bookmarks_lock:
        marks = _output_bookmarks.setdefault(session_id, [])
        # Cap at 20 per session
        if len(marks) >= 20:
            marks.pop(0)
        marks.append({
            "label": label,
            "position": position,
            "timestamp": time.time(),
        })
    return jsonify({"success": True, "label": label, "speech": f"Bookmarked as {label}."})


@app.route("/bookmarks/read", methods=["POST"])
def read_from_bookmark():
    """Return the slice of output starting from a named bookmark."""
    body = safejson()
    label = str(safe(body.get("label"), "")).strip().lower()
    full_output = str(safe(body.get("output"), ""))
    session_id = get_session_id()

    with _output_bookmarks_lock:
        marks = list(_output_bookmarks.get(session_id, []))
    match = next((m for m in marks if m["label"].lower() == label), None)
    if not match and marks:
        # Fuzzy: take the most recent if no exact match
        match = marks[-1]
    if not match:
        return jsonify({"success": False, "error": "No bookmark found"})

    pos = match["position"]
    if pos < 0 or pos > len(full_output):
        return jsonify({"success": False, "error": "Bookmark position out of range"})
    return jsonify({
        "success": True,
        "label": match["label"],
        "slice": full_output[pos:],
    })


# ==========================
# VOICE MACROS
# ==========================

def _macros_path(session_id=None):
    if session_id is None:
        session_id = get_session_id()
    safe_id = re.sub(r'[^a-fA-F0-9\-]', '', session_id)[:64] or "default"
    return os.path.join(DATA_DIR, f"macros_{safe_id}.json")


def _load_macros():
    path = _macros_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _save_macros(macros):
    path = _macros_path()
    dirpath = os.path.dirname(path) or "."
    with _voice_macros_lock:
        tmp = None
        try:
            os.makedirs(dirpath, exist_ok=True)
            fd, tmp = tempfile.mkstemp(suffix=".json", prefix="macros_", dir=dirpath)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(macros, f, indent=2)
            except Exception:
                try: os.close(fd)
                except OSError: pass
                raise
            os.replace(tmp, path)
        except Exception:
            try:
                if tmp and os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass
            raise


@app.route("/macros", methods=["GET"])
def list_macros():
    macros = _load_macros()
    names = sorted(macros.keys())
    if not names:
        speech = "You have no voice macros saved."
    elif len(names) == 1:
        speech = f"You have 1 macro: {names[0]}."
    else:
        speech = f"You have {len(names)} macros: {', '.join(names)}."
    return jsonify({"success": True, "macros": macros, "names": names, "speech": speech})


@app.route("/macros", methods=["POST"])
def save_macro():
    body = safejson()
    name = str(safe(body.get("name"), "")).strip().lower()[:64]
    code = str(safe(body.get("code"), ""))
    if not name:
        return jsonify({"success": False, "error": "Macro name required"}), 400
    if len(code) > MAX_CODE_SIZE:
        return jsonify({"success": False, "error": "Code too large"}), 413
    if not re.match(r'^[a-z0-9 _\u0900-\u097f-]+$', name):
        return jsonify({"success": False, "error": "Macro name must be letters, numbers, spaces, dash or underscore"}), 400
    macros = _load_macros()
    if len(macros) >= 50 and name not in macros:
        return jsonify({"success": False, "error": "Macro limit reached (50)"}), 400
    macros[name] = {"code": code, "saved_at": time.time()}
    _save_macros(macros)
    return jsonify({"success": True, "speech": f"Macro {name} saved."})


@app.route("/macros/<name>", methods=["DELETE"])
def delete_macro(name):
    name = name.strip().lower()
    macros = _load_macros()
    if name not in macros:
        return jsonify({"success": False, "error": "Macro not found"}), 404
    del macros[name]
    _save_macros(macros)
    return jsonify({"success": True, "speech": f"Macro {name} deleted."})


@app.route("/macros/get/<name>", methods=["GET"])
def get_macro(name):
    name = name.strip().lower()
    macros = _load_macros()
    if name not in macros:
        return jsonify({"success": False, "error": "Macro not found"}), 404
    return jsonify({"success": True, "code": macros[name].get("code", ""), "name": name})


# ==========================
# INTERACTIVE RUN (Mechanism B) — SSE streaming with input pipe
# ==========================

def _cleanup_run(run_id):
    """Tear down a run's resources. Idempotent."""
    with _active_runs_lock:
        state = _active_runs.pop(run_id, None)
    if not state:
        return
    proc = state.get("proc")
    if proc:
        try:
            if proc.poll() is None:
                if sys.platform != "win32":
                    import signal as _signal
                    try:
                        os.killpg(os.getpgid(proc.pid), _signal.SIGKILL)
                    except (ProcessLookupError, OSError):
                        pass
                else:
                    proc.kill()
        except Exception:
            pass
    fifo = state.get("fifo")
    if fifo and os.path.exists(fifo):
        try:
            os.unlink(fifo)
        except OSError:
            pass
    for tmp in (state.get("code_file"), state.get("trace_file"), state.get("script_file")):
        if tmp and os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


@app.route("/run-stream/start", methods=["POST"])
def run_stream_start():
    """Start an interactive run. Returns a run_id. Client opens an SSE
    connection at /run-stream/<run_id> to receive output events and posts
    answers to /run-stream/<run_id>/input when prompted.

    POSIX-only feature. On Windows, returns 501 with a friendly message
    suggesting Mechanism A.
    """
    if sys.platform == "win32":
        return jsonify({
            "success": False,
            "error": "Live input mode requires POSIX (Linux or macOS). On Windows, use the inputs panel instead.",
        }), 501

    body = safejson()
    code = safe(body.get("code"), "")
    if len(code) > MAX_CODE_SIZE:
        return jsonify({"success": False, "error": "Code too large"}), 413
    if not code.strip():
        return jsonify({"success": False, "error": "Code cannot be empty"}), 400
    if not _check_run_rate_limit(get_session_id()):
        return jsonify({"success": False, "error": "Rate limit exceeded"}), 429

    run_id = uuid.uuid4().hex
    sandbox = get_sandbox(get_session_id())
    workspace_dir = sandbox.workspace_dir

    # Create FIFO. Only one consumer (subprocess) and one producer (us).
    fifo_path = os.path.join(workspace_dir, f"input_{run_id}.fifo")
    try:
        os.mkfifo(fifo_path)
    except OSError as e:
        return jsonify({"success": False, "error": f"Could not create input pipe: {e}"}), 500

    # Write code to temp file in workspace
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False,
                                      encoding='utf-8', dir=workspace_dir) as cf:
        cf.write(code)
        code_file_path = cf.name

    trace_file = os.path.join(workspace_dir, f"trace_{run_id}.json")
    runner_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sandbox_runner.py')

    env = os.environ.copy()
    env['CODEUP_CODE_FILE'] = code_file_path
    env['CODEUP_TRACE_FILE'] = trace_file
    env['CODEUP_INTERACTIVE'] = '1'
    env['CODEUP_INPUT_FIFO'] = fifo_path
    env.pop('CODEUP_INPUTS_FILE', None)

    output_queue = _queue_mod.Queue()

    popen_kwargs = dict(
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=workspace_dir,
        text=True,
        bufsize=1,  # line-buffered so we can stream
    )
    if sys.platform != "win32":
        popen_kwargs["preexec_fn"] = _set_subprocess_limits
        popen_kwargs["start_new_session"] = True

    try:
        proc = subprocess.Popen([sys.executable, runner_path], **popen_kwargs)
    except Exception as e:
        try: os.unlink(fifo_path)
        except OSError: pass
        try: os.unlink(code_file_path)
        except OSError: pass
        return jsonify({"success": False, "error": f"Could not start run: {e}"}), 500

    state = {
        "proc": proc,
        "fifo": fifo_path,
        "code_file": code_file_path,
        "trace_file": trace_file,
        "queue": output_queue,
        "started_at": time.time(),
        "session_id": get_session_id(),
        "awaiting_input": False,
        "awaiting_input_lock": threading.Lock(),
    }
    with _active_runs_lock:
        _active_runs[run_id] = state

    # Reader threads — push every line into the output queue. Watch for input
    # sentinel and emit a structured event when seen.
    SENTINEL = "CODEUP::INPUT_REQUEST::"

    def _stdout_reader():
        try:
            for line in iter(proc.stdout.readline, ''):
                if not line:
                    break
                if line.startswith(SENTINEL):
                    prompt = line[len(SENTINEL):].rstrip('\n')
                    with state["awaiting_input_lock"]:
                        state["awaiting_input"] = True
                    output_queue.put({"type": "input_request", "prompt": prompt})
                else:
                    output_queue.put({"type": "stdout", "text": line})
        except Exception as e:
            output_queue.put({"type": "error", "text": f"stdout reader error: {e}"})
        finally:
            try: proc.stdout.close()
            except Exception: pass

    def _stderr_reader():
        try:
            for line in iter(proc.stderr.readline, ''):
                if not line:
                    break
                output_queue.put({"type": "stderr", "text": line})
        except Exception as e:
            output_queue.put({"type": "error", "text": f"stderr reader error: {e}"})
        finally:
            try: proc.stderr.close()
            except Exception: pass

    def _waiter():
        # Hard 60-second cap on interactive runs (longer than batch /run because
        # users need time to think and answer prompts)
        deadline = time.time() + 60
        while proc.poll() is None and time.time() < deadline:
            time.sleep(0.2)
        if proc.poll() is None:
            try:
                if sys.platform != "win32":
                    import signal as _signal
                    os.killpg(os.getpgid(proc.pid), _signal.SIGKILL)
                else:
                    proc.kill()
            except Exception:
                pass
            output_queue.put({"type": "stderr", "text": "\nExecution timed out after 60 seconds.\n"})
        output_queue.put({"type": "done", "exit_code": proc.returncode})

    threading.Thread(target=_stdout_reader, daemon=True).start()
    threading.Thread(target=_stderr_reader, daemon=True).start()
    threading.Thread(target=_waiter, daemon=True).start()

    return jsonify({"success": True, "run_id": run_id})


@app.route("/run-stream/<run_id>/stream", methods=["GET"])
def run_stream(run_id):
    """SSE endpoint. Yields events from the output queue until 'done'."""
    with _active_runs_lock:
        state = _active_runs.get(run_id)
    if not state:
        return jsonify({"success": False, "error": "Run not found or expired"}), 404
    # Authorize: only the originating session can read its run
    if state.get("session_id") != get_session_id():
        return jsonify({"success": False, "error": "Forbidden"}), 403

    output_queue = state["queue"]

    def generate():
        try:
            while True:
                try:
                    event = output_queue.get(timeout=30)
                except _queue_mod.Empty:
                    # Heartbeat to keep connection alive through proxies
                    yield ": heartbeat\n\n"
                    # Check if run is dead but no 'done' was emitted
                    proc = state.get("proc")
                    if proc and proc.poll() is not None:
                        yield f"data: {json.dumps({'type': 'done', 'exit_code': proc.returncode})}\n\n"
                        break
                    continue
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") == "done":
                    break
        finally:
            _cleanup_run(run_id)

    return app.response_class(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
            "Connection": "keep-alive",
        },
    )


@app.route("/run-stream/<run_id>/input", methods=["POST"])
def run_stream_input(run_id):
    """Receive a line of input from the client and write it to the FIFO."""
    with _active_runs_lock:
        state = _active_runs.get(run_id)
    if not state:
        return jsonify({"success": False, "error": "Run not found"}), 404
    if state.get("session_id") != get_session_id():
        return jsonify({"success": False, "error": "Forbidden"}), 403
    body = safejson()
    value = str(safe(body.get("value"), ""))[:1000]
    fifo = state.get("fifo")
    if not fifo or not os.path.exists(fifo):
        return jsonify({"success": False, "error": "Input pipe not available"}), 410
    try:
        # Open + write + close. The subprocess opens the FIFO inside a `with`
        # block per call, which means we can open ours each time too.
        with open(fifo, 'w', encoding='utf-8') as f:
            f.write(value + '\n')
        with state["awaiting_input_lock"]:
            state["awaiting_input"] = False
        return jsonify({"success": True})
    except OSError as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/run-stream/<run_id>/cancel", methods=["POST"])
def run_stream_cancel(run_id):
    with _active_runs_lock:
        state = _active_runs.get(run_id)
    if state and state.get("session_id") != get_session_id():
        return jsonify({"success": False, "error": "Forbidden"}), 403
    _cleanup_run(run_id)
    return jsonify({"success": True})


# ==========================
# CURRENT EXECUTION POSITION (mid-run polling for live mode)
# ==========================

@app.route("/run-stream/<run_id>/position", methods=["GET"])
def run_stream_position(run_id):
    """Return whether the run is awaiting input. Used by the heartbeat UI."""
    with _active_runs_lock:
        state = _active_runs.get(run_id)
    if not state:
        return jsonify({"success": False, "alive": False})
    if state.get("session_id") != get_session_id():
        return jsonify({"success": False, "error": "Forbidden"}), 403
    proc = state.get("proc")
    alive = proc is not None and proc.poll() is None
    with state["awaiting_input_lock"]:
        awaiting = state.get("awaiting_input", False)
    return jsonify({
        "success": True,
        "alive": alive,
        "awaiting_input": awaiting,
        "elapsed_ms": int((time.time() - state.get("started_at", time.time())) * 1000),
    })


# ==========================
# SANDBOXED FILE SYSTEM
# ==========================

@app.route("/fs/write", methods=["POST"])
def fs_write():
    body = safejson()
    filepath = safe(body.get("path"), "")
    content = safe(body.get("content"), "")
    if not filepath:
        return jsonify({"success": False, "error": "Path is required"}), 400
    sandbox = get_sandbox(get_session_id())
    result = sandbox.write(filepath, content)
    return jsonify(result)

@app.route("/fs/read", methods=["POST"])
def fs_read():
    body = safejson()
    filepath = safe(body.get("path"), "")
    if not filepath:
        return jsonify({"success": False, "error": "Path is required"}), 400
    sandbox = get_sandbox(get_session_id())
    result = sandbox.read(filepath)
    return jsonify(result)

@app.route("/fs/delete", methods=["POST"])
def fs_delete():
    body = safejson()
    filepath = safe(body.get("path"), "")
    if not filepath:
        return jsonify({"success": False, "error": "Path is required"}), 400
    sandbox = get_sandbox(get_session_id())
    result = sandbox.delete(filepath)
    return jsonify(result)

@app.route("/fs/list", methods=["POST"])
def fs_list():
    body = safejson()
    dirpath = safe(body.get("path"), ".")
    sandbox = get_sandbox(get_session_id())
    result = sandbox.list_files(dirpath)
    return jsonify(result)

@app.route("/fs/info", methods=["GET"])
def fs_info():
    sandbox = get_sandbox(get_session_id())
    result = sandbox.get_workspace_info()
    return jsonify(result)

# ==========================
# EXECUTION TRACE (for playback)
# ==========================

@app.route("/execution-trace", methods=["GET"])
def get_execution_trace():
    """Get the last execution trace for playback.

    Reads under the session lock and returns a snapshot copy so a concurrent
    /run that's mid-write can't return a partially-mutated trace.
    """
    session_id = get_session_id()
    with _session_traces_lock:
        if session_id not in _session_traces:
            _session_traces[session_id] = _make_session_storage()
        storage = _session_traces[session_id]
        storage['last_accessed'] = time.time()
        # Snapshot under the lock — list copy is shallow but trace events are
        # immutable dicts so this is safe.
        trace = list(storage.get('last_trace', []) or [])
        idx = storage.get('current_trace_index', -1)
        duration = storage.get('trace_duration_ms', 0)

    return jsonify({
        "trace": trace,
        "current_index": idx,
        "total_lines_executed": sum(1 for e in trace if e.get('type') == 'line_exec'),
        "duration_ms": duration,
        "message": "Trace playback data"
    })


def _get_trace_event(index):
    """Retrieve a single trace event by index from session storage.

    FIX C-3 (continued): Previously read from _trace_context (never written),
    so always returned None, making all voice trace-playback responses say
    'No trace event at this position.' Now correctly reads from get_trace_storage().
    """
    storage = get_trace_storage()
    trace = storage.get('last_trace', []) or []
    if index < 0 or index >= len(trace):
        return None
    return trace[index]


def _event_to_speech(event, idx=None, total=None):
    if not event:
        return "No trace event at this position."

    step_prefix = f"Step {idx + 1} of {total}: " if idx is not None and total is not None else ""

    t = event.get('type')
    if t == 'line_exec':
        return f"{step_prefix}Executed line {event.get('line')}"
    if t == 'state_change':
        changes = '; '.join(event.get('changes', []))
        return f"{step_prefix}State changed on line {event.get('line')}: {changes}"
    if t == 'call':
        return f"{step_prefix}Called function {event.get('function')} at line {event.get('line')}"
    if t == 'return':
        return f"{step_prefix}Returned value {event.get('value')}"
    return f"{step_prefix}{t}: {event}"


# ==========================
# EXECUTION STORY MODE
# ==========================

@app.route("/execution-story", methods=["POST"])
def execution_story():
    body = safejson()
    code = safe(body.get("code"), "")
    language = safe(body.get("language"), "en")

    storage = get_trace_storage()
    trace = storage.get('last_trace', []) or []

    if not trace:
        msg = "No execution trace available. Please run your code first."
        if language == "hi":
            msg = "कोई execution trace उपलब्ध नहीं है। पहले अपना code चलाएं।"
        return jsonify({"success": False, "story": msg})

    # Build a compact trace summary for the LLM
    events_summary = []
    for e in trace[:50]:  # cap at 50 events to stay within token limit
        t = e.get('type')
        if t == 'line_exec':
            events_summary.append(f"line {e.get('line')} executed")
        elif t == 'state_change':
            changes = ', '.join(e.get('changes', []))
            events_summary.append(f"line {e.get('line')}: {changes}")
        elif t == 'call':
            events_summary.append(f"function '{e.get('function')}' called at line {e.get('line')}")
        elif t == 'return':
            events_summary.append(f"returned {e.get('value')}")

    trace_text = "\n".join(events_summary)

    if language == "hi":
        system = (
            "आप एक Python execution narrator हैं जो blind learners के लिए काम करते हैं।\n"
            "नीचे दिए गए code और execution trace को देखकर एक simple, conversational story बनाएं।\n"
            "Dry technical output की जगह narrative language use करें। जैसे:\n"
            "'Program शुरू हुआ। पहले x को 5 की value मिली। फिर loop शुरू हुआ...'\n"
            "अधिकतम 8 छोटे वाक्य। Simple Hindi में।"
        )
    else:
        system = (
            "You are a Python execution narrator for blind learners.\n"
            "Given the code and execution trace, narrate what happened as a clear story.\n"
            "Use conversational language instead of dry technical output. For example:\n"
            "'The program began. First, x was given the value 5. Then the loop started...'\n"
            "Maximum 8 short sentences. Simple English."
        )

    user = f"Code:\n```python\n{code}\n```\n\nExecution trace:\n{trace_text}"
    story = call_gemini(system, user, temperature=0.3, language=language)
    return jsonify({"success": True, "story": story})


# ==========================
# MENTOR / LEARNING MODE
# ==========================

def _validate_quiz_response(parsed: dict) -> Optional[str]:
    """Validate a quiz dict from the LLM. Returns None if valid, error string if not.
    Defends against the LLM returning malformed or partial JSON that would crash
    the frontend or confuse the learner. Restricts to exactly 3 options (A/B/C)
    so the frontend regex can match cleanly."""
    if not isinstance(parsed, dict):
        return "Quiz response was not a dictionary"
    if not parsed.get("question") or not isinstance(parsed["question"], str):
        return "Quiz missing valid question"
    options = parsed.get("options", [])
    if not isinstance(options, list) or len(options) != 3:
        return "Quiz must have exactly 3 options"
    answer = parsed.get("answer", "")
    if not isinstance(answer, str) or answer.upper() not in ("A", "B", "C"):
        return "Quiz answer must be A, B, or C"
    if not parsed.get("explanation"):
        return "Quiz missing explanation"
    return None


@app.route("/mentor/quiz", methods=["POST"])
def mentor_quiz():
    body = safejson()
    topic = safe(body.get("topic"), "Python basics")
    language = safe(body.get("language"), "en")

    if language == "hi":
        system = (
            "आप एक blind Python learner के लिए quiz questions बनाते हैं।\n"
            "दिए गए topic पर एक quiz question बनाएं जिसमें:\n"
            "- एक clear question\n"
            "- 3 options (A, B, C)\n"
            "- सही answer\n"
            "- एक line explanation\n"
            "JSON format में respond करें:\n"
            "{\"question\": \"...\", \"options\": [\"A: ...\", \"B: ...\", \"C: ...\"], \"answer\": \"A\", \"explanation\": \"...\"}\n"
            "केवल JSON। कोई extra text नहीं।"
        )
    else:
        system = (
            "You create quiz questions for a blind Python learner.\n"
            "Create one quiz question on the given topic with:\n"
            "- A clear question\n"
            "- 3 options (A, B, C)\n"
            "- The correct answer letter\n"
            "- A one-line explanation\n"
            "Respond ONLY with JSON:\n"
            "{\"question\": \"...\", \"options\": [\"A: ...\", \"B: ...\", \"C: ...\"], \"answer\": \"A\", \"explanation\": \"...\"}\n"
            "JSON only. No extra text."
        )

    user = f"Topic: {topic}"
    raw = call_gemini(system, user, temperature=0.4, language=language)

    # Detect AI-disabled / error responses before attempting JSON parse
    if raw.startswith("AI service") or "not configured" in raw.lower() or "unavailable" in raw.lower():
        return jsonify({
            "success": False,
            "error": "Quiz unavailable: AI not configured. Try the bug challenge or tutorial instead.",
        })

    try:
        clean = re.sub(r'```(?:json)?\s*|\s*```', '', raw).strip()
        parsed = json.loads(clean)
    except Exception:
        return jsonify({
            "success": False,
            "error": "AI returned a malformed quiz. Try saying 'quiz me' again, or try a different topic.",
        })

    validation_error = _validate_quiz_response(parsed)
    if validation_error:
        return jsonify({
            "success": False,
            "error": f"AI returned an incomplete quiz ({validation_error}). Try again.",
        })

    # Normalize answer to uppercase for the frontend matcher
    parsed["answer"] = parsed["answer"].upper()
    return jsonify({"success": True, "quiz": parsed})


@app.route("/mentor/explain", methods=["POST"])
def mentor_explain():
    body = safejson()
    concept = safe(body.get("concept"), "variables")
    language = safe(body.get("language"), "en")

    if language == "hi":
        system = (
            "आप एक blind beginner के लिए Python concepts explain करते हैं।\n"
            "Concept को बिल्कुल simple तरीके से समझाएं जैसे पहली बार सुन रहे हों।\n"
            "एक real-life analogy दें। फिर एक short code example।\n"
            "अधिकतम 6 छोटी lines।"
        )
    else:
        system = (
            "You explain Python concepts to a blind beginner.\n"
            "Explain the concept as simply as possible, as if hearing it for the first time.\n"
            "Give a real-life analogy. Then a short code example.\n"
            "Maximum 6 short lines."
        )

    user = f"Concept: {concept}"
    explanation = call_gemini(system, user, temperature=0.2, language=language)

    # Reject empty or near-empty responses so the frontend doesn't speak silence.
    if not explanation or not explanation.strip() or len(explanation.strip()) < 20:
        return jsonify({
            "success": False,
            "error": "AI returned an incomplete explanation. Try asking again, or try a different concept name."
        })
    if explanation.startswith("AI service") or "not configured" in explanation.lower():
        return jsonify({
            "success": False,
            "error": explanation,
        })
    return jsonify({"success": True, "explanation": explanation})


def _validate_bug_challenge(parsed: dict) -> Optional[str]:
    """Validate a bug challenge dict. Critical: the buggy code must be valid
    enough to load into the editor (even if it doesn't run), and the fixed
    code must actually compile, otherwise the student gets a 'fix' that's
    worse than the original."""
    if not isinstance(parsed, dict):
        return "Challenge was not a dictionary"
    for key in ("code", "hint", "bug", "fixed"):
        if not parsed.get(key) or not isinstance(parsed[key], str):
            return f"Challenge missing or invalid field: {key}"
    # The fixed code must at least parse — otherwise the LLM gave us garbage
    try:
        compile(parsed["fixed"], "<challenge>", "exec")
    except SyntaxError:
        return "AI's 'fixed' code has syntax errors"
    return None


@app.route("/mentor/bug-challenge", methods=["POST"])
def mentor_bug_challenge():
    body = safejson()
    language = safe(body.get("language"), "en")

    if language == "hi":
        system = (
            "आप एक Python debugging challenge बनाते हैं।\n"
            "एक short buggy Python program बनाएं (5-10 lines)।\n"
            "JSON format में respond करें:\n"
            "{\"code\": \"buggy code here\", \"hint\": \"एक line hint\", \"bug\": \"actual bug description\", \"fixed\": \"fixed code\"}\n"
            "Bugs simple होने चाहिए: syntax error, wrong variable name, off-by-one, missing colon आदि।\n"
            "केवल JSON।"
        )
    else:
        system = (
            "You create Python debugging challenges.\n"
            "Create a short buggy Python program (5-10 lines).\n"
            "Respond ONLY with JSON:\n"
            "{\"code\": \"buggy code here\", \"hint\": \"one line hint\", \"bug\": \"actual bug description\", \"fixed\": \"fixed code\"}\n"
            "Bugs should be simple: syntax error, wrong variable name, off-by-one, missing colon, etc.\n"
            "JSON only."
        )

    user = "Generate a bug challenge"
    raw = call_gemini(system, user, temperature=0.5, language=language)

    if raw.startswith("AI service") or "not configured" in raw.lower() or "unavailable" in raw.lower():
        return jsonify({
            "success": False,
            "error": "Bug challenge unavailable: AI not configured. Try the tutorial or write your own code instead.",
        })

    try:
        clean = re.sub(r'```(?:json)?\s*|\s*```', '', raw).strip()
        parsed = json.loads(clean)
    except Exception:
        return jsonify({
            "success": False,
            "error": "AI returned a malformed challenge. Try again.",
        })

    validation_error = _validate_bug_challenge(parsed)
    if validation_error:
        return jsonify({
            "success": False,
            "error": f"AI generated an invalid challenge ({validation_error}). Try saying 'bug challenge' again.",
        })

    return jsonify({"success": True, "challenge": parsed})


# ==========================
# VOICE INTENTS — story, breakpoint, mentor
# ==========================

# These are handled in the /voice-command route.
# New intents added to the bottom of the intent dispatch block:
# story_mode, set_breakpoint, clear_breakpoints, watch_variable,
# debug_continue, debug_step_in, debug_step_out,
# mentor_mode, quiz_me, explain_concept, bug_challenge


# ==========================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    host = os.environ.get("HOST", "127.0.0.1")
    app.run(debug=False, host=host, port=port)