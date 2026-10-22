# Open Source Research Data Tool
Search and download from open data portals by their DCAT catalogs

## What is it?
This tool helps researchers work with datasets from open data portals without visiting each portal's website individually. It supports multiple BC municipal portals (Kelowna, Vancouver, Victoria and Burnaby) plus any portals you add yourself, lets you search each portal's catalogue by keyword, and allows you to pick which datasets and their formats to download. It detects new versions of datasets that have been updated at the source. It's designed to be a polite scraper, with built-in rate limits, robots.txt checks, and transparent user identification. 


## Who is it for?
This tool is designed for:
- Researchers who need repeatable data pulls from open data portals
- Research assistants doing regular refreshes as new data is published
- Anyone working with open data catalogs

## Quick Start

### Requirements
- Python 3.9 or later
- No external packages required (uses only the standard library)

### Installation
Download the repository (Code → Download ZIP, then unzip), or clone it.

To use the command-line tool only, `publicdata.py` on its own is enough.
To use the web interface as well, keep the folder layout intact:

```
publicdata.py
start-website.bat
webapp/
    server.py
    index.html
```

`server.py` looks for `publicdata.py` in the folder above it, and
`start-website.bat` looks for `webapp/`. Moving files out of this layout will
stop the website from starting.

No external packages are needed; the tool uses only Python standard library.



### First run
Open a terminal, navigate to the folder containing `publicdata.py`, and run:
**Windows Powershell:**
```
python publicdata.py
```
**Mac OS / linux:**
```
python3 publicdata.py
```
Example:
```
Downloaded datasets need a folder to save into.
Default location: 

Would you like to configure a permanent folder for future runs?
  y = yes, ask me where and remember it
  n = no, just use the default for this run only
  Enter = same as 'n'
Configure permanent folder? [y/N]: n
Using  for this run only.
(You'll be asked again next time you run the tool.)

Files will be saved to: 


--- Contact info ---
This tool identifies itself to open data portals via a User-Agent
string that includes your contact info. This is polite practice —
it lets portal operators reach you if something looks wrong.

Suggested: your email address, or a URL where you can be reached.
If you skip, a generic 'unknown-user' will be used, but this may
be flagged as suspicious by some portals.

Contact info (email or URL, or press Enter to skip): 

Available open data portals:

British Columbia:
  [1] City of Burnaby  (built-in)
  [2] City of Kelowna  (built-in)
  [3] City of Vancouver  (built-in)
  [4] City of Victoria  (built-in)

  [5] Add a new portal...
  [6] Delete a user-added portal...
  Type 'quit' or press Ctrl+C to exit.

Pick a portal: 

Pick a portal: 1
Fetching catalog for City of Burnaby...
  (https://data.burnaby.ca/api/feed/dcat-us/1.1.json)
Catalog contains 74 datasets.

Enter a keyword to search City of Burnaby (or 'quit' to exit): roads

Found 7 datasets matching 'roads'.

Datasets found:

  [ 1] Street
       Available: CSV, GEOJSON, KML, ZIP
  [ 2] Ditch
       Available: CSV, GEOJSON, KML, ZIP
  [ 3] Lane
       Available: CSV, GEOJSON, KML, ZIP
  [ 4] Legal Right Of Way
       Available: CSV, GEOJSON, KML, ZIP
  [ 5] Street Light
       Available: CSV, GEOJSON, KML, ZIP
  [ 6] Traffic Calming Features
       Available: CSV, GEOJSON, KML, ZIP
  [ 7] Traffic Signals
       Available: CSV, GEOJSON, KML, ZIP

Pick datasets to download:
  Examples: 1,3,5  |  1-4  |  1,3-7,10  |  all
  Type 'quit' or press Ctrl+C to exit.
Your pick: 1

Selected 1 dataset(s).

Available formats:
  [1] CSV  (available in 1/1 dataset(s))
  [2] GEOJSON  (available in 1/1 dataset(s))
  [3] KML  (available in 1/1 dataset(s))
  [4] ZIP  (available in 1/1 dataset(s))
  [5] All formats (download every available version)
Pick a format number: 1
Downloading only CSV versions.

[1] Street
  Format: CSV
    Downloading: https://data.burnaby.ca/api/download/v1/items/18cb9099908640c68910b76033309d75/csv?layers=8
    Saving as:   Street.csv
    Done (845.4 KB)

--- Summary ---
Portal:                            City of Burnaby
Selected datasets:                 1
Files downloaded:                  1
Datasets with no matching format:  0
No issues encountered this session.
```
##Running the web interface
As well as the terminal version, the tool has a local web interface with the same features: browsing portals, searching, picking formats, downloading and viewing history.

## Running with Docker

Docker runs the web interface in a container, which works the same way on
Windows, macOS and Linux. Python does not need to be installed.

From the project folder:

```
docker compose up --build
```

Then open <http://localhost:8000>. Press Ctrl+C, or run `docker compose down`,
to stop it.

Downloaded files appear in a `downloads` folder next to the Dockerfile.
Settings, your portal list and download history are kept in a Docker volume,
so they survive restarts.

Before real use, set your contact address in `docker-compose.yml`:

```
environment:
  OPENDATA_CONTACT: "you@example.com"
```

Portals see this in the User-Agent. Left as `unknown-user`, some portals are
more likely to block the requests.

### Notes

- If port 8000 is already in use, change the first number only, for example
  `"8080:8000"`.
- The container listens on all interfaces inside its own network namespace,
  which is why `OPENDATA_HOST=0.0.0.0` is set in the Dockerfile. The container
  boundary provides the isolation that binding to localhost provides when
  running directly.
- The command-line tool also runs in the container, with an interactive
  terminal:

```
docker run --rm -it -v "%cd%/downloads:/data" opendata-explorer python publicdata.py
```

## How it works
1. Choose a portal from the built-in list, or add your own
2. The tool fetches the portal's dataset catalog
3. If you've downloaded from this portal before, the tool checks for updates and offers to refresh them
4. Enter a search keyword
5. Review matching datasets and pick which ones to download
6. Pick a format (CSV, GeoJSON, etc.) or "all formats"
7. Files download to your configured folder
8. Summary shows what worked, what didn't and why

## Detailed Features

Each subsection below describes one feature of the tool. 

### Multi-portal support

The tool ships with four built-in BC city portals: Kelowna, Vancouver, Victoria, and Burnaby. You can add your own by providing a portal name, its DCAT catalog url and the province it's in.
User-added portals are grouped by province in the picker for easy navigation.

Portal choices are saved to `~/.publicdataportals.json` and persist over runs. Built-in portals can't be deleted, but user-added ones can be removed 
using the "Delete a user-added portal" option in the picker menu.

### Adding another city's portal

The four built-in portals are a starting point, not a limit. Any ArcGIS Hub
portal that publishes a DCAT feed can be added.

#### Adding one

**In the web interface:** open **Add a portal** in the left sidebar, fill in
the form, and click **Add portal**.

**In the command-line tool:** at the portal list, choose **[5] Add a new
portal**, then answer the prompts.

Either way you supply:

| Field | Meaning | Example |
|-------|---------|---------|
| Short key | lowercase, no spaces; used internally and to prefix filenames | `newwest` |
| Display name | what you see in the list | `City of New Westminster` |
| Catalog URL | the DCAT feed (see below) | `https://opendata.newwestcity.ca/api/feed/dcat-us/1.1.json` |
| Homepage | optional, a link shown next to the portal | `https://opendata.newwestcity.ca` |
| Province | groups the list; anything you like | `British Columbia` |

Portals you add are saved to `~/.publicdataportals.json` and appear on every
later run, marked *user-added*. Built-in portals cannot be deleted; your own
can, with **[6] Delete a user-added portal** or the **×** beside its name in
the web interface.

#### Finding the catalog URL

Start from the portal's home page and try these two addresses:

```
{homepage}/api/feed/dcat-us/1.1.json
{homepage}/data.json
```

Open each in a browser. The one that works returns JSON containing a
`"dataset"` array. That is the URL to paste in.

#### Check it before adding

A feed that loads is not necessarily a feed you can download from. Two things
to look for in the JSON:

1. A `"dataset"` array with a sensible number of entries.
2. Inside a dataset, a `"distribution"` list whose entries have a `"format"`
   such as `CSV`, `GeoJSON`, `KML` or `ZIP`.

If the distributions have no `"format"`, the portal is probably running
Socrata or CKAN rather than ArcGIS Hub. The catalog will load and datasets
will appear, but the format picker will show "(no format)" for everything and
the Shapefile option will find nothing. Support for those portal types is
planned; see Known Limitations.

#### A worked example

City of New Westminster publishes an ArcGIS Hub feed:

```
Short key    : newwest
Display name : City of New Westminster
Catalog URL  : https://opendata.newwestcity.ca/api/feed/dcat-us/1.1.json
Homepage     : https://opendata.newwestcity.ca
Province     : British Columbia
```

That gives 169 datasets, 96 of them with downloadable files in CSV, GeoJSON,
KML and ZIP — and all 96 offer shapefiles.

#### When it does not work

| What you see | What it means |
|--------------|---------------|
| `HTTP Error 404` on both addresses | Not an ArcGIS Hub portal. It may be CKAN or Socrata, which are not supported yet. |
| `getaddrinfo failed` / cannot resolve | The address does not exist. Find the real one from the city's own website rather than guessing. |
| `CERTIFICATE_VERIFY_FAILED` | The portal's HTTPS certificate is not valid. Nothing this tool can fix; report it to the portal operator. |
| Feed loads, but every format shows "(no format)" | A DCAT feed from a non-ArcGIS portal. Datasets list, but format picking will not work properly. |
| `Portal type '...' is not yet supported` | The saved entry has a type other than `arcgis_hub`. |

Guessing addresses rarely works — of ten BC and Canadian portals tried by
guesswork, only one had a usable feed at a guessed address. Start from the
city's open data page and look for an API, Developers or Download link.

### Keyword Search

Enter a search term after selecting a portal, and the tool filters the catalog to datasets whose title, description, or tags contain that keyword. Matching is case-insensitive and works on partial words. 
Example:
```
Enter a keyword to search City of Burnaby (or 'quit' to exit): roads

Found 7 datasets matching 'roads'.
```

### Interactive dataset and format picking
After search results appear, the tool asks you to pick which datasets to download. You can pick individual datasets like (`1,3,5`), ranges (`1-4`), combinations (`1- 3,7,10 `), or all.
Once you pick the datasets, the tool shows you which formats are available to download across all your picks. 
Note: some formats may be available for some datasets and not for others

### Choosing a format: shapefiles vs CSV

The format list offers **Shapefile** first where it is available. It is worth
understanding what the choice costs.

CSV drops the map geometry. Exporting a polygon layer to CSV keeps the
attributes and a `SHAPESTArea` figure, but not the outline itself — so you can
tell how large each feature is, but not where it is or what shape it has. For
point datasets CSV keeps the X/Y coordinates, so less is lost.

Shapefile and GeoJSON both preserve the geometry:

| Format | Geometry | Coordinate system |
|--------|----------|-------------------|
| CSV | lost for lines and polygons | n/a |
| GeoJSON | yes | always WGS84 |
| Shapefile | yes | the portal's own, recorded in the `.prj` file |

A shapefile arrives as a `.zip` containing `.shp`, `.shx`, `.dbf` and `.prj`.
That is normal — the parts belong together and GIS software opens the set.

**Why "Shapefile" and not "SHP":** portals disagree on the label. Vancouver
calls it `SHP`; Kelowna, Victoria and Burnaby call the identical bundle `ZIP`.
Picking `SHP` would therefore return nothing on three of the four portals, so
the tool offers a single "Shapefile" choice that matches either label.

Those same portals also publish a File Geodatabase under the `ZIP` label. The
tool tells the two apart and downloads only the shapefile.

### Update detection
Every download is recorded to `~/.publicdatahistory.json` along with the source's "last modified" timestamp at the time of download. When you run the tool again with the same portal, it compares your local records to the current catalog. If any dataset has been updated at the source since your last download, you're shown a list and asked whether to refresh.

**Example:**
```
2 previously-downloaded dataset(s) have been updated:

  [ 1] Park Baseball Dugout
       Format: CSV
       Was: 2026-07-18  →  Now: 2026-07-20
  [ 2] Park Activity
       Format: CSV
       Was: 2026-07-18  →  Now: 2026-07-20

Re-download updated datasets?
  Examples: 1,3,5  |  all  |  none
  Type 'quit' or press Ctrl+C to skip and continue.
Your pick: 1

Refreshing 1 dataset(s)...

  Park Baseball Dugout (CSV)
    Downloading: https://opendata.medicinehat.ca/api/download/v1/items/...
    Saving as:   Park_Baseball_Dugout.csv
    Done (3.2 KB)
```

### Ethical Scraping
The tool follows several conventions for well-behaved automated access to public data:
- Rate limiting: 1.5 seconds between requests to the same domain
- robots.txt: checked before every download
- User-Agent: identifies the tool with contact info
- Size confirmation: prompts before files over 100 MB

### Structured notifications
During a run, the tool records any download failures, robots.txt refusals, missing format warnings, and size-skip decisions. At the end of the session, these are printed as a grouped summary rather than scattered through the download output.

Example:
```
--- Summary ---
Portal:                            City of Kelowna
Selected datasets:                 6
Files downloaded:                  4
Datasets with no matching format:  2

--- Notifications ---

Datasets without the requested format (2):
  • Transportation
    Reason: No CSV version in this dataset's distributions
    Suggestion: Try 'All formats' instead, or check the dataset's landing page
  • MMCD infrastructure data standards and Civil 3D template
    Reason: No CSV version in this dataset's distributions
    Suggestion: Try 'All formats' instead, or check the dataset's landing page
```
    
### Download history
Every download is recorded to `~/.publicdatahistory.json`. Each entry includes:
- which portal it came from
- Dataset title and format
- Source URL and local file path
- the source's "last modified" timestamp at the time of download
- your local download timestamp
The history file is what powers update detection; the tool uses it to compare your local record against the current portal catalog

To view the file directly:
**Windows PowerShell:** 
```
Get-Content $env:USERPROFILE\.publicdatahistory.json
```
**macOS / Linux:** 
```
cat ~/.publicdatahistory.json
```
## Files created

The tool creates three files in your home directory to remember your 
preferences and history across runs:

| File | Purpose |
|------|---------|
| `~/.publicdataconfig.json` | Download folder path and contact info |
| `~/.publicdataportals.json` | User-added portals |
| `~/.publicdatahistory.json` | Download history (for update detection) |

To reset any of these, delete the file. See Troubleshooting for 
platform-specific commands.

**Note:** These files start with `.` and are hidden by default on both 
Windows and macOS. On Windows, enable "Hidden items" in File Explorer's 
View menu to see them. On macOS, press `Cmd+Shift+.` in Finder.

## Troubleshooting

### "The filename, directory name, or volume label syntax is incorrect"

This happens when the folder path is pasted with surrounding quotation 
marks. Windows "Copy as path" does this automatically. Recent versions 
of the tool strip these quotes automatically; if you still see this 
error, manually remove the `"` characters from your pasted path.

### Resetting the download folder or contact info

Delete the config file. The next run will treat you as a first-time user 
and prompt for these again.

**Windows (PowerShell):**
```
Remove-Item $env:USERPROFILE\.publicdataconfig.json
```
**macOS / Linux:**
```
rm ~/.publicdataconfig.json
```

## Multiple Users
The tool is designed for individual use, one user at a time on their own machine. Each user's configuration, portal list, and download history are stored in files in their home directory; users on different machines or with different logins don't interfere with each other. This tool does not handle simultaneous access from multiple users to the same config files or download folder. If you are running it in a shared environment, give each user their own login or at least their own download folder to avoid conflicts. 

## Known Limitations

**Portal types**
- Only ArcGIS Hub portals (with a DCAT feed) are supported. CKAN and Socrata
  portals are not.
- Because there is no CKAN support, the Province of BC catalogue
  (catalogue.data.gov.bc.ca) cannot be used yet.

**Platforms**
- The one-click `start-website.bat` is Windows-only. macOS and Linux users can
  run `python3 webapp/server.py` directly, or use Docker.
- Tested on Windows. The code uses no platform-specific calls, so it should
  work on macOS and Linux, but this has not been confirmed on those systems.
- On macOS, if every portal fetch fails with a certificate error, run
  `Install Certificates.command` from your `/Applications/Python 3.x/` folder.
  This is a known macOS Python issue, not a problem with this tool.

**Scope**
- The web interface runs locally and is not reachable from other devices.
- Downloads are whole files; rows and columns cannot be filtered beforehand.
- One user at a time per machine (see Multiple Users above).

## Development notes

Parts of this tool, particularly the local web interface and the Docker setup,
were written with AI assistance (Claude). All code has been reviewed and tested
by the author.

## License 

## Data sources

This tool downloads from publicly published open data catalogues:

| Portal | Catalogue |
|--------|-----------|
| City of Kelowna | opendata.kelowna.ca |
| City of Vancouver | opendata.vancouver.ca |
| City of Victoria | opendata.victoria.ca |
| City of Burnaby | data.burnaby.ca |

The tool reads each portal's published DCAT catalogue; it does not scrape web
pages. It identifies itself with a contact address, honours `robots.txt`, and
waits 1.5 seconds between requests to the same site.

Each portal licenses its data under its own terms. You are responsible for
checking and following the licence of any dataset you download. This tool's
licence covers the tool itself, not the data it retrieves.
