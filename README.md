# Open Source Research Data Tool
Web scrapes open city data portals for research purposes. 

# What is it?
This tool helps researchers work with datasets from open data portals without visiting each portal's website individually. It supports multiple BC municipal portals (Kelowna, Vancouver, Victoria, along with 
portals you add yourself), lets you search each portal's catalog by keyword, and allows you to pick which datasets and their formats to download. It detects new versions of datasets that have been updated at the source. It's designed to be a polite scraper. has built-in rate limits along with robot.txt for ethical purposes and user identification. 


# Who is it for?
This tool is designed for:
- Researchers who need repeatable data pulls from open data portals
- Research assistants doing regular refreshes as new data publishes
- Anyone working with open data catalogs

## Quick Start

###Requirements
- Python 3.9 or later
- No external packages required (uses only the standard library)

### Installation
Download 'publicdata.py' onto your device; no other extra dependencies are needed.

###First 


2. Run publicdata.py on your device (can be through an IDE for Python, or simply the command line)
3. Follow the options after the tool runs

Example:
Downloaded datasets need a folder to save into.
Default location: C:\Users\ethan\OneDrive\Desktop\open-data-downloads

Would you like to configure a permanent folder for future runs?
  y = yes, ask me where and remember it
  n = no, just use the default for this run only
  Enter = same as 'n'
Configure permanent folder? [y/N]: n
Using C:\Users\ethan\OneDrive\Desktop\open-data-downloads for this run only.
(You'll be asked again next time you run the tool.)

Files will be saved to: C:\Users\ethan\OneDrive\Desktop\open-data-downloads


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


# Multiple Users
The tool is designed for individual use, one user at a time on their own machine. Each user's configuration, portal list, and download history are stored in files in their home directory; users on different machines or with different logins don't interfere with each other. This tool does not handle simultaneous access from multiple users to the same config files or download folder. If you are running the in a shared environment, give each user their own login or at least their own download folder to avoid conflicts. 
