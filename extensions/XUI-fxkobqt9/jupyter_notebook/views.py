import json
import os
import urllib.error
import urllib.request

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.shortcuts import render
from django.urls import reverse

from accounts.models import UserProfile
from bookmarks.models import Bookmark
from extensions.models import UIExtension
from extensions.views import admin_extension
from portals.models import PortalConfig

XUI_NAME = "jupyter_notebook"
BOOKMARK_URL = "/extensions/admin/jupyter_notebook/jupyter_notebook_view"

# Matches root_dir in jupyter_server_config.py.
NOTEBOOK_DIR = "/home/cloudbolt"
DEFAULT_NOTEBOOK = "django-shell.ipynb"


def sync_cbadmin_bookmarks(enabled):
    """While this XUI is enabled every active CB admin gets a navbar bookmark
    to it; disabling the XUI removes the bookmark again."""
    if enabled:
        admins = UserProfile.objects.filter(super_admin=True, user__is_active=True)
        for profile in admins:
            Bookmark.objects.get_or_create(
                profile=profile,
                page_url=BOOKMARK_URL,
                defaults={"page_title": "Django Notebook"},
            )
    else:
        Bookmark.objects.filter(page_url=BOOKMARK_URL).delete()


@receiver(post_save, sender=UIExtension, dispatch_uid="jupyter_notebook_bookmarks")
def on_uiextension_save(sender, instance, **kwargs):
    # The UI Extensions management toggle saves the row (toggle_boolean_property),
    # so enable/disable reacts instantly.
    if instance.name == XUI_NAME:
        sync_cbadmin_bookmarks(instance.enabled)


try:
    # Worker-start sync: covers toggles missed while unloaded and admins
    # created since the last sync.
    _row = UIExtension.objects.filter(name=XUI_NAME).first()
    if _row:
        sync_cbadmin_bookmarks(_row.enabled)
except Exception:
    # DB unavailable (migrations, collectstatic, package indexing) — skip.
    pass


@admin_extension(
    title="Jupyter Notebooks",
    description="Embedded JupyterLab tuned for CMP: opens straight into a "
    "Django Shell-Plus notebook, full-height.",
)
def jupyter_notebook_view(request):
    portal = PortalConfig.get_current_portal(request)
    # Relative URL keeps the embed on whatever host the admin is browsing
    # (portal domain, raw IP, alias) — the portal's configured domain can
    # differ from the request host and then the iframe never loads.
    # NOTEBOOK_BASE_URI still overrides when explicitly set.
    notebook_base_uri = getattr(settings, "NOTEBOOK_BASE_URI", "")

    # JupyterLab has no per-request theming; its theme is a persisted setting
    # on the (shared) lab server. Sync it to the portal's dark mode on each
    # visit so the embed matches the CMP chrome.
    theme = "JupyterLab Dark" if portal.dark_mode else "JupyterLab Light"
    theme_req = urllib.request.Request(
        f"http://127.0.0.1:{settings.NOTEBOOK_PORT}"
        "/shell/lab/api/settings/@jupyterlab/apputils-extension:themes",
        data=json.dumps({"raw": json.dumps({"theme": theme})}).encode(),
        method="PUT",
        headers={
            "Authorization": f"token {settings.NOTEBOOK_TOKEN}",
            "Content-Type": "application/json",
        },
    )
    try:
        urllib.request.urlopen(theme_req, timeout=3)
    except (urllib.error.URLError, OSError):
        pass  # lab server down — the iframe will surface that on its own

    # Open straight into a notebook instead of the Launcher/file browser.
    notebook_path = os.path.join(NOTEBOOK_DIR, DEFAULT_NOTEBOOK)
    if not os.path.exists(notebook_path):
        with open(notebook_path, "w") as f:
            json.dump(
                {
                    "cells": [],
                    "metadata": {
                        "kernelspec": {
                            "display_name": "Django Shell-Plus",
                            "language": "python",
                            "name": "django_extensions",
                        }
                    },
                    "nbformat": 4,
                    "nbformat_minor": 5,
                },
                f,
            )

    notebook_uri = (
        f"{notebook_base_uri}/shell/lab/tree/{DEFAULT_NOTEBOOK}"
        f"?token={settings.NOTEBOOK_TOKEN}"
    )
    context = {
        "notebook_uri": notebook_uri,
        "pagetitle": "Django Notebook",
        # "Admin / Jupyter Notebooks" breadcrumb, uniform with other admin pages.
        "uplink": {"url": reverse("admin_home"), "label": "Admin"},
    }
    return render(
        request, "jupyter_notebook/templates/django-notebook.html", context
    )
