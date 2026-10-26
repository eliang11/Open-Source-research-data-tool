"""
server.py — Local test website built on top of publicdata.py.

Runs a small web server (standard library only, no installs needed) that
exposes the portal search / download logic from publicdata.py through a
browser UI. The interactive input() prompts from the CLI are replaced by
a JSON API that webapp/index.html talks to.

Run:   python webapp/server.py          (opens http://127.0.0.1:8000)
       python webapp/server.py 8080     (prefer a different port)
       python webapp/server.py --no-browser
"""

import html
import json
import mimetypes
import os
import re
import socket
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse, urlsplit
from urllib.request import Request, urlopen

WEB_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(WEB_ROOT.parent))

import publicdata as core  # noqa: E402  (needs the sys.path tweak above)


#Bind address. The loopback by default, so the site is reachable only from
#this computer — which is what you want when running it locally. Set
#OPENDATA_HOST=0.0.0.0 only when something else provides the isolation, such
#as a hosting platform that terminates connections in front of this server.
HOST = os.environ.get("OPENDATA_HOST", "127.0.0.1")

#Host header names that may address this server, used to block DNS-rebinding.
#The port is deliberately not checked, because the port a client connects to
#is not always the port this process bound — anything forwarding or mapping
#ports in front of it makes "localhost:8080" legitimate while PORT is 8000.
ALLOWED_HOST_NAMES = {"127.0.0.1", "localhost", "::1"}
ALLOWED_HOST_NAMES |= {
    name.strip().lower()
    for name in os.environ.get("OPENDATA_ALLOW_HOSTS", "").split(",")
    if name.strip()
}

_port_args = [a for a in sys.argv[1:] if not a.startswith("-")]
REQUESTED_PORT = int(_port_args[0]) if _port_args else 8000

#The port actually bound — start_server() moves it if REQUESTED_PORT is taken
PORT = REQUESTED_PORT

#How many ports to try past the requested one before giving up
PORT_SEARCH_RANGE = 20

#Extensions the download folder is allowed to receive. The extension would
#otherwise come from whatever URL the portal's catalog gives, so a portal
#could drop a .exe or .bat next to the user's real data.
SAFE_EXTENSIONS = {
    "csv", "tsv",
    "json", "geojson",
    "xls", "xlsx",
    "zip",
    "kml", "kmz",
    "xml",
    "pdf",
    "txt",
    "gpx", "gdb",
    "dat",
}

#Catalogs are fetched once per portal and kept for the life of the server
_catalog_cache = {}

#Downloads write files and the shared history JSON, so run them one at a time
_download_lock = threading.Lock()


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


#Settings (replaces get_download_dir() / get_user_agent() prompts)

def default_download_dir():
    """Same default location logic as publicdata.get_download_dir()."""
    home = Path.home()
    if (home / "OneDrive" / "Desktop").exists():
        return home / "OneDrive" / "Desktop" / "open-data-downloads"
    if (home / "Desktop").exists():
        return home / "Desktop" / "open-data-downloads"
    return home / "Documents" / "open-data-downloads"


def apply_settings():
    """Load the saved config and set publicdata's module-level globals from it."""
    config = core.load_config()

    saved_dir = config.get("download_dir")
    core.DOWNLOAD_DIR = Path(saved_dir) if saved_dir else default_download_dir()

    contact = config.get("user_contact") or "unknown-user"
    core.USER_AGENT = f"{core.TOOL_NAME_VERSION} (research; {contact})"
    core.robots_cache = core.RobotsCache(core.USER_AGENT)


#Helpers

def require(data, name):
    value = data.get(name)
    if isinstance(value, str):
        value = value.strip()
    if not value:
        raise ApiError(400, f"Missing '{name}'")
    return value


def strip_html(text):
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def dataset_id(ds):
    """Stable ID for a dataset — matches what record_download() stores."""
    return ds.get("identifier") or ds.get("landingPage") or ds.get("title") or ""


def get_portal(portal_key):
    portal = core.get_all_portals().get(portal_key)
    if portal is None:
        raise ApiError(404, f"Unknown portal '{portal_key}'")
    return portal


def get_catalog(portal_key, refresh=False):
    portal = get_portal(portal_key)
    if refresh or portal_key not in _catalog_cache:
        try:
            datasets = core.fetch_catalog(portal)
        except ValueError as e:
            raise ApiError(502, f"The catalog was not valid JSON: {e}")
        if datasets is None:
            raise ApiError(502, f"Could not fetch the catalog for {portal['name']}. "
                                "Check your connection and the catalog URL.")
        _catalog_cache[portal_key] = datasets
    return portal, _catalog_cache[portal_key]


def find_dataset(datasets, ds_id):
    for ds in datasets:
        if dataset_id(ds) == ds_id:
            return ds
    raise ApiError(404, "Dataset not found in the catalog (try refreshing it)")


def summarize_dataset(ds):
    downloadables = core.find_downloadable_distributions(ds)
    formats = sorted({
        (d.get("format") or "").upper().strip()
        for d in downloadables
        if d.get("format")
    })
    description = strip_html(ds.get("description") or "")
    if len(description) > 280:
        description = description[:280].rstrip() + "…"
    return {
        "id": dataset_id(ds),
        "title": ds.get("title") or "(untitled)",
        "description": description,
        "modified": (ds.get("modified") or "")[:10],
        "formats": formats,
        #Whether a shapefile is on offer under any of the labels portals use
        "has_shapefile": bool(
            core.find_downloadable_distributions(ds, core.SHAPEFILE_FORMAT)
        ),
        "downloadable": bool(downloadables),
        "landing_page": ds.get("landingPage") or "",
    }


def safe_download_name(title, distribution, portal_key):
    """core.safe_filename(), but refusing extensions that aren't data files.

    core.safe_filename() falls back to the extension in the download URL, so a
    portal whose catalog points at an .exe or .bat would have that land in the
    download folder — which defaults to the Desktop. Anything not recognised as
    data is saved as .dat instead.
    """
    name = core.safe_filename(title, distribution, portal_key)
    if name.rpartition(".")[2].lower() in SAFE_EXTENSIONS:
        return name

    #Re-run with the format/URL stripped so it falls back to .dat, while
    #keeping the duplicate-name counter that checks the download folder
    return core.safe_filename(
        title,
        {"format": "", "mediaType": "", "downloadURL": ""},
        portal_key,
    )


def download_one(distribution, dataset, portal_key, confirm_large):
    """Web version of publicdata.download_distribution() — no input() prompts.

    Instead of asking about large files, returns status 'too_large' so the
    browser can ask the user and retry with confirm_large=True.
    """
    url = distribution.get("downloadURL") or distribution.get("accessURL")
    result = {
        "format": (distribution.get("format") or "").upper().strip(),
        "url": url or "",
    }
    if not url:
        return {**result, "status": "skipped", "message": "No URL on this distribution"}

    if not core.robots_cache.is_allowed(url):
        return {**result, "status": "blocked",
                "message": f"robots.txt for {urlparse(url).netloc} disallows this path"}

    if not confirm_large:
        size = core.check_file_size(url)
        if size is not None and size > core.SIZE_CONFIRM_THRESHOLD_BYTES:
            return {**result, "status": "too_large",
                    "size_mb": round(size / (1024 * 1024), 1)}

    title = dataset.get("title") or "(untitled)"
    core.DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    out_path = core.DOWNLOAD_DIR / safe_download_name(title, distribution, portal_key)

    core.rate_limiter.wait_for(url)
    req = Request(url, headers={"User-Agent": core.USER_AGENT})
    try:
        with urlopen(req, timeout=120) as response:
            out_path.write_bytes(response.read())
    except Exception as e:
        return {**result, "status": "failed", "message": str(e)}

    core.record_download(dataset, distribution, out_path, portal_key)
    return {**result, "status": "downloaded", "filename": out_path.name,
            "size_kb": round(out_path.stat().st_size / 1024, 1)}


#API endpoints — each takes (query, body) and returns a JSON-able dict

def api_list_portals(query, body):
    user_portals = core.load_user_portals()
    portals = []
    for key, p in core.get_all_portals().items():
        portals.append({
            "key": key,
            "name": p.get("name", key),
            "province": p.get("province", "Unspecified"),
            "homepage": p.get("homepage", ""),
            "catalog_url": p.get("catalog_url", ""),
            "user_added": key in user_portals,
        })
    portals.sort(key=lambda p: (p["province"], p["name"]))
    return {"portals": portals}


def api_add_portal(query, body):
    """Same validation as publicdata.add_user_portal()."""
    key = require(body, "key").lower()
    if " " in key:
        raise ApiError(400, "Key can't contain spaces")
    name = require(body, "name")
    catalog_url = require(body, "catalog_url")
    if not catalog_url.startswith(("http://", "https://")):
        raise ApiError(400, "Catalog URL must start with http:// or https://")

    entry = {
        "name": name,
        "type": "arcgis_hub",
        "catalog_url": catalog_url,
        "province": (body.get("province") or "").strip() or "Unspecified",
    }
    homepage = (body.get("homepage") or "").strip()
    if homepage:
        entry["homepage"] = homepage

    user_portals = core.load_user_portals()
    user_portals[key] = entry
    core.save_user_portals(user_portals)
    _catalog_cache.pop(key, None)
    return {"key": key}


def api_delete_portal(query, body):
    key = require(query, "key")
    user_portals = core.load_user_portals()
    if key not in user_portals:
        raise ApiError(400, "Built-in portals can't be deleted")
    del user_portals[key]
    core.save_user_portals(user_portals)
    _catalog_cache.pop(key, None)
    return {"deleted": key}


def api_catalog(query, body):
    key = require(query, "portal")
    portal, datasets = get_catalog(key, refresh=query.get("refresh") == "1")
    return {
        "key": key,
        "name": portal.get("name", key),
        "province": portal.get("province", "Unspecified"),
        "homepage": portal.get("homepage", ""),
        "count": len(datasets),
    }


def api_search(query, body):
    key = require(query, "portal")
    keyword = require(query, "q")
    _, datasets = get_catalog(key)
    matches = core.search_catalog(datasets, keyword)
    return {"matches": [summarize_dataset(ds) for ds in matches]}


def api_updates(query, body):
    key = require(query, "portal")
    _, datasets = get_catalog(key)
    updates = []
    for u in core.check_for_updates(datasets, key):
        record = u["record"]
        updates.append({
            "dataset_id": record.get("dataset_id"),
            "title": record.get("dataset_title", "(untitled)"),
            "format": record.get("distribution_format", ""),
            "old_modified": (u["old_modified"] or "")[:10] or "unknown",
            "new_modified": (u["new_modified"] or "")[:10] or "unknown",
        })
    return {"updates": updates}


def api_download(query, body):
    """Download one dataset's distributions.

    Body: portal, dataset_id, format (null = all formats),
          url (optional: only this distribution), first_only, confirm_large
    """
    key = require(body, "portal")
    ds_id = require(body, "dataset_id")
    _, datasets = get_catalog(key)
    ds = find_dataset(datasets, ds_id)

    dists = core.find_downloadable_distributions(ds, body.get("format") or None)
    if body.get("url"):
        dists = [d for d in dists
                 if (d.get("downloadURL") or d.get("accessURL")) == body["url"]]
    if body.get("first_only"):
        dists = dists[:1]

    with _download_lock:
        results = [download_one(d, ds, key, bool(body.get("confirm_large"))) for d in dists]
    return {"dataset_id": ds_id, "results": results}


def api_history(query, body):
    download_dir = core.DOWNLOAD_DIR.resolve()
    portals = core.get_all_portals()
    rows = []
    for rec in reversed(core.load_history().get("downloads", [])):
        path = Path(rec.get("local_path") or "")
        available = path.is_file() and path.resolve().parent == download_dir
        portal_key = rec.get("portal", "")
        rows.append({
            "title": rec.get("dataset_title", "(untitled)"),
            "portal": portals.get(portal_key, {}).get("name", portal_key),
            "format": rec.get("distribution_format", ""),
            "downloaded_at": (rec.get("downloaded_at") or "")[:16].replace("T", " "),
            "source_modified": (rec.get("modified_at_download") or "")[:10],
            "filename": path.name if available else None,
        })
    return {"downloads": rows}


def api_get_settings(query, body):
    config = core.load_config()
    return {
        "download_dir": str(core.DOWNLOAD_DIR),
        "download_dir_saved": bool(config.get("download_dir")),
        "default_download_dir": str(default_download_dir()),
        "user_contact": config.get("user_contact", ""),
        "user_agent": core.USER_AGENT,
        "config_path": str(core.CONFIG_PATH),
    }


def api_save_settings(query, body):
    config = core.load_config()

    new_dir = (body.get("download_dir") or "").strip()
    if new_dir:
        path = Path(new_dir).expanduser()
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise ApiError(400, f"Could not create folder: {e}")
        config["download_dir"] = str(path)
    else:
        config.pop("download_dir", None)

    contact = (body.get("user_contact") or "").strip()
    if contact:
        config["user_contact"] = contact
    else:
        config.pop("user_contact", None)

    core.save_config(config)
    apply_settings()
    return api_get_settings(query, body)


ROUTES = {
    ("GET", "/api/portals"): api_list_portals,
    ("POST", "/api/portals"): api_add_portal,
    ("DELETE", "/api/portals"): api_delete_portal,
    ("GET", "/api/catalog"): api_catalog,
    ("GET", "/api/search"): api_search,
    ("GET", "/api/updates"): api_updates,
    ("POST", "/api/download"): api_download,
    ("GET", "/api/history"): api_history,
    ("GET", "/api/settings"): api_get_settings,
    ("POST", "/api/settings"): api_save_settings,
}


#HTTP handler

class Handler(BaseHTTPRequestHandler):
    server_version = "OpenDataExplorerWeb/0.1"

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def _dispatch(self, method):
        #Only answer requests addressed to this machine (blocks DNS-rebinding
        #tricks). urlsplit parses the name out of "host:port" and "[::1]:port".
        hostname = urlsplit("//" + (self.headers.get("Host") or "")).hostname
        if (hostname or "") not in ALLOWED_HOST_NAMES:
            self._send_json({"error": "Forbidden host"}, 403)
            return

        parsed = urlparse(self.path)
        path = parsed.path
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}

        try:
            if method == "GET" and path in ("/", "/index.html"):
                self._send_bytes((WEB_ROOT / "index.html").read_bytes(), "text/html; charset=utf-8")
                return
            if method == "GET" and path.startswith("/files/"):
                self._send_download(unquote(path[len("/files/"):]))
                return

            handler = ROUTES.get((method, path))
            if handler is None:
                raise ApiError(404, "Not found")
            body = self._read_json() if method == "POST" else {}
            self._send_json(handler(query, body))
        except ApiError as e:
            self._send_json({"error": e.message}, e.status)
        except Exception as e:
            self._send_json({"error": f"Server error: {e}"}, 500)

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "Request body must be JSON")
        if not isinstance(data, dict):
            raise ApiError(400, "Request body must be a JSON object")
        return data

    def _send_download(self, filename):
        """Serve a file from the download folder (and nowhere else)."""
        download_dir = core.DOWNLOAD_DIR.resolve()
        target = (download_dir / filename).resolve()
        if target.parent != download_dir or not target.is_file():
            raise ApiError(404, "File not found")
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self._send_bytes(target.read_bytes(), content_type,
                         {"Content-Disposition": f'attachment; filename="{target.name}"'})

    def _send_json(self, payload, status=200):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_bytes(data, "application/json; charset=utf-8", status=status)

    def _send_bytes(self, data, content_type, extra_headers=None, status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)


def port_is_free(port):
    """True if nothing is already listening on this port.

    Tested by connecting rather than by binding: HTTPServer sets
    allow_reuse_address, and on Windows that lets a second process bind a port
    another program already holds, so a failed bind is not a reliable signal.
    """
    with socket.socket() as probe:
        probe.settimeout(0.3)
        return probe.connect_ex((HOST, port)) != 0


def start_server():
    """Bind the first free port at or after REQUESTED_PORT.

    Port 8000 is a common default, so on someone else's machine another
    program may already hold it. Moving to the next free port is friendlier
    than refusing to start.
    """
    global PORT
    last_error = None
    for candidate in range(REQUESTED_PORT, REQUESTED_PORT + PORT_SEARCH_RANGE):
        if not port_is_free(candidate):
            continue
        try:
            server = ThreadingHTTPServer((HOST, candidate), Handler)
        except OSError as e:
            last_error = e
            continue
        PORT = candidate
        return server

    raise SystemExit(
        f"Could not find a free port between {REQUESTED_PORT} and "
        f"{REQUESTED_PORT + PORT_SEARCH_RANGE - 1}. Last error: {last_error}"
    )


def main():
    apply_settings()
    server = start_server()

    #0.0.0.0 is an address to listen on, not one to visit, so show a usable one
    display_host = "localhost" if HOST in ("0.0.0.0", "::") else HOST
    url = f"http://{display_host}:{PORT}"

    if PORT != REQUESTED_PORT:
        print(f"Port {REQUESTED_PORT} is in use by another program; using {PORT}.")
    print(f"Open Data Explorer running at {url}")
    print(f"Downloads are saved to: {core.DOWNLOAD_DIR}")
    print("Press Ctrl+C to stop.")

    #No browser to open when bound to all interfaces: that only happens when
    #something else is serving this to a user elsewhere
    if "--no-browser" not in sys.argv and HOST not in ("0.0.0.0", "::"):
        opener = threading.Timer(1.0, webbrowser.open, args=(url,))
        opener.daemon = True
        opener.start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("\nStopped.")


if __name__ == "__main__":
    main()
       
