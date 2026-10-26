#!/bin/bash
# macOS / Linux version of start-website.bat.
#
# macOS: double-click this file in Finder and it opens in Terminal.
#        If it opens in a text editor instead, run this once:
#            chmod +x start-website.command
# Linux: run ./start-website.command from a terminal.
#
# Close the Terminal window (or press Ctrl+C) to stop the website.

# Work from the folder this script lives in, whatever the shell's cwd is
cd "$(dirname "$0")" || exit 1

if [ ! -f "webapp/server.py" ] || [ ! -f "publicdata.py" ]; then
    echo
    echo "This file is in the wrong place, or some files are missing."
    echo
    echo "Expected next to this file:"
    echo "   publicdata.py"
    echo "   webapp/server.py"
    echo "   webapp/index.html"
    echo
    read -r -p "Press Return to close."
    exit 1
fi

# Find a working Python 3. macOS has shipped no "python" since 12.3, and on
# some systems "python" is still Python 2, so python3 is tried first. Each
# candidate is actually run rather than merely located.
PY=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 \
       && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info[0] == 3 else 1)' >/dev/null 2>&1; then
        PY="$candidate"
        break
    fi
done

if [ -z "$PY" ]; then
    echo
    echo "Python 3 was not found on this computer."
    echo
    echo "macOS: install it with  brew install python3"
    echo "       or download it from https://www.python.org/downloads/"
    echo "Linux: install it with  sudo apt install python3"
    echo
    read -r -p "Press Return to close."
    exit 1
fi

# server.py picks a free port and opens the browser itself
"$PY" webapp/server.py

echo
echo "The website has stopped."
read -r -p "Press Return to close."
