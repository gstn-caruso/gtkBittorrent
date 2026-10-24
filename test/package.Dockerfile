FROM ubuntu:26.04
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates xvfb xauth dbus-x11 fontconfig fonts-cantarell xdg-utils desktop-file-utils \
    && rm -rf /var/lib/apt/lists/*
COPY dist/ /artifacts/
COPY test/package-smoke.sh /package-smoke.sh
CMD ["sh", "/package-smoke.sh"]
