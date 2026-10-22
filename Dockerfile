# Open Data Explorer — the web interface, in a container.
#
# Build:  docker build -t opendata-explorer .
# Run:    docker run --rm -p 8000:8000 -v "%cd%/downloads:/data" opendata-explorer
#         (on macOS/Linux use "$(pwd)/downloads:/data")
# Then open http://localhost:8000
#
# The command-line tool works too, but needs an interactive terminal:
#         docker run --rm -it -v "%cd%/downloads:/data" opendata-explorer \
#                python publicdata.py

FROM python:3.12-slim

# The tool uses only the Python standard library, so there is nothing to pip
# install. That is also why there is no requirements.txt step here.

WORKDIR /app

COPY publicdata.py ./
COPY webapp/ ./webapp/
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

# Run as a normal user rather than root, and give it the two writable paths.
#   /config  the .publicdata*.json settings, portal list and download history
#   /data    the downloaded files
RUN useradd --create-home --uid 1000 app \
 && mkdir -p /config /data \
 && chown -R app:app /config /data /app \
 && chmod +x /usr/local/bin/docker-entrypoint.sh

ENV HOME=/config \
    OPENDATA_HOST=0.0.0.0 \
    PYTHONUNBUFFERED=1

# HOME=/config is what puts the settings files on a volume: the tool builds
# their paths from Path.home(), which follows $HOME.
#
# OPENDATA_HOST=0.0.0.0 is required. The server binds the loopback by default,
# but a container's loopback is its own, so a published port would reach
# nothing. Inside a container the container boundary provides the isolation
# that binding to 127.0.0.1 provides on a normal machine.

USER app

VOLUME ["/config", "/data"]
EXPOSE 8000

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "webapp/server.py", "--no-browser"]
