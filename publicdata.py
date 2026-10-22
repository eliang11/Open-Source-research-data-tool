"""
publicdata.py — Search BC open data portals via their DCAT feeds
and download dataset files matching a keyword.

Supports multiple BC city portals (Kelowna, Vancouver, Victoria, Burnaby)
with the option for users to add more.

Downloads any actual data file (CSV, JSON, Excel, ZIP, KML, etc.) but
skips HTML landing pages and other non-data URLs.
"""

import json
import time
import urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


#Configuration

USER_AGENT = None  #Set by get_user_agent() in main()
TOOL_NAME_VERSION = "OpenDataExplorer/0.1"
CONFIG_PATH = Path.home() / ".publicdataconfig.json"
HISTORY_PATH = Path.home() / ".publicdatahistory.json"
PORTALS_CONFIG_PATH = Path.home() / ".publicdataportals.json"

#Set by get_download_dir() at start of main()
DOWNLOAD_DIR = None

#Rate limit + size threshold
RATE_LIMIT_SECONDS = 1.5
SIZE_CONFIRM_THRESHOLD_BYTES = 100 * 1024 * 1024  # 100 MB


#Verified BC open data portals 
DEFAULT_PORTALS = {
    "kelowna": {
        "name": "City of Kelowna",
        "type": "arcgis_hub",
        "catalog_url": "https://opendata.kelowna.ca/api/feed/dcat-us/1.1.json",
        "homepage": "https://opendata.kelowna.ca",
        "province": "British Columbia",
        "dataset_count": 283,
    },
    "vancouver": {
        "name": "City of Vancouver",
        "type": "arcgis_hub",
        "catalog_url": "https://opendata.vancouver.ca/data.json",
        "homepage": "https://opendata.vancouver.ca",
        "province": "British Columbia",
        "dataset_count": 197,
    },
    "victoria": {
        "name": "City of Victoria",
        "type": "arcgis_hub",
        "catalog_url": "https://opendata.victoria.ca/api/feed/dcat-us/1.1.json",
        "homepage": "https://opendata.victoria.ca",
        "province": "British Columbia",
        "dataset_count": 502,
    },
    "burnaby": {
        "name": "City of Burnaby",
        "type": "arcgis_hub",
        "catalog_url": "https://data.burnaby.ca/api/feed/dcat-us/1.1.json",
        "homepage": "https://data.burnaby.ca",
        "province": "British Columbia",
        "dataset_count": 74,
    },
}


#Format sets used to filter downloadable content
DATA_FORMATS = {
    "CSV",
    "JSON", "GEOJSON",
    "XLS", "XLSX", "EXCEL",
    "ZIP", "SHAPEFILE", "SHP",
    "KML", "KMZ",
    "XML",
    "PDF",
    "TXT",
    "GPX",
    "GDB",
}

#Portals disagree on what to call a shapefile download. Vancouver labels it
#"SHP"; Kelowna, Victoria and Burnaby label the identical bundle "ZIP" (each
#verified to contain a complete .shp/.shx/.dbf/.prj set). Picking "SHP" would
#therefore return nothing on three of the four portals, so this virtual format
#matches either label and lets one choice work everywhere.
#
#It matters because CSV drops the geometry: a polygon layer exported to CSV
#keeps the attributes and an area figure, but not the outline itself.
SHAPEFILE_FORMAT = "SHAPEFILE"

#Labels that always mean a shapefile
SHAPEFILE_ALIASES = {"SHP", "SHAPEFILE"}

#ArcGIS Hub also offers a File Geodatabase under that same "ZIP" label, with
#only the distribution title and the download URL to tell them apart, so a
#plain label check would fetch both. These words mark a ZIP as something else.
NOT_SHAPEFILE_HINTS = ("filegdb", "geodatabase", ".gdb", "kml", "kmz",
                       "csv", "geojson", "excel", "xlsx")

NON_DATA_FORMATS = {
    "WEB PAGE", "HTML", "WEBSITE",
    "ESRI REST",
    "ARCGIS GEOSERVICES REST API",
    "OGC WFS", "OGC WMS",
    "WMS", "WFS",
}


#Rate limiter 

class RateLimiter:
    """Tracks time of last request per domain and enforces a minimum delay."""

    def __init__(self, delay_seconds=1.5):
        self.delay_seconds = delay_seconds
        self._last_request_time = {}

    def wait_for(self, url):
        domain = urlparse(url).netloc.lower()
        if not domain:
            return
        now = time.time()
        last_time = self._last_request_time.get(domain)

        if last_time is not None:
            elapsed = now - last_time
            wait_needed = self.delay_seconds - elapsed
            if wait_needed > 0:
                time.sleep(wait_needed)
                now = time.time()

        self._last_request_time[domain] = now


rate_limiter = RateLimiter(delay_seconds=RATE_LIMIT_SECONDS)


#Robots.txt cache (ethical scraping)

class RobotsCache:
    """Fetches and caches robots.txt per domain for a session.
    
    Uses Python's stdlib robots.txt parser. Each domain's robots.txt is
    fetched once and reused for the rest of the session.
    """

    def __init__(self, user_agent):
        self.user_agent = user_agent
        self._cache = {}  # Maps domain -> RobotFileParser (or None if fetch failed)

    def is_allowed(self, url):
        """Return True if robots.txt allows fetching this URL.
        
        If robots.txt is missing or unreadable, defaults to True (allow).
        """
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        if domain not in self._cache:
            self._cache[domain] = self._fetch_robots_for(parsed.scheme, domain)

        parser = self._cache[domain]
        if parser is None:
            return True

        return parser.can_fetch(self.user_agent, url)

    def _fetch_robots_for(self, scheme, domain):
        """Fetch robots.txt for one domain. Returns a parser or None on failure."""
        robots_url = f"{scheme}://{domain}/robots.txt"
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(robots_url)
        try:
            parser.read()
            return parser
        except Exception:
            return None


#Set in main() after USER_AGENT is resolved
robots_cache = None


#Notifications 

class Notifications:
    """Collects notifications during a session and prints a summary at the end."""

    LEVEL_WARNING = "warning"
    LEVEL_ERROR = "error"
    LEVEL_INFO = "info"

    def __init__(self):
        self._items = []

    def add(self, level, category, subject, reason, suggestion=None):
        self._items.append({
            "level": level,
            "category": category,
            "subject": subject,
            "reason": reason,
            "suggestion": suggestion,
        })

    def has_any(self):
        return len(self._items) > 0

    def print_summary(self):
        """Print all collected notifications, grouped by category."""
        if not self._items:
            print("No issues encountered this session.\n")
            return

        by_category = {}
        for item in self._items:
            by_category.setdefault(item["category"], []).append(item)

        labels = {
            "download_failed": "Downloads that failed",
            "robots_disallowed": "URLs blocked by robots.txt",
            "no_format_available": "Datasets without the requested format",
            "size_skipped": "Large files the user chose not to download",
            "catalog_error": "Catalog fetch errors",
        }

        print("\n--- Notifications ---\n")
        for category in sorted(by_category.keys()):
            label = labels.get(category, category)
            items = by_category[category]
            print(f"{label} ({len(items)}):")
            for item in items:
                print(f"  • {item['subject']}")
                print(f"    Reason: {item['reason']}")
                if item.get("suggestion"):
                    print(f"    Suggestion: {item['suggestion']}")
            print()


notifications = Notifications()


#Download location config 

def load_config():
    """Read settings from the config file. Returns {} if no file or unreadable."""
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        print(f"Warning: config at {CONFIG_PATH} is unreadable; starting fresh.")
        return {}


def save_config(config):
    """Write the config dictionary to disk as JSON."""
    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")


def get_download_dir():
    """Return the download directory.
    
    On first run (no saved config), asks if the user wants to configure
    a permanent folder. If yes, prompts for path and saves for future runs.
    If no, uses a temporary default for this session only.
    """
    config = load_config()
    
    saved_path = config.get("download_dir")
    if saved_path:
        path = Path(saved_path)
        if path.exists() or path.parent.exists():
            return path
        else:
            print(f"Note: previously-configured folder no longer accessible.")
            print(f"  Was: {saved_path}")
    
    home = Path.home()
    if (home / "OneDrive" / "Desktop").exists():
        default_path = home / "OneDrive" / "Desktop" / "open-data-downloads"
    elif (home / "Desktop").exists():
        default_path = home / "Desktop" / "open-data-downloads"
    else:
        default_path = home / "Documents" / "open-data-downloads"
    
    print("\nDownloaded datasets need a folder to save into.")
    print(f"Default location: {default_path}")
    print()
    print("Would you like to configure a permanent folder for future runs?")
    print("  y = yes, ask me where and remember it")
    print("  n = no, just use the default for this run only")
    print("  Enter = same as 'n'")
    choice = input("Configure permanent folder? [y/N]: ").strip().lower()
    
    if choice == "y":
        print(f"\nEnter folder path, or press Enter to use the default:")
        print(f"Default: {default_path}")
        user_input = input("Folder path: ").strip()
        chosen_path = Path(user_input) if user_input else default_path
        
        try:
            chosen_path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print(f"Could not create folder at {chosen_path}: {e}")
            print(f"Falling back to default: {default_path}")
            chosen_path = default_path
            chosen_path.mkdir(parents=True, exist_ok=True)
        
        config["download_dir"] = str(chosen_path)
        save_config(config)
        print(f"Saved. Future runs will use: {chosen_path}")
        print(f"(To reset this later, delete {CONFIG_PATH})\n")
        return chosen_path
    
    else:
        try:
            default_path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print(f"Could not create default folder: {e}")
            fallback = Path.cwd() / "open-data-downloads"
            fallback.mkdir(parents=True, exist_ok=True)
            print(f"Using: {fallback}")
            return fallback
        
        print(f"Using {default_path} for this run only.")
        print(f"(You'll be asked again next time you run the tool.)\n")
        return default_path


def get_user_agent():
    """Return the User-Agent string, prompting the user on first run for contact info."""
    config = load_config()
    
    saved_contact = config.get("user_contact")
    if saved_contact:
        return f"{TOOL_NAME_VERSION} (research; {saved_contact})"
    
    print("\n--- Contact info ---")
    print("This tool identifies itself to open data portals via a User-Agent")
    print("string that includes your contact info. This is polite practice —")
    print("it lets portal operators reach you if something looks wrong.")
    print()
    print("Suggested: your email address, or a URL where you can be reached.")
    print("If you skip, a generic 'unknown-user' will be used, but this may")
    print("be flagged as suspicious by some portals.")
    print()
    
    try:
        contact = input("Contact info (email or URL, or press Enter to skip): ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nSkipping.")
        contact = ""
    
    if not contact:
        contact = "unknown-user"
        print("Using generic identifier.\n")
    else:
        config["user_contact"] = contact
        save_config(config)
        print(f"Saved. Future runs will identify as '{contact}'.")
        print(f"(To change this later, edit or delete {CONFIG_PATH})\n")
    
    return f"{TOOL_NAME_VERSION} (research; {contact})"


#Portal registry 

def load_user_portals():
    """Read the user's custom portal list. Returns {} if none."""
    if not PORTALS_CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(PORTALS_CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        print(f"Warning: portal list at {PORTALS_CONFIG_PATH} is unreadable.")
        return {}


def save_user_portals(portals):
    """Write the user's custom portal list to disk."""
    PORTALS_CONFIG_PATH.write_text(
        json.dumps(portals, indent=2),
        encoding="utf-8",
    )


def get_all_portals():
    """Combine defaults with user additions. User entries override defaults."""
    combined = dict(DEFAULT_PORTALS)
    user_portals = load_user_portals()
    combined.update(user_portals)
    return combined


def add_user_portal():
    """Interactively add a new portal to the user's config.
    
    Returns the new portal key on success, or None if cancelled/invalid.
    """
    print("\n--- Add a new portal ---")
    print("Only ArcGIS Hub portals (with DCAT feed) are supported right now.")
    print("To find a portal's DCAT URL, try:")
    print("  {portal-homepage}/api/feed/dcat-us/1.1.json")
    print("  {portal-homepage}/data.json")
    print("If you see JSON with a 'dataset' array, that's the catalog URL.\n")

    try:
        key = input("Short key (lowercase, no spaces, e.g. 'nanaimo'): ").strip().lower()
        if not key or " " in key:
            print("Invalid key (no spaces allowed).")
            return None

        if key in DEFAULT_PORTALS:
            confirm = input(f"'{key}' already exists as a default. Overwrite? [y/N]: ").strip().lower()
            if confirm != "y":
                print("Cancelled.")
                return None

        name = input("Display name (e.g. 'City of Nanaimo'): ").strip()
        if not name:
            print("Display name required. Aborting.")
            return None

        catalog_url = input("Catalog URL (full https:// URL to DCAT feed): ").strip()
        if not catalog_url.startswith(("http://", "https://")):
            print("URL must start with http:// or https://. Aborting.")
            return None

        homepage = input("Homepage URL (optional, press Enter to skip): ").strip()

        print("\nWhich province is this portal from?")
        print("  Examples: British Columbia, Alberta, Ontario")
        province = input("Province (or press Enter for 'Unspecified'): ").strip()

    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        return None

    new_entry = {
        "name": name,
        "type": "arcgis_hub",
        "catalog_url": catalog_url,
        "province": province if province else "Unspecified",
    }
    if homepage:
        new_entry["homepage"] = homepage

    user_portals = load_user_portals()
    user_portals[key] = new_entry
    save_user_portals(user_portals)

    print(f"\nAdded '{name}' as '{key}'.")
    print(f"Saved to {PORTALS_CONFIG_PATH}\n")
    return key


def delete_user_portal():
    """Interactively delete a user-added portal.
    
    Built-in portals cannot be deleted.
    """
    user_portals = load_user_portals()
    
    if not user_portals:
        print("\nYou haven't added any portals yet.")
        print("Built-in portals cannot be deleted.\n")
        return
    
    print("\nUser-added portals:\n")
    keys = sorted(user_portals.keys())
    for i, key in enumerate(keys, 1):
        portal = user_portals[key]
        province = portal.get("province", "Unspecified")
        print(f"  [{i}] {portal['name']}  ({province})")
    print(f"  Type 'quit' or press Ctrl+C to cancel.")
    
    try:
        choice = input("\nWhich portal to delete? ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        return
    
    if choice in ("quit", "exit", "cancel", "q"):
        return
    
    try:
        choice_num = int(choice)
    except ValueError:
        print(f"  '{choice}' isn't a number. Cancelled.")
        return
    
    if choice_num < 1 or choice_num > len(keys):
        print(f"  Out of range. Cancelled.")
        return
    
    chosen_key = keys[choice_num - 1]
    portal_name = user_portals[chosen_key]["name"]
    
    confirm = input(f"Delete '{portal_name}'? [y/N]: ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        return
    
    del user_portals[chosen_key]
    save_user_portals(user_portals)
    print(f"Deleted '{portal_name}'.\n")


def pick_portal():
    """Show available portals grouped by province and let the user pick one.
    
    Also offers 'Add a new portal' and 'Delete a portal' options.
    Returns (portal_key, portal_dict) or (None, None) if cancelled.
    """
    while True:
        portals = get_all_portals()
        user_portals = load_user_portals()

        if not portals:
            print("\nNo portals configured.")
            choice = input("Add one now? [y/N]: ").strip().lower()
            if choice == "y":
                new_key = add_user_portal()
                if new_key:
                    return new_key, get_all_portals()[new_key]
            return None, None

        #Group portals by province
        by_province = {}
        for key, portal in portals.items():
            province = portal.get("province", "Unspecified")
            by_province.setdefault(province, []).append((key, portal))
        
        sorted_provinces = sorted(by_province.keys())
        for province in sorted_provinces:
            by_province[province].sort(key=lambda item: item[1]["name"])
        
        print("\nAvailable open data portals:\n")
        flat_list = []
        
        for province in sorted_provinces:
            print(f"{province}:")
            for key, portal in by_province[province]:
                flat_list.append((key, portal))
                number = len(flat_list)
                source = "user-added" if key in user_portals else "built-in"
                print(f"  [{number}] {portal['name']}  ({source})")
            print()
        
        add_option = len(flat_list) + 1
        delete_option = len(flat_list) + 2
        print(f"  [{add_option}] Add a new portal...")
        print(f"  [{delete_option}] Delete a user-added portal...")
        print(f"  Type 'quit' or press Ctrl+C to exit.")

        try:
            choice = input("\nPick a portal: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled.")
            return None, None

        if choice in ("quit", "exit", "cancel", "q"):
            return None, None

        try:
            choice_num = int(choice)
        except ValueError:
            print(f"  '{choice}' isn't a number. Try again.")
            continue

        if choice_num == add_option:
            add_user_portal()
            continue
        
        if choice_num == delete_option:
            delete_user_portal()
            continue

        if 1 <= choice_num <= len(flat_list):
            chosen_key, chosen_portal = flat_list[choice_num - 1]
            return chosen_key, chosen_portal

        print(f"  Out of range (1-{delete_option}). Try again.")


#History and update tracking

def load_history():
    """Read the download history file. Returns empty history if none exists."""
    if not HISTORY_PATH.exists():
        return {"downloads": []}
    try:
        return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        print(f"Warning: history at {HISTORY_PATH} is unreadable; starting fresh.")
        return {"downloads": []}


def save_history(history):
    """Write the history to disk."""
    HISTORY_PATH.write_text(
        json.dumps(history, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def record_download(dataset, distribution, local_path, portal_key):
    """Add an entry to the download history after a successful download."""
    history = load_history()

    entry = {
        "portal": portal_key,
        "dataset_id": dataset.get("identifier") or dataset.get("landingPage") or "",
        "dataset_title": dataset.get("title") or "(untitled)",
        "distribution_format": (distribution.get("format") or "").upper().strip(),
        "source_url": distribution.get("downloadURL") or distribution.get("accessURL") or "",
        "modified_at_download": dataset.get("modified") or "",
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "local_path": str(local_path),
    }

    downloads = history["downloads"]
    for i, existing in enumerate(downloads):
        same_portal = existing.get("portal") == entry["portal"]
        same_dataset = existing.get("dataset_id") == entry["dataset_id"]
        same_format = existing.get("distribution_format") == entry["distribution_format"]
        if same_portal and same_dataset and same_format:
            downloads[i] = entry
            save_history(history)
            return

    downloads.append(entry)
    save_history(history)


def check_for_updates(current_catalog, portal_key):
    """Compare downloaded history against the current catalog for a portal."""
    history = load_history()
    tracked = [d for d in history["downloads"] if d.get("portal") == portal_key]

    if not tracked:
        return []

    catalog_by_id = {}
    for ds in current_catalog:
        ds_id = ds.get("identifier") or ds.get("landingPage") or ""
        if ds_id:
            catalog_by_id[ds_id] = ds

    updates = []
    for record in tracked:
        ds_id = record.get("dataset_id")
        if not ds_id or ds_id not in catalog_by_id:
            continue

        current = catalog_by_id[ds_id]
        current_modified = current.get("modified") or ""
        recorded_modified = record.get("modified_at_download") or ""

        if current_modified and current_modified != recorded_modified:
            updates.append({
                "record": record,
                "current_dataset": current,
                "old_modified": recorded_modified,
                "new_modified": current_modified,
            })

    return updates


def prompt_for_update_refresh(updates):
    """Show the user what's been updated and ask if they want to re-download."""
    print(f"\n{len(updates)} previously-downloaded dataset(s) have been updated:\n")

    for i, u in enumerate(updates, 1):
        record = u["record"]
        title = record.get("dataset_title", "(untitled)")
        fmt = record.get("distribution_format", "unknown")
        old_date = u["old_modified"][:10] if u["old_modified"] else "unknown"
        new_date = u["new_modified"][:10] if u["new_modified"] else "unknown"

        print(f"  [{i:2}] {title}")
        print(f"       Format: {fmt}")
        print(f"       Was: {old_date}  →  Now: {new_date}")

    print()
    print("Re-download updated datasets?")
    print("  Examples: 1,3,5  |  all  |  none")
    print("  Type 'quit' or press Ctrl+C to skip and continue.")

    while True:
        try:
            selection_text = input("Your pick: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nSkipping update refresh.")
            return []

        if selection_text.lower() in ("quit", "exit", "cancel", "q", "skip"):
            print("Skipped.")
            return []

        if not selection_text:
            print("  Please enter a selection, or type 'quit' to skip.")
            continue

        selected_indices = parse_selection(selection_text, len(updates))

        if not selected_indices and selection_text.lower() != "none":
            print("  No valid selections. Try again, or type 'quit'.")
            continue

        break

    if not selected_indices:
        return []

    return [updates[i - 1] for i in selected_indices]


#Catalog fetching 

def fetch_catalog(portal):
    """Fetch a portal's catalog. Dispatches based on portal type."""
    portal_type = portal.get("type")
    portal_name = portal.get("name", "(unnamed portal)")

    if portal_type == "arcgis_hub":
        return _fetch_arcgis_hub_catalog(portal["catalog_url"], portal_name)

    print(f"Portal type '{portal_type}' is not yet supported.")
    return None


def _fetch_arcgis_hub_catalog(catalog_url, portal_name):
    """Fetch a DCAT feed from an ArcGIS Hub portal."""
    print(f"Fetching catalog for {portal_name}...")
    print(f"  ({catalog_url})")
    rate_limiter.wait_for(catalog_url)
    req = Request(catalog_url, headers={"User-Agent": USER_AGENT})

    try:
        response = urlopen(req, timeout=30)
        body = response.read().decode("utf-8")
    except Exception as e:
        print(f"Failed to fetch catalog: {e}")
        notifications.add(
            level=Notifications.LEVEL_ERROR,
            category="catalog_error",
            subject=portal_name,
            reason=str(e),
            suggestion="Check network connection and verify the catalog URL is correct",
        )
        return None

    data = json.loads(body)
    datasets = data.get("dataset", [])
    print(f"Catalog contains {len(datasets)} datasets.\n")
    return datasets


#Search 

def search_catalog(datasets, keyword):
    keyword_lower = keyword.lower()
    matches = []
    for ds in datasets:
        title = (ds.get("title") or "").lower()
        description = (ds.get("description") or "").lower()
        tags = " ".join(ds.get("keyword") or []).lower()
        if keyword_lower in title or keyword_lower in description or keyword_lower in tags:
            matches.append(ds)
    return matches


#User selection helpers

def parse_selection(selection_text, max_number):
    selection_text = selection_text.strip().lower()

    if not selection_text or selection_text == "none":
        return []

    if selection_text == "all":
        return list(range(1, max_number + 1))
    selected = set()

    for part in selection_text.split(","):
        part = part.strip()
        if not part:
            continue

        if "-" in part:
            try:
                start_str, end_str = part.split("-", 1)
                start = int(start_str.strip())
                end = int(end_str.strip())
                if start > end:
                    start, end = end, start
                for n in range(start, end + 1):
                    if 1 <= n <= max_number:
                        selected.add(n)
            except ValueError:
                print(f"  Warning: couldn't parse '{part}', skipping")
        else:
            try:
                n = int(part)
                if 1 <= n <= max_number:
                    selected.add(n)
                else:
                    print(f"  Warning: {n} is out of range (1-{max_number}), skipping")
            except ValueError:
                print(f"  Warning: '{part}' isn't a number, skipping")

    return sorted(selected)


def pick_datasets(matches):
    """Show matching datasets and get the user's selection."""
    print("Datasets found:\n")

    for i, ds in enumerate(matches, 1):
        title = ds.get("title") or "(untitled)"

        downloadables = find_downloadable_distributions(ds)
        if downloadables:
            formats = sorted({
                (d.get("format") or "").upper().strip()
                for d in downloadables
                if d.get("format")
            })
            format_str = ", ".join(formats) if formats else "no formats listed"
        else:
            format_str = "landing page only — nothing to download"

        print(f"  [{i:2}] {title}")
        print(f"       Available: {format_str}")

    print()
    print("Pick datasets to download:")
    print("  Examples: 1,3,5  |  1-4  |  1,3-7,10  |  all")
    print("  Type 'quit' or press Ctrl+C to exit.")

    while True:
        try:
            selection_text = input("Your pick: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled.")
            return []

        if selection_text.lower() in ("quit", "exit", "cancel", "q"):
            print("Cancelled.")
            return []

        if not selection_text:
            print("  Please enter a selection, or type 'quit' to exit.")
            continue

        selected_indices = parse_selection(selection_text, len(matches))

        if not selected_indices:
            print("  No valid selections found. Try again, or type 'quit'.")
            continue

        break

    selected = [matches[i - 1] for i in selected_indices]
    print(f"\nSelected {len(selected)} dataset(s).\n")
    return selected


def pick_formats(selected_datasets):
    """Show available formats across selected datasets and let the user pick one."""
    available_formats = {}

    for ds in selected_datasets:
        formats_in_dataset = set()
        for dist in find_downloadable_distributions(ds):
            fmt = (dist.get("format") or "").upper().strip()
            if fmt:
                formats_in_dataset.add(fmt)
        for fmt in formats_in_dataset:
            available_formats[fmt] = available_formats.get(fmt, 0) + 1

    if not available_formats:
        print("No downloadable formats in selected datasets.")
        return None

    sorted_formats = sorted(
        available_formats.items(),
        key=lambda pair: (-pair[1], pair[0])
    )

    #Offer the shapefile bundle as one choice, listed first, however the portal
    #happens to label it. Shapefiles keep the geometry that CSV discards.
    shapefile_count = sum(
        1 for ds in selected_datasets
        if find_downloadable_distributions(ds, SHAPEFILE_FORMAT)
    )
    if shapefile_count:
        sorted_formats.insert(0, (SHAPEFILE_FORMAT, shapefile_count))

    print("Available formats:")
    for i, (fmt, count) in enumerate(sorted_formats, 1):
        coverage = f"available in {count}/{len(selected_datasets)} dataset(s)"
        label = f"{fmt}  (keeps map geometry; SHP or ZIP)" if fmt == SHAPEFILE_FORMAT else fmt
        print(f"  [{i}] {label}  ({coverage})")
    all_option = len(sorted_formats) + 1
    print(f"  [{all_option}] All formats (download every available version)")

    choice = input("Pick a format number: ").strip()

    try:
        choice_num = int(choice)
    except ValueError:
        print("Not a number — defaulting to most common format.")
        return sorted_formats[0][0]

    if choice_num == all_option:
        return None

    if 1 <= choice_num <= len(sorted_formats):
        return sorted_formats[choice_num - 1][0]

    print("Out of range — defaulting to most common format.")
    return sorted_formats[0][0]


#Distribution filtering

def is_downloadable_data(distribution):
    """Return True if this distribution points to an actual data file."""
    format_str = (distribution.get("format") or "").upper().strip()
    media_type = (distribution.get("mediaType") or "").lower().strip()

    if format_str in NON_DATA_FORMATS:
        return False
    if media_type == "text/html":
        return False

    download_url = distribution.get("downloadURL")
    if download_url:
        return True

    if format_str in DATA_FORMATS:
        return True

    return False


def is_shapefile_distribution(distribution):
    """Return True if this distribution is the shapefile bundle.

    Needed because portals disagree: Vancouver labels it "SHP", while Kelowna,
    Victoria and Burnaby label it "ZIP" — and those same portals also publish a
    File Geodatabase as "ZIP". The title and URL are what separate them.
    """
    fmt = (distribution.get("format") or "").upper().strip()
    if fmt in SHAPEFILE_ALIASES:
        return True
    if fmt != "ZIP":
        return False

    hint = " ".join((
        distribution.get("title") or "",
        distribution.get("downloadURL") or distribution.get("accessURL") or "",
    )).lower()

    if "shapefile" in hint:
        return True
    if any(word in hint for word in NOT_SHAPEFILE_HINTS):
        return False

    #A ZIP with nothing to distinguish it: on these portals that is the
    #shapefile export, so treat it as one rather than hiding it
    return True


def find_downloadable_distributions(dataset, preferred_format=None):
    """Get downloadable distributions, optionally filtered to a specific format.

    SHAPEFILE_FORMAT is a virtual format: it matches whichever label the portal
    uses for its shapefile bundle, rather than a format string of its own.
    """
    matches = [d for d in dataset.get("distribution", []) if is_downloadable_data(d)]

    if preferred_format is None:
        return matches

    preferred_upper = preferred_format.upper().strip()

    if preferred_upper == SHAPEFILE_FORMAT:
        shapefiles = [d for d in matches if is_shapefile_distribution(d)]
        #If a portal offers both labels, take the explicit one rather than
        #downloading the same data twice
        explicit = [
            d for d in shapefiles
            if (d.get("format") or "").upper().strip() in SHAPEFILE_ALIASES
        ]
        return explicit or shapefiles

    return [
        d for d in matches
        if (d.get("format") or "").upper().strip() == preferred_upper
    ]


#File download helpers

def check_file_size(url):
    """Send a HEAD request to find out the file size. Returns bytes, or None."""
    rate_limiter.wait_for(url)
    req = Request(url, headers={"User-Agent": USER_AGENT}, method="HEAD")
    try:
        response = urlopen(req, timeout=15)
        length = response.headers.get("Content-Length")
        return int(length) if length else None
    except Exception:
        return None


def safe_filename(dataset_title, distribution, portal_key=None, fallback_ext="dat"):
    """Build a filesystem-safe filename based on title + format.
    
    Prefixes the portal_key to reduce collisions across portals.
    If a file with the same name already exists in DOWNLOAD_DIR, appends
    a counter (e.g. Street_2.csv) to avoid overwriting.
    """
    title_clean = "".join(c if c.isalnum() or c in "-_." else "_" for c in dataset_title)
    title_clean = title_clean.strip("_") or "dataset"

    fmt = (distribution.get("format") or "").lower().strip()
    media_type = (distribution.get("mediaType") or "").lower().strip()
    url = distribution.get("downloadURL") or distribution.get("accessURL") or ""

    ext_map = {
        "csv": "csv", "json": "json", "geojson": "geojson",
        "xls": "xls", "xlsx": "xlsx", "excel": "xlsx",
        "zip": "zip", "shapefile": "zip", "shp": "zip",
        "kml": "kml", "kmz": "kmz",
        "xml": "xml", "pdf": "pdf", "txt": "txt",
    }
    ext = ext_map.get(fmt)

    if not ext:
        if "/" in media_type:
            ext = media_type.split("/")[-1].split(";")[0]

    if not ext:
        url_path = urlparse(url).path
        if "." in url_path:
            ext = url_path.rsplit(".", 1)[-1][:5]

    if not ext:
        ext = fallback_ext

    # Prefix with portal key so downloads from different portals don't collide
    prefix = f"{portal_key}_" if portal_key else ""
    base_name = f"{prefix}{title_clean}.{ext}"

    # If the file already exists, add a counter to make it unique
    if DOWNLOAD_DIR is not None:
        out_path = DOWNLOAD_DIR / base_name
        if out_path.exists():
            counter = 2
            while (DOWNLOAD_DIR / f"{prefix}{title_clean}_{counter}.{ext}").exists():
                counter += 1
            base_name = f"{prefix}{title_clean}_{counter}.{ext}"

    return base_name


def download_distribution(distribution, dataset, portal_key):
    """Download one distribution and record it in the history."""
    url = distribution.get("downloadURL") or distribution.get("accessURL")
    if not url:
        print("    (no URL on this distribution, skipping)")
        return False

    dataset_title = dataset.get("title") or "(untitled)"

    #Ethical scraping: check robots.txt before doing anything
    if not robots_cache.is_allowed(url):
        print(f"    Skipped: robots.txt disallows this URL")
        notifications.add(
            level=Notifications.LEVEL_WARNING,
            category="robots_disallowed",
            subject=f"{dataset_title} ({distribution.get('format', 'unknown')})",
            reason=f"robots.txt for {urlparse(url).netloc} disallows this path",
            suggestion="Try downloading manually from the source website",
        )
        return False

    size = check_file_size(url)
    if size is not None and size > SIZE_CONFIRM_THRESHOLD_BYTES:
        size_mb = size / (1024 * 1024)
        answer = input(f"    File is {size_mb:.1f} MB. Download? [y/N]: ").strip().lower()
        if answer != "y":
            print("    Skipped.")
            notifications.add(
                level=Notifications.LEVEL_INFO,
                category="size_skipped",
                subject=f"{dataset_title} ({size_mb:.1f} MB)",
                reason="File exceeds size threshold and user declined",
                suggestion="Increase SIZE_CONFIRM_THRESHOLD_BYTES or download manually",
            )
            return False

    filename = safe_filename(dataset_title, distribution, portal_key)
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DOWNLOAD_DIR / filename

    print(f"    Downloading: {url}")
    print(f"    Saving as:   {out_path.name}")

    rate_limiter.wait_for(url)
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        response = urlopen(req, timeout=120)
        out_path.write_bytes(response.read())
        size_kb = out_path.stat().st_size / 1024
        print(f"    Done ({size_kb:.1f} KB)")

        record_download(dataset, distribution, out_path, portal_key)
        return True
    except Exception as e:
        print(f"    Download failed: {e}")
        notifications.add(
            level=Notifications.LEVEL_ERROR,
            category="download_failed",
            subject=f"{dataset_title} ({distribution.get('format', 'unknown')})",
            reason=str(e),
            suggestion="Check the source URL manually or try again later",
        )
        return False


#Main flow 

def main():
    # Get the download location
    global DOWNLOAD_DIR
    DOWNLOAD_DIR = get_download_dir()
    print(f"Files will be saved to: {DOWNLOAD_DIR.resolve()}\n")

    # Get the User-Agent (asks user on first run for contact info)
    global USER_AGENT
    USER_AGENT = get_user_agent()

    # Initialize robots.txt cache with the resolved User-Agent
    global robots_cache
    robots_cache = RobotsCache(USER_AGENT)

    # Session state — kept across searches within the same portal
    current_portal_key = None
    current_portal = None
    current_datasets = None

    # Main session loop — keeps running until user quits
    while True:
        # If no portal selected yet, prompt for one
        if current_portal is None:
            current_portal_key, current_portal = pick_portal()
            if current_portal is None:
                # User cancelled the portal picker
                break

            # Fetch catalog for this portal (only once per portal)
            current_datasets = fetch_catalog(current_portal)
            if current_datasets is None:
                # Catalog failed — reset and let user pick another portal
                print("Try a different portal.\n")
                current_portal_key = None
                current_portal = None
                continue

            # Check for updates on previously-downloaded datasets from this portal
            updates = check_for_updates(current_datasets, current_portal_key)
            if updates:
                selected_updates = prompt_for_update_refresh(updates)
                if selected_updates:
                    print(f"\nRefreshing {len(selected_updates)} dataset(s)...\n")
                    for u in selected_updates:
                        record = u["record"]
                        current_ds = u["current_dataset"]
                        fmt = record.get("distribution_format")

                        dists = find_downloadable_distributions(current_ds, fmt)
                        if not dists:
                            print(f"  Could not find {fmt} version of {record['dataset_title']} — skipping")
                            continue

                        print(f"  {record['dataset_title']} ({fmt})")
                        download_distribution(dists[0], current_ds, current_portal_key)
                    print()

        # Keyword-search flow for the current portal
        keyword = input(f"Enter a keyword to search {current_portal['name']} (or 'quit' to exit): ").strip()
        if not keyword or keyword.lower() in ("quit", "exit", "q"):
            break

        matches = search_catalog(current_datasets, keyword)
        print(f"\nFound {len(matches)} datasets matching '{keyword}'.\n")

        if matches:
            selected = pick_datasets(matches)

            if selected:
                preferred_format = pick_formats(selected)
                if preferred_format == "CANCELLED":
                    pass  # User cancelled format picker — skip to "what next"
                else:
                    if preferred_format is None:
                        print("Downloading all available formats.\n")
                    else:
                        print(f"Downloading only {preferred_format} versions.\n")

                    downloaded = 0
                    no_data = 0

                    for i, ds in enumerate(selected, 1):
                        title = ds.get("title", "(untitled)")
                        modified = ds.get("modified", "")
                        modified_display = modified[:10] if modified else "unknown date"
                        print(f"[{i}] {title}  (source last updated: {modified_display})")

                        downloadables = find_downloadable_distributions(ds, preferred_format)
                        if not downloadables:
                            if preferred_format:
                                print(f"    (no {preferred_format} version available for this dataset)")
                                notifications.add(
                                    level=Notifications.LEVEL_INFO,
                                    category="no_format_available",
                                    subject=title,
                                    reason=f"No {preferred_format} version in this dataset's distributions",
                                    suggestion=f"Try 'All formats' instead, or check the dataset's landing page",
                                )
                            else:
                                print("    (no downloadable data — landing page only)")
                                notifications.add(
                                    level=Notifications.LEVEL_INFO,
                                    category="no_format_available",
                                    subject=title,
                                    reason="Dataset only offers a web-page landing link, no data files",
                                    suggestion="Check the source website for the actual data",
                                )
                            no_data += 1
                            continue

                        for dist in downloadables:
                            fmt = dist.get("format") or "unknown"
                            print(f"  Format: {fmt}")
                            if download_distribution(dist, ds, current_portal_key):
                                downloaded += 1

                    print(f"\n--- Session summary ---")
                    print(f"Portal:                            {current_portal['name']}")
                    print(f"Selected datasets:                 {len(selected)}")
                    print(f"Files downloaded:                  {downloaded}")
                    print(f"Datasets with no matching format:  {no_data}")

        # "What next?" prompt at the end of each cycle
        print()
        print("What would you like to do next?")
        print(f"  [1] Search {current_portal['name']} again")
        print("  [2] Pick a different portal")
        print("  [3] Quit")

        try:
            next_action = input("Your choice: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            break

        if next_action in ("3", "quit", "exit", "q"):
            break
        elif next_action == "2":
            current_portal_key = None
            current_portal = None
            current_datasets = None
        elif next_action == "1" or not next_action:
            pass  # continue with same portal
        else:
            print("Please pick 1, 2, or 3.\n")
            continue
        # Otherwise (including "1" or empty), just continue the loop
        # which loops back to the keyword search for the same portal

    print("\nExiting.")
    notifications.print_summary()


if __name__ == "__main__":
    main()
