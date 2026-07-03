#!/data/data/com.termux/files/usr/bin/bash
set -e

APT_RETRY_OPTS="-o Acquire::Retries=5 -o Acquire::http::Timeout=60 -o Acquire::https::Timeout=60"

pkg update
apt $APT_RETRY_OPTS install -y x11-repo
apt $APT_RETRY_OPTS install -y python clang ffmpeg python-psutil python-lxml
python -m pip install --upgrade pip setuptools wheel
if ! command -v pip3 >/dev/null 2>&1; then
  ln -sf "$(command -v pip)" "$PREFIX/bin/pip3"
fi
apt $APT_RETRY_OPTS install -y chromium

pip install -r requirements-termux.txt
pip install DrissionPage --no-deps

python -c "import psutil, lxml, DrissionPage, pydub, speech_recognition; print('OK')"
