FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    DISPLAY=:99 \
    XVFB_WHD=1280x1024x24 \
    BROWSER_REMOTE_DEBUGGING_PORT=9222 \
    EXPOSED_CDP_PORT=9223 \
    VNC_SERVER_PORT=5900 \
    WEBSOCKET_PROXY_PORT=6080 \
    BROWSER_WINDOW_WIDTH=1280 \
    BROWSER_WINDOW_HEIGHT=1024 \
    BROWSER_DOWNLOAD_DIR=/workspace/downloads \
    BROWSER_USER_DATA_DIR=/workspace/browser-profile \
    DEFAULT_URL=about:blank

RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    xvfb \
    openbox \
    x11vnc \
    novnc \
    websockify \
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
    && (find /usr/lib -name gtk-query-immodules-3.0 -exec {} --update-cache \; || true) \
    && rm -rf /var/lib/apt/lists/*

ENV XMODIFIERS="@im=fcitx" \
    GTK_IM_MODULE="fcitx" \
    QT_IM_MODULE="fcitx" \
    LC_ALL=zh_CN.UTF-8 \
    LANG=zh_CN.UTF-8

RUN mkdir -p /workspace/downloads /workspace/uploads /workspace/browser-profile /var/log/sandbox /run/sandbox /opt/sandbox/scripts /root/.config/fcitx

COPY apps/runtime-xvfb/scripts/ /opt/sandbox/scripts/
COPY apps/runtime-xvfb/openbox/ /opt/sandbox/openbox/
COPY apps/runtime-xvfb/supervisor/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY apps/runtime-xvfb/fcitx/profile5 /root/.config/fcitx5/profile_src
RUN mkdir -p /root/.config/fcitx5

RUN chmod +x /opt/sandbox/scripts/*.sh

RUN fc-cache -f

EXPOSE 9223 5900 6080

CMD ["/bin/bash", "/opt/sandbox/scripts/start_all.sh"]
