FROM python:3.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    DISPLAY=:100 \
    XPRA_DISPLAY=:100 \
    XPRA_BIND_HOST=0.0.0.0 \
    XPRA_PORT=14500 \
    XPRA_HTML5=on \
    BROWSER_REMOTE_DEBUGGING_PORT=9222 \
    EXPOSED_CDP_PORT=9223 \
    BROWSER_WINDOW_WIDTH=1280 \
    BROWSER_WINDOW_HEIGHT=1024 \
    BROWSER_DOWNLOAD_DIR=/workspace/downloads \
    BROWSER_USER_DATA_DIR=/workspace/browser-profile \
    DEFAULT_URL=about:blank

RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    xpra \
    libjs-jquery \
    python3-pil \
    openbox \
    socat \
    xdotool \
    wmctrl \
    x11-utils \
    imagemagick \
    curl \
    supervisor \
    fonts-noto-core \
    fonts-noto-cjk \
    fonts-noto-color-emoji \
    fonts-liberation \
    fontconfig \
    libfontconfig1 \
    fcitx5 \
    fcitx5-chinese-addons \
    fcitx5-frontend-gtk2 \
    fcitx5-frontend-gtk3 \
    fcitx5-frontend-qt5 \
    dbus-x11 \
    locales \
    && echo "zh_CN.UTF-8 UTF-8" > /etc/locale.gen \
    && locale-gen \
    && find /usr/lib -name gtk-query-immodules-3.0 -exec {} --update-cache \; || true \
    && rm -rf /var/lib/apt/lists/*

ENV XMODIFIERS="@im=fcitx" \
    GTK_IM_MODULE="fcitx" \
    QT_IM_MODULE="fcitx" \
    LC_ALL=zh_CN.UTF-8 \
    LANG=zh_CN.UTF-8

RUN mkdir -p /workspace/downloads /workspace/uploads /workspace/browser-profile /var/log/sandbox /run/sandbox /opt/sandbox/scripts /root/.config/fcitx

COPY apps/runtime-xpra/scripts/ /opt/sandbox/scripts/
COPY apps/runtime-xpra/openbox/ /opt/sandbox/openbox/
COPY apps/runtime-xpra/supervisor/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY apps/runtime-xpra/fcitx/profile5 /root/.config/fcitx5/profile_src
RUN mkdir -p /root/.config/fcitx5

RUN chmod +x /opt/sandbox/scripts/*.sh

RUN fc-cache -f

EXPOSE 9223 14500

CMD ["/bin/bash", "/opt/sandbox/scripts/start_all.sh"]
