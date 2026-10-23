FROM ubuntu@sha256:c098726dd9b9733f3e885f8de0ef375206a311b0a317eadc40d347b1115fb944

COPY dependencies.lock /tmp/dependencies.lock
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive xargs apt-get install --no-install-recommends -y < /tmp/dependencies.lock \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /source
