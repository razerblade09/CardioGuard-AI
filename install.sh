#!/usr/bin/env bash
#
# CardioGuard AI — Automated Setup (macOS / Linux)
# ================================================
# Creates the Python virtual environment, installs backend dependencies,
# generates config files from their templates, and installs the dashboard's
# npm packages.
#
# Usage:
#   bash install.sh                   # full setup
#   bash install.sh --skip-dashboard  # backend only
#   bash install.sh --skip-backend    # dashboard only
#
# The script never overwrites an existing config file.

set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

SKIP_BACKEND=0
SKIP_DASHBOARD=0
for arg in "$@"; do
    case "$arg" in
        --skip-backend)   SKIP_BACKEND=1 ;;
        --skip-dashboard) SKIP_DASHBOARD=1 ;;
        -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
        *) echo "Unknown option: $arg" >&2; exit 1 ;;
    esac
done

C_CYAN='\033[36m'; C_GREEN='\033[32m'; C_YELLOW='\033[33m'
C_RED='\033[31m';  C_GREY='\033[90m';  C_OFF='\033[0m'

WARNINGS=()
TODO=()

step() { printf "\n${C_CYAN}==> %s${C_OFF}\n" "$1"; }
ok()   { printf "    ${C_GREEN}[ok]${C_OFF}   %s\n" "$1"; }
info() { printf "    ${C_GREY}%s${C_OFF}\n" "$1"; }
warn() { printf "    ${C_YELLOW}[warn] %s${C_OFF}\n" "$1"; WARNINGS+=("$1"); }
fail() { printf "    ${C_RED}[fail] %s${C_OFF}\n" "$1"; exit 1; }
todo() { TODO+=("$1"); }
have() { command -v "$1" >/dev/null 2>&1; }

echo
echo "  CardioGuard AI - Setup"
echo "  ======================"
printf "  ${C_GREY}%s${C_OFF}\n" "$ROOT"

# ─── 1. Prerequisites ────────────────────────────────────────────────────────
step "Checking prerequisites"

# Probe each candidate: a name on PATH is not enough — Windows ships a
# Microsoft Store stub named python3 that resolves but reports no version.
PY=""
PY_VERSION=""
for candidate in python3.12 python3 python; do
    have "$candidate" || continue
    probe="$($candidate --version 2>&1)"
    case "$probe" in
        Python\ 3.*) PY="$candidate"; PY_VERSION="${probe#Python }"; break ;;
    esac
done
[ -n "$PY" ] || fail "A working Python 3 interpreter was not found. Install Python 3.12 and re-run."

PY_MAJOR="${PY_VERSION%%.*}"
PY_REST="${PY_VERSION#*.}"
PY_MINOR="${PY_REST%%.*}"
ok "Python $PY_VERSION ($PY)"

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    fail "Python 3.10 or newer is required (3.12 recommended)."
fi
if [ "$PY_MINOR" -ne 12 ]; then
    warn "Project targets Python 3.12; you have $PY_VERSION. Pinned wheels may not resolve."
fi

if have node; then
    ok "Node $(node --version)"
else
    warn "Node.js not found - the dashboard cannot be installed or run."
    SKIP_DASHBOARD=1
    todo "Install Node.js 18 LTS or newer from https://nodejs.org, then re-run: bash install.sh --skip-backend"
fi

have git && ok "Git $(git --version | sed 's/git version //')"

# ─── 2. Python environment ───────────────────────────────────────────────────
if [ "$SKIP_BACKEND" -eq 0 ]; then
    step "Setting up the Python environment"

    if [ -d ".venv" ]; then
        info ".venv already exists - reusing it"
    else
        info "Creating .venv ..."
        "$PY" -m venv .venv || fail "Could not create the virtual environment (is python3-venv installed?)"
        ok "Virtual environment created"
    fi

    VENV_PY="$ROOT/.venv/bin/python"
    [ -x "$VENV_PY" ] || fail ".venv/bin/python is missing - delete .venv and re-run this script."

    info "Upgrading pip ..."
    "$VENV_PY" -m pip install --upgrade pip --quiet
    info "Installing backend dependencies (this can take a few minutes) ..."
    if "$VENV_PY" -m pip install -r requirements.txt --quiet; then
        ok "Backend dependencies installed"
    else
        warn "pip reported errors - review the output above."
    fi
fi

# ─── 3. Config files from templates ──────────────────────────────────────────
step "Preparing configuration files"

FW_EXAMPLE="firmware/cardioguard/config.h.example"
FW_CONFIG="firmware/cardioguard/config.h"
if [ -f "$FW_CONFIG" ]; then
    info "$FW_CONFIG already exists - left untouched"
elif [ -f "$FW_EXAMPLE" ]; then
    cp "$FW_EXAMPLE" "$FW_CONFIG"
    ok "Created $FW_CONFIG from the template"
    todo "Edit $FW_CONFIG - Wi-Fi SSID/password (2.4 GHz only), CLOUD_API_URL, PATIENT_ID, DEVICE_ID, GOOGLE_GEO_KEY"
else
    warn "$FW_EXAMPLE not found - cannot generate the firmware config"
fi

ENV_EXAMPLE="dashboard/.env.local.example"
ENV_LOCAL="dashboard/.env.local"
if [ -f "$ENV_LOCAL" ]; then
    info "$ENV_LOCAL already exists - left untouched"
elif [ -f "$ENV_EXAMPLE" ]; then
    cp "$ENV_EXAMPLE" "$ENV_LOCAL"
    ok "Created $ENV_LOCAL from the template"
    todo "Edit $ENV_LOCAL - paste the Firebase web config (all VITE_* values)"
else
    warn "$ENV_EXAMPLE not found - cannot generate the dashboard env file"
fi

if [ -f "firebase_credentials.json" ]; then
    ok "firebase_credentials.json present"
else
    warn "firebase_credentials.json is missing - Firebase logging will be disabled"
    todo "Download the service-account key: Firebase Console > Project settings > Service accounts > Generate new private key, then save it to the project root as firebase_credentials.json"
fi

if [ -f "ai/cardioguard_model.onnx" ]; then
    ok "ai/cardioguard_model.onnx present"
else
    warn "ai/cardioguard_model.onnx is missing - the API will not start"
    todo "Produce the model: python export_onnx.py  (requires ai/best_model.keras)"
fi

# ─── 4. Dashboard dependencies ───────────────────────────────────────────────
if [ "$SKIP_DASHBOARD" -eq 0 ]; then
    step "Installing dashboard dependencies"
    (
        cd dashboard || exit 1
        info "Running npm install ..."
        npm install --no-fund --no-audit
    )
    if [ $? -eq 0 ]; then
        ok "Dashboard dependencies installed"
    else
        warn "npm install reported errors - review the output above."
    fi
fi

# ─── 5. Summary ──────────────────────────────────────────────────────────────
echo
printf "  ${C_GREY}--------------------------------------------------------${C_OFF}\n"
echo "  Setup complete"
printf "  ${C_GREY}--------------------------------------------------------${C_OFF}\n"

if [ ${#WARNINGS[@]} -gt 0 ]; then
    echo
    printf "  ${C_YELLOW}Warnings:${C_OFF}\n"
    for w in "${WARNINGS[@]}"; do printf "    ${C_YELLOW}- %s${C_OFF}\n" "$w"; done
fi

if [ ${#TODO[@]} -gt 0 ]; then
    echo
    echo "  Before the system will run, you still need to:"
    i=1
    for t in "${TODO[@]}"; do echo "    $i. $t"; i=$((i + 1)); done
fi

echo
echo "  Then start the system:"
printf "    ${C_GREY}Backend    source .venv/bin/activate${C_OFF}\n"
printf "    ${C_GREY}           uvicorn cloud_api:app --host 0.0.0.0 --port 8000${C_OFF}\n"
printf "    ${C_GREY}Dashboard  cd dashboard && npm run dev${C_OFF}\n"
printf "    ${C_GREY}Firmware   open firmware/cardioguard/cardioguard.ino in Arduino IDE 2.x${C_OFF}\n"
echo
printf "  ${C_GREY}Full instructions: docs/USER_MANUAL.md${C_OFF}\n"
echo
