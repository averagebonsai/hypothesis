# Authoring image only. The offline validation worker remains separate.
ARG TOOLKIT_IMAGE=hypothesis-worker:prepared
FROM ${TOOLKIT_IMAGE}
USER 0:0
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends git ripgrep ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN --mount=type=cache,target=/var/cache/muse python /opt/toolkit/docker/install_muse.py && muse --version
# Framework regression fixtures are for the validator, not authoring context.
RUN rm -rf /opt/toolkit/tests
ENV MUSE_NO_AUTO_UPDATE=1 \
    HOME=/tmp/muse-home \
    XDG_CONFIG_HOME=/tmp/muse-home/.config \
    XDG_CACHE_HOME=/tmp/muse-home/.cache
USER 10001:10001
WORKDIR /workspace
ENTRYPOINT ["muse"]
