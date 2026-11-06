#!/usr/bin/env bash
# Install the OPTIONAL external tools STEGO LAB integrates with.
# The app works without these; each unavailable tool is reported in the UI and
# its feature explains what to install. This script targets Debian/Ubuntu.
set -uo pipefail

echo "==> Installing optional external tools (Debian/Ubuntu)"
echo "    Requires sudo for apt and gem."

SUDO=""
[ "$(id -u)" -ne 0 ] && SUDO="sudo"

$SUDO apt-get update
# steghide, stegseek, outguess, exiftool, binwalk, tesseract, ffmpeg
$SUDO apt-get install -y --no-install-recommends \
  steghide stegseek outguess libimage-exiftool-perl binwalk tesseract-ocr ffmpeg ruby || true

# zsteg is a Ruby gem
if command -v gem >/dev/null 2>&1; then
  echo "==> Installing zsteg (Ruby gem)"
  $SUDO gem install zsteg || gem install --user-install zsteg || true
fi

echo
echo "==> Done. Verify from the backend venv:"
echo '    python -c "from app.core.tools import registry; [print(t[\"name\"], t[\"available\"]) for t in registry()]"'
