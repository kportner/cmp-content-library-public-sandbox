# Jupyter Notebooks — CloudBolt Admin Extension

Run Jupyter notebooks against your CloudBolt CMP directly from the admin UI.
The page (**All Admin → Admin Extensions → Jupyter Notebooks**) embeds
JupyterLab wired to CloudBolt's **Django Shell-Plus** kernel, with all CMP
models pre-imported:

```python
Server.objects.count()
Resource.objects.filter(lifecycle="ACTIVE").last()
```

## Requirements

- CloudBolt CMP 2026.3.25 or later.
- Root shell access to the appliance for the one-time install step.
- Outbound PyPI access (only if JupyterLab is missing or below the secure
  minimum — see Security).

## Install

1. Upload/enable the extension on **Admin → UI Extensions**, or if you received
   the package as a directory, place it at
   `/var/opt/cloudbolt/proserv/xui/jupyter_notebook` and register it:

   ```bash
   sudo -u cloudbolt /usr/local/bin/python /opt/cloudbolt/manage.py shell -c "
   from extensions.models import UIExtension
   UIExtension.objects.get_or_create(name='jupyter_notebook', defaults={
       'label': 'Jupyter Notebooks',
       'filepath': '/var/opt/cloudbolt/proserv/xui/jupyter_notebook',
       'enabled': True})"
   sudo -u cloudbolt /usr/local/bin/python /opt/cloudbolt/manage.py collect_xui_apps
   ```

2. Run the installer as root (idempotent — safe to re-run any time):

   ```bash
   sudo bash /var/opt/cloudbolt/proserv/xui/jupyter_notebook/install.sh
   ```

   It configures the appliance's `jupyterd` service for JupyterLab, applies
   the security settings below, restarts the service, and self-verifies —
   expect `ALL CHECKS PASSED`.

3. Restart the web service once: `sudo systemctl restart httpd`.

## Using it

- Open **All Admin → Admin Extensions → Jupyter Notebooks**. Every CB admin
  also gets a **Django Notebook** entry in the navbar Bookmarks menu
  automatically while the extension is enabled.
- The page opens straight into `django-shell.ipynb`; notebooks are stored in
  `/home/cloudbolt` on the appliance.
- Only the **Django Shell-Plus** kernel is available — it is the default for
  new notebooks, so no kernel selection is needed.
- The notebook theme follows your portal's light/dark mode automatically.

## Security

- The page is restricted to CloudBolt admins; the notebook server binds to
  `127.0.0.1` only and requires CloudBolt's notebook token.
- The installer enforces **JupyterLab ≥ 4.5.7** and **Notebook ≥ 7.5.6**,
  which include the fixes for CVE-2026-42557 and GHSA-rch3-82jr-f9w9.
- The plain "Python 3 (ipykernel)" kernel is disabled.
- **Treat notebook access as root-equivalent for CMP**: the kernel executes
  code with full database access. Grant the page only to trusted admins and
  only open notebook files from trusted sources.
- Optional hardening: set a unique `NOTEBOOK_TOKEN` in
  `/var/opt/cloudbolt/proserv/customer_settings.py`, then
  `sudo systemctl restart jupyterd`.

## Uninstall

```bash
sudo bash /var/opt/cloudbolt/proserv/xui/jupyter_notebook/uninstall.sh
```

Removes the extension, its bookmarks, the Jupyter service configuration, and
disables `jupyterd`, leaving CloudBolt itself untouched. Add
`--remove-pip-packages` to also remove the JupyterLab/Notebook Python packages
(note: a later CMP upgrade may reinstall its own copies).

## Troubleshooting

| Symptom | Fix |
|---|---|
| Page shows *Service Unavailable* / empty frame | `sudo systemctl status jupyterd`, then re-run `install.sh` (it self-verifies) |
| "JupyterLab application assets not found" | Re-run `install.sh` |
| Need the notebook on a different URL/host | Set `NOTEBOOK_BASE_URI` in `customer_settings.py` (default is relative to the host you're browsing) |
