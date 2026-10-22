#!/bin/bash
# Installer for the Jupyter Notebooks stack (xui/jupyter_notebook).
# Run as root(sudo su -) on the CMP appliance AFTER the XUI is uploaded/enabled:
#   bash /var/opt/cloudbolt/proserv/xui/jupyter_notebook/install.sh
# Idempotent — safe to re-run. Docs: /var/opt/cloudbolt/proserv/jupyter/README.md
set -euo pipefail
umask 022  # pip/config files must stay world-readable for the cloudbolt user

PY=/usr/local/bin/python
XUI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JUPYTER_ETC=/usr/local/etc/jupyter
SITE_PKGS=/usr/local/lib/python3.12/site-packages
LAB_APP_DIR=$SITE_PKGS/share/jupyter/lab
INIT=/etc/rc.d/init.d/jupyterd
# Security minimums: CVE-2026-42557 (jupyterlab) / GHSA-rch3-82jr-f9w9 (notebook).
export JUPYTERLAB_MIN=4.5.7 NOTEBOOK_MIN=7.5.6
TOKEN="$(grep -oP 'NOTEBOOK_TOKEN = "\K[^"]+' /opt/cloudbolt/settings.py | head -1)"

[ "$(id -u)" -eq 0 ] || { echo "ERROR: run as root"; exit 1; }
[ -f "$INIT" ] || { echo "ERROR: $INIT missing — is this a CMP appliance?"; exit 1; }

echo "== guard rail: setuptools must stay < 81 (81+ removes pkg_resources; CMP won't start)"
# Read the version from dist metadata, NOT via `import setuptools` — a mangled
# install (e.g. missing _distutils_hack) fails to import even at a safe version.
$PY - <<'EOF'
import importlib.metadata as md
v = md.version("setuptools")
assert int(v.split(".")[0]) < 81, f"setuptools {v} >= 81 would break CMP - aborting"
import pkg_resources  # the module CMP actually needs at runtime
print(f"setuptools {v} ok, pkg_resources importable")
EOF
if ! $PY -c "import setuptools" >/dev/null 2>&1; then
    SETUPTOOLS_VER="$($PY -c 'import importlib.metadata as md; print(md.version("setuptools"))')"
    echo "setuptools $SETUPTOOLS_VER is present but broken (import fails) — repairing at the same version"
    $PY -m pip install --root-user-action=ignore --force-reinstall --no-deps "setuptools==$SETUPTOOLS_VER"
    $PY -c "import setuptools, pkg_resources" || { echo "FAIL: setuptools still broken after repair"; exit 1; }
fi

echo "== pip packages (jupyterlab >= $JUPYTERLAB_MIN per CVE-2026-42557, notebook >= $NOTEBOOK_MIN per GHSA-rch3-82jr-f9w9)"
# jupyterlab 4.5.7 needs packaging >= 24 (packaging.utils.InvalidName); repeated
# installs can also leave duplicate packaging dist-info dirs (module/metadata
# mismatch) — repair to one clean version first.
if ! $PY -c "from packaging.utils import InvalidName" >/dev/null 2>&1 \
   || [ "$(ls -d $SITE_PKGS/packaging-*.dist-info 2>/dev/null | wc -l)" -gt 1 ]; then
    echo "packaging too old or inconsistent — repairing"
    rm -rf $SITE_PKGS/packaging-*.dist-info
    $PY -m pip install --root-user-action=ignore --force-reinstall "packaging==26.3"
fi
# Upgrade anything below the security-patched versions (covers absent packages
# and classic notebook 6.x alike — jupyterd runs --lab on py3.12).
TO_INSTALL="$($PY - <<'EOF'
import importlib.metadata as md
import os
def below(dist, minimum):
    try:
        v = tuple(int(x) for x in md.version(dist).split(".")[:3])
    except md.PackageNotFoundError:
        return True
    return v < tuple(int(x) for x in minimum.split("."))
wanted = [
    f"{dist}=={os.environ[env]}"
    for dist, env in (("jupyterlab", "JUPYTERLAB_MIN"), ("notebook", "NOTEBOOK_MIN"))
    if below(dist, os.environ[env])
]
print(" ".join(wanted))
EOF
)"
if [ -n "$TO_INSTALL" ]; then
    echo "installing: $TO_INSTALL"
    $PY -m pip install --root-user-action=ignore $TO_INSTALL
fi
$PY - <<'EOF'
import importlib.metadata as md
import os
import pkg_resources
for dist, env in (("jupyterlab", "JUPYTERLAB_MIN"), ("notebook", "NOTEBOOK_MIN")):
    v = tuple(int(x) for x in md.version(dist).split(".")[:3])
    minimum = tuple(int(x) for x in os.environ[env].split("."))
    assert v >= minimum, f"{dist} {md.version(dist)} below security minimum {os.environ[env]}"
s = md.version("setuptools")
assert int(s.split(".")[0]) < 81, f"pip pulled setuptools {s} >= 81 - REMEDIATE"
print(f"jupyterlab {md.version('jupyterlab')} ok, notebook {md.version('notebook')} ok, setuptools {s} ok")
EOF
# Belt and braces in case pip ever ran under a restrictive umask before.
chmod -R a+rX "$LAB_APP_DIR"

echo "== jupyterd runtime dir (tmpfs — tmpfiles.d entry keeps it across reboots)"
mkdir -p /var/run/cloudbolt/jupyterd
chown cloudbolt:cloudbolt /var/run/cloudbolt/jupyterd
cat > /etc/tmpfiles.d/cloudbolt-jupyterd.conf <<'EOF'
d /var/run/cloudbolt/jupyterd 0755 cloudbolt cloudbolt -
EOF
chmod 644 /etc/tmpfiles.d/cloudbolt-jupyterd.conf

echo "== jupyterd must launch JupyterLab (shell_plus --lab)"
if ! grep -q 'shell_plus --lab' "$INIT"; then
    cp -p "$INIT" "$INIT.bak"
    sed -i 's|shell_plus --notebook|shell_plus --lab|' "$INIT"
fi
grep -q 'shell_plus --lab' "$INIT" || { echo "ERROR: could not set --lab in $INIT"; exit 1; }

echo "== Jupyter server config (delivered by this package)"
mkdir -p "$JUPYTER_ETC/labconfig" "$LAB_APP_DIR/settings"
install -m 0644 "$XUI_DIR/jupyter_server_config.py" "$JUPYTER_ETC/jupyter_server_config.py"
# Disable the "Jupyter news" popup (announcements plugin).
cat > "$JUPYTER_ETC/labconfig/page_config.json" <<'EOF'
{
  "disabledExtensions": {
    "@jupyterlab/apputils-extension:announcements": true
  }
}
EOF
# Pin the Lab theme (flip to "JupyterLab Dark" for dark portals).
cat > "$LAB_APP_DIR/settings/overrides.json" <<'EOF'
{
  "@jupyterlab/apputils-extension:themes": {
    "theme": "JupyterLab Light"
  }
}
EOF
chmod 644 "$JUPYTER_ETC/labconfig/page_config.json" "$LAB_APP_DIR/settings/overrides.json"

echo "== ownership"
chown -R cloudbolt:cloudbolt "$XUI_DIR"

echo "== SELinux: Apache must be allowed to proxy /shell/ to 127.0.0.1:55555"
if command -v getenforce >/dev/null 2>&1 && [ "$(getenforce)" = "Enforcing" ]; then
    setsebool -P httpd_can_network_connect 1
fi

echo "== services"
systemctl daemon-reload
systemctl enable jupyterd >/dev/null 2>&1 || true
systemctl restart jupyterd

echo "== verify"
for i in $(seq 1 24); do
    ss -tln | grep -q 127.0.0.1:55555 && break
    sleep 5
done
ss -tln | grep -q 127.0.0.1:55555 || { echo "FAIL: nothing listening on 55555"; exit 1; }

LAB_HTML="$(curl -s "http://127.0.0.1:55555/shell/lab?token=$TOKEN")"
echo "$LAB_HTML" | grep -q "JupyterLab" || { echo "FAIL: /shell/lab is not JupyterLab"; exit 1; }
echo "$LAB_HTML" | grep -q "assets not found" && { echo "FAIL: Lab assets missing (app_dir wrong)"; exit 1; }

KERNELS="$(curl -s "http://127.0.0.1:55555/shell/api/kernelspecs?token=$TOKEN")"
echo "$KERNELS" | grep -q '"default": "django_extensions"' || { echo "FAIL: default kernel is not django_extensions"; exit 1; }
# NB: match the kernelspec NAME key — the django_extensions spec's argv itself
# contains "ipykernel_launcher", so a bare 'ipykernel' grep false-positives.
echo "$KERNELS" | grep -q '"python3":' && { echo "FAIL: python3 kernel still exposed"; exit 1; }

curl -sI "http://127.0.0.1:55555/shell/lab?token=$TOKEN" | grep -qi "frame-ancestors" \
    || { echo "FAIL: CSP frame-ancestors header missing (iframe embed will break)"; exit 1; }

echo
echo "ALL CHECKS PASSED — JupyterLab on 127.0.0.1:55555 under /shell/, Django Shell-Plus kernel only."
echo "Open: All Admin -> Admin Extensions -> Jupyter Notebooks"
