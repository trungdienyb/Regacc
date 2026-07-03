#!/data/data/com.termux/files/usr/bin/bash
set -u

APT_RETRY_OPTS="-o Acquire::Retries=10 -o Acquire::http::Timeout=120 -o Acquire::https::Timeout=120"
TERMUX_PREFIX="${PREFIX:-}"
X11_LIST="$TERMUX_PREFIX/etc/apt/sources.list.d/x11.list"

log() {
  printf '\n[install] %s\n' "$1"
}

run_apt() {
  apt $APT_RETRY_OPTS "$@"
}

ensure_pip3_command() {
  if command -v pip3 >/dev/null 2>&1; then
    return 0
  fi

  if command -v pip >/dev/null 2>&1; then
    ln -sf "$(command -v pip)" "$TERMUX_PREFIX/bin/pip3"
    return 0
  fi

  if python -m pip --version >/dev/null 2>&1; then
    cat > "$TERMUX_PREFIX/bin/pip3" <<'EOF'
#!/data/data/com.termux/files/usr/bin/sh
exec python -m pip "$@"
EOF
    chmod +x "$TERMUX_PREFIX/bin/pip3"
    return 0
  fi

  return 1
}

create_temporary_pip3_shim() {
  if command -v pip3 >/dev/null 2>&1; then
    return 0
  fi

  log "Tạo pip3 tạm để gỡ trạng thái dpkg đang kẹt."
  cat > "$TERMUX_PREFIX/bin/pip3" <<'EOF'
#!/data/data/com.termux/files/usr/bin/sh
echo "temporary pip3 shim for dpkg repair; python-pip will be installed next" >&2
exit 0
EOF
  chmod +x "$TERMUX_PREFIX/bin/pip3"
}

repair_dpkg_state() {
  log "Sửa trạng thái dpkg/apt nếu có package đang cài dở."
  dpkg --configure -a && return 0

  create_temporary_pip3_shim
  dpkg --configure -a || true
  run_apt --fix-broken install -y || true
}

configure_x11_repo() {
  log "Đảm bảo X11 repo dùng mirror Grimler ổn định cho Chromium."
  mkdir -p "$TERMUX_PREFIX/etc/apt/sources.list.d"
  cat > "$X11_LIST" <<'EOF'
deb https://www.grimler.se/termux-x11 x11 main
EOF
}

install_base_packages() {
  log "Cập nhật apt index."
  run_apt update

  log "Cài package nền tảng và pip của Termux."
  run_apt install -y x11-repo python python-pip clang ffmpeg python-psutil python-lxml

  if command -v pip >/dev/null 2>&1; then
    ln -sf "$(command -v pip)" "$TERMUX_PREFIX/bin/pip3"
  fi

  ensure_pip3_command || {
    echo "Không tạo được pip3. Hãy chạy: apt install python-pip" >&2
    exit 1
  }
}

install_chromium() {
  log "Cài Chromium từ X11 repo."
  run_apt install -y chromium || {
    log "Cài Chromium lỗi, thử sửa dpkg rồi cài lại."
    repair_dpkg_state
    run_apt install -y chromium
  }

  repair_dpkg_state

  if command -v chromium-browser >/dev/null 2>&1; then
    chromium-browser --version
  elif command -v chromium >/dev/null 2>&1; then
    chromium --version
  else
    echo "Không tìm thấy chromium-browser/chromium sau khi cài." >&2
    exit 1
  fi
}

install_python_packages() {
  log "Cài Python dependencies không build lại psutil/lxml từ PyPI."
  pip install -r requirements-termux.txt
  pip install DrissionPage --no-deps

  python -c "import psutil, lxml, DrissionPage, pydub, speech_recognition; print('Python deps OK')"
}

main() {
  if [ -z "$TERMUX_PREFIX" ]; then
    echo "Script này cần chạy trong Termux." >&2
    exit 1
  fi

  configure_x11_repo
  repair_dpkg_state
  install_base_packages
  repair_dpkg_state
  install_chromium
  install_python_packages

  log "Hoàn tất. Chạy:"
  if command -v chromium-browser >/dev/null 2>&1; then
    echo 'python reg_accTTC.py -t 1 --browser-path "$(which chromium-browser)"'
  else
    echo 'python reg_accTTC.py -t 1 --browser-path "$(which chromium)"'
  fi
}

main "$@"
