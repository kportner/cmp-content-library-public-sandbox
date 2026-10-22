#!/bin/bash
# Uninstaller for the Jupyter Notebook XUI + jupyterd JupyterLab stack.
# Exact inverse of install.sh — removes everything it added; CloudBolt CMP
# itself is untouched. Run as root:
#   bash uninstall.sh                       # keep CMP-shipped python packages (patched)
#   bash uninstall.sh --remove-pip-packages # also pip-uninstall jupyterlab + notebook
set -euo pipefail

PY=/usr/local/bin/python
PKG=jupyter_notebook
XUI_DIR=/var/opt/cloudbolt/proserv/xui/$PKG
JUPYTER_ETC=/usr/local/etc/jupyter
SITE_PKGS="$($PY -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
INIT=/etc/rc.d/init.d/jupyterd

[ "$(id -u)" -eq 0 ] || { echo "ERROR: run as root"; exit 1; }

echo "== stop + disable jupyterd"
systemctl stop jupyterd 2>/dev/null || true
systemctl disable jupyterd 2>/dev/null || true

echo "== restore jupyterd to its shipped launcher (shell_plus --notebook)"
if [ -f "$INIT" ]; then
    sed -i 's|shell_plus --lab|shell_plus --notebook|' "$INIT"
    rm -f "$INIT.bak"
fi
systemctl daemon-reload

echo "== remove jupyter server config delivered by the package"
rm -f "$JUPYTER_ETC/jupyter_server_config.py" \
      "$JUPYTER_ETC/labconfig/page_config.json" \
      "$SITE_PKGS/share/jupyter/lab/settings/overrides.json" \
      /etc/tmpfiles.d/cloudbolt-jupyterd.conf
rmdir "$JUPYTER_ETC/labconfig" 2>/dev/null || true
rm -rf /var/run/cloudbolt/jupyterd

echo "== remove the auto-created default notebook (any other notebooks are kept)"
rm -f /home/cloudbolt/django-shell.ipynb

echo "== deregister + remove the XUI"
sudo -u cloudbolt $PY /opt/cloudbolt/manage.py shell -c "
from extensions.models import UIExtension
print('UIExtension rows deleted:', UIExtension.objects.filter(name='$PKG').delete()[0])
try:
    from bookmarks.models import Bookmark
    print('bookmarks deleted:', Bookmark.objects.filter(page_url__contains='$PKG').delete()[0])
except ImportError:
    pass"
rm -rf "$XUI_DIR"

if [ "${1:-}" = "--remove-pip-packages" ]; then
    echo "== pip-uninstalling the jupyter server/UI constellation"
    # Nothing in CMP imports these — the sole consumer is django_extensions
    # shell_plus --notebook/--lab, which is exactly the feature being removed.
    # (jupyter_core / jupyterlab_pygments / ipython / nbformat / nbconvert are
    # kept: shared plumbing other tooling may import.)
    # These are CMP-shipped: the next CMP upgrade will reinstall its own
    # (possibly vulnerable) versions — track that with the product Jira.
    $PY -m pip uninstall -y --root-user-action=ignore \
        jupyterlab jupyterlab_server jupyter-lsp \
        notebook notebook_shim nbclassic \
        jupyter_server jupyter_server_terminals jupyter-events \
        ipykernel jupyter_client || true
else
    echo "== python packages kept at patched versions (add --remove-pip-packages to remove the jupyter stack)"
fi

echo "== restart web service"
systemctl restart httpd
sleep 5

echo "== verify"
if ss -tln | grep -q 127.0.0.1:55555; then echo "FAIL: something still listening on 55555"; exit 1; fi
if [ -d "$XUI_DIR" ]; then echo "FAIL: $XUI_DIR still present"; exit 1; fi
if [ -f "$JUPYTER_ETC/jupyter_server_config.py" ]; then echo "FAIL: jupyter_server_config.py still present"; exit 1; fi
CMP_CODE="$(curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1/accounts/login/)"
[ "$CMP_CODE" = "200" ] || { echo "FAIL: CMP login page returned $CMP_CODE"; exit 1; }
echo
echo "UNINSTALL COMPLETE — jupyterd disabled, XUI removed, CMP responding normally ($CMP_CODE)."
