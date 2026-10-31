ARG BASE_IMAGE=verge-browser-runtime-xvfb:latest
FROM ${BASE_IMAGE}

# Browser binaries are supplied separately; this image does not redistribute them.
COPY docker/camoufox-requirements.txt /opt/sandbox/camoufox-requirements.txt
RUN python3 -m venv /opt/sandbox/camoufox-venv && \
    /opt/sandbox/camoufox-venv/bin/pip install --no-cache-dir \
      -r /opt/sandbox/camoufox-requirements.txt
COPY apps/runtime-common/camoufox_*.py /opt/sandbox/camoufox/
COPY apps/runtime-xvfb/scripts/ /opt/sandbox/scripts/
COPY apps/runtime-xvfb/openbox/ /opt/sandbox/openbox/
COPY apps/runtime-xvfb/supervisor/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
LABEL io.verge.browser.engines="camoufox" io.verge.browser.launcher-version="1"
