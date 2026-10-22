"""
HTTP layer: the lazily fetched tab shell, its DataTables source (objects_json),
and the ACTIONS catalogue that both the CMP dialogs and the POST dispatcher run
through. All AWS work lives in models.S3Bucket.
"""

import json
import time

from accounts.models import Group
from django.conf import settings
from django.contrib import messages
from django.http import Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import escape, format_html
from django.utils.http import urlencode
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_POST

from extensions.views import (
    admin_extension, dashboard_extension, tab_extension, TabExtensionDelegate)
from jobs.models import RecurringJob
from resourcehandlers.aws.models import AWSHandler
from resources.models import Resource, ResourceType
from servicecatalog.models import ServiceBlueprint
from utilities.decorators import dialog_view, json_view_no_escape
from utilities.logger import ThreadLogger

from xui.s3_file_manager import forms, models

logger = ThreadLogger(__name__)


# ── Bucket resolution and browser state ──────────────────────────────────────

def _bucket_queryset(profile):
    """S3 bucket resources the user may browse (RBAC via group membership)."""
    qs = Resource.objects.filter(
        resource_type__name=models.S3_RESOURCE_TYPE, lifecycle="ACTIVE")
    if not profile.super_admin:
        qs = qs.filter(group__in=profile.get_groups())
    return qs.order_by("-created")


def _dedup_by_name(resources):
    """First Resource seen per bucket name, in the given order.

    The "Sync Resources" job can leave behind duplicate Resource rows for
    the same physical bucket, which would otherwise show up as the exact
    same bucket name twice everywhere a bucket list is presented (admin
    panel inventory, dashboard widget dropdown).
    """
    seen_names, deduped = set(), []
    for resource in resources:
        if resource.name in seen_names:
            continue
        seen_names.add(resource.name)
        deduped.append(resource)
    return deduped


def _get_bucket(request, resource_id):
    """S3Bucket wrapper, or 404 — same answer for unknown and unauthorized ids."""
    return models.S3Bucket(get_object_or_404(
        _bucket_queryset(request.get_user_profile()), pk=resource_id))


def _clean_path(value):
    """Folder prefix: ends in "/", no "..". Leading "/" is kept — S3 allows it."""
    path = (value or "").strip()
    if ".." in path:
        raise Http404("Invalid path")
    return f"{path.rstrip('/')}/" if path else ""


def _browser_state(request):
    """Folder/flat/filter, from the query string first, then the form body."""
    def value(key):
        return request.GET.get(key) or request.POST.get(key) or ""
    return {"s3path": _clean_path(value("s3path")),
            "s3flat": "1" if value("s3flat") == "1" else "",
            "s3filter": value("s3filter").strip()}


TAB_HASH = "#tab-s3-bucket-management"


def _tab_url(resource, state, **panel):
    """Resource URL that reopens the S3 tab; `_` keeps it unique per redirect
    (a same-URL-with-hash assignment never navigates, so the dialog would hang)."""
    params = {k: v for k, v in {**state, **panel}.items() if v}
    params["_"] = int(time.time() * 1000)
    return f"{resource.get_absolute_url()}?{urlencode(params)}{TAB_HASH}"


def _reject(request, form, bucket, state):
    """Report form errors as toasts and return to the folder."""
    for field, errors in form.errors.items():
        messages.error(request, errors[0] if field == "__all__"
                       else f"{form.fields[field].label or field}: {errors[0]}")
    return HttpResponseRedirect(_tab_url(bucket.resource, state))


# ── The tab ──────────────────────────────────────────────────────────────────

class S3BucketTabDelegate(TabExtensionDelegate):
    def should_display(self):
        resource = self.instance
        return bool(getattr(resource, "resource_type", None)
                    and resource.resource_type.name == models.S3_RESOURCE_TYPE
                    and getattr(resource, "lifecycle", None) == "ACTIVE")


def _browser_context(profile, resource):
    """Context for browser_panel.html — shared by the tab and the dashboard
    widget's fragment, so both render the exact same bucket browser."""
    return {
        "resource": resource,
        "can_edit_permissions": models.Authorization.can_edit_permissions(profile),
        "can_delete_bucket": models.Authorization.can_delete_bucket(profile),
        "is_super_admin": profile.super_admin,
        "objects_url": reverse("s3_mgmt_objects_json", args=[resource.id]),
        "dialog_url": reverse("s3_mgmt_dialog", args=[resource.id]),
        "upload_max_files": settings.DATA_UPLOAD_MAX_NUMBER_FILES,
    }


@tab_extension(model=Resource, title="S3 File Manager",
               delegate=S3BucketTabDelegate)
def s3_file_manager_tab(request, obj_id):
    """The tab shell; CloudBolt fetches it lazily, so it carries no page state."""
    profile = request.get_user_profile()
    resource = get_object_or_404(_bucket_queryset(profile), pk=obj_id)
    return render(request, "s3_file_manager/templates/browser_panel.html",
                  _browser_context(profile, resource))


# ── The dashboard widget ─────────────────────────────────────────────────────

@dashboard_extension(title="S3 Bucket Manager",
                     description="Pick an S3 bucket and browse it from the dashboard")
def s3_dashboard_widget(request):
    """Bucket picker; the fragment it loads is s3_dashboard_widget_browser,
    which renders the same browser_panel.html the resource tab uses."""
    profile = request.get_user_profile()
    # First-run on a fresh install: the ResourceType this xui filters on
    # doesn't exist yet because the "AWS S3 Bucket" blueprint hasn't been
    # imported, so _bucket_queryset's filter would just silently return
    # nothing. Distinguish that from "the type exists, nothing synced yet"
    # so the widget can point at the actual next step instead of a bare
    # empty dropdown either way.
    resource_type_exists = ResourceType.objects.filter(
        name=models.S3_RESOURCE_TYPE).exists()
    buckets = (_dedup_by_name(_bucket_queryset(profile).order_by("name"))
               if resource_type_exists else [])
    s3_blueprint = ServiceBlueprint.objects.filter(
        name="AWS S3 Bucket", status="ACTIVE").first()
    return render(request, "s3_file_manager/templates/dashboard_widget.html", {
        "buckets": buckets,
        "resource_type_exists": resource_type_exists,
        "s3_blueprint_id": s3_blueprint.id if s3_blueprint else None,
    })


def s3_dashboard_widget_browser(request, resource_id):
    """AJAX fragment for the dashboard widget: the same panel the tab renders."""
    profile = request.get_user_profile()
    resource = get_object_or_404(_bucket_queryset(profile), pk=resource_id)
    return render(request, "s3_file_manager/templates/browser_panel.html",
                  _browser_context(profile, resource))


@require_POST
def sync_s3_buckets(request):
    """Manually trigger the "Sync Resources" recurring job so newly created
    S3 buckets (or ones created outside CloudBolt) show up without waiting
    for its normal schedule. Super admin only, same as the admin panel."""
    profile = request.get_user_profile()
    if not profile.super_admin:
        return JsonResponse({"status": False,
                             "message": "Permission denied: super admin required."})
    try:
        rb = RecurringJob.objects.get(name="Sync Resources")
        recurring_job = RecurringJob.objects.get(global_id=rb.global_id)
        job = recurring_job.cast().spawn_new_job()
        logger.info("User %s manually triggered the 'Sync Resources' recurring "
                    "job; created job id %s" % (profile, job.id))
        return JsonResponse({"status": True, "job_id": job.id})
    except RecurringJob.DoesNotExist:
        return JsonResponse({"status": False,
                             "message": "The 'Sync Resources' recurring job was not found."})
    except Exception as e:
        logger.exception("Failed to trigger the 'Sync Resources' recurring job")
        return JsonResponse({"status": False, "message": str(e)})


@json_view_no_escape
def objects_json(request, resource_id):
    """One folder as server-side DataTables data: rows are positional cell lists.

    no_escape because rows carry URLs; every text cell is escaped explicitly.
    """
    bucket = _get_bucket(request, resource_id)
    path = _clean_path(request.GET.get("path"))
    flat = request.GET.get("flat") == "1"
    can_edit_note = models.Authorization.can_delete_bucket(request.get_user_profile())

    try:
        versioning = bucket.versioning
        items = bucket.list_folder(path, flat=flat,
                                   show_deleted=request.GET.get("deleted") == "1")
        error, bucket_missing = "", False
    except Exception as e:
        logger.exception(f"Failed to list S3 bucket {bucket.name}")
        items, versioning = [], ""
        bucket_missing = bucket.confirm_missing()
        # confirm_missing() makes its own real AWS call (head_bucket) rather
        # than trusting this exception's text — once it's confirmed, "in AWS"
        # is appended so the message reads unambiguously (the bucket clearly
        # still "exists" as this very CloudBolt resource showing the error).
        error = f"{e} in AWS" if bucket_missing else str(e)

    total = len(items)
    search = (request.GET.get("sSearch") or "").strip().lower()
    if search:
        items = [i for i in items if search in str(i["name"]).lower()]

    # Sort by the requested column (folders always first), then page.
    sort_keys = {1: lambda i: str(i["name"]).lower(),
                 2: lambda i: str(i["item_type"] or ""),
                 3: lambda i: i.get("last_modified_iso") or "",
                 4: lambda i: i.get("actual_size") or 0,
                 5: lambda i: str(i.get("storage_class") or "")}
    try:
        column = int(request.GET.get("iSortCol_0") or 1)
        start = int(request.GET.get("iDisplayStart") or 0)
        length = int(request.GET.get("iDisplayLength") or 25)
    except ValueError:
        column, start, length = 1, 0, 25
    items.sort(key=lambda i: (i["is_file"], sort_keys.get(column, sort_keys[1])(i)),
               reverse=(request.GET.get("sSortDir_0") or "asc") == "desc")
    page = items if length < 0 else items[start:start + length]

    dialog_url = reverse("s3_mgmt_dialog", args=[bucket.resource.id])
    download_url = reverse("s3_mgmt_download", args=[bucket.resource.id])
    rows = []
    if path and start == 0:
        # ".." leads the first page; excluded from totals so paging stays honest.
        stem = path.rstrip("/")
        parent = f"{stem.rsplit('/', 1)[0]}/" if "/" in stem else ""
        rows.append(["", format_html(
            '<a href="#" class="s3b-folder" data-s3-key="{}" title="Up one level">'
            '<i class="bi bi-arrow-90deg-up me-2"></i>..</a>', parent),
            "Folder", "—", "—", "—", ""])
    for item in page:
        key, name, is_file = item["key"], str(item["name"]), item["is_file"]
        icon = ("bi-file-earmark text-body-secondary" if is_file
                else "bi-folder-fill text-warning")
        if is_file or flat:
            name_html = format_html('<i class="bi {} me-2"></i>{}', icon, name)
        else:
            name_html = format_html(
                '<i class="bi {} me-2"></i>'
                '<a href="#" class="s3b-folder" data-s3-key="{}">{}</a>',
                icon, key, name)
        if item["is_deleted"]:
            name_html = format_html(
                '{}<span class="badge text-bg-secondary ms-2">deleted</span>',
                name_html)

        buttons = []
        if is_file and not item["is_deleted"]:
            buttons.append(format_html(
                '<a class="btn btn-light" title="Download" href="{}?key={}">'
                '<i class="bi bi-download"></i></a>', download_url, key))
        if not item["is_deleted"] and not flat:
            buttons.append(format_html(
                '<a class="btn btn-light open-dialog" title="Rename" '
                'href="{}?action=rename&amp;key={}&amp;path={}">'
                '<i class="bi bi-pencil"></i></a>', dialog_url, key, path))
        if is_file and item["version_count"] > 1:
            buttons.append(format_html(
                '<a class="btn btn-light open-dialog" title="Versions" '
                'href="{}?action=versions&amp;key={}&amp;path={}">'
                '<i class="bi bi-clock-history"></i> {}</a>',
                dialog_url, key, path, item["version_count"]))

        # DataTables inserts cells as HTML, so plain-text cells are escaped —
        # item_type comes from the (user-controlled) object key.
        rows.append([
            format_html('<input class="form-check-input s3b-item" type="checkbox" '
                        'value="{}" aria-label="Select {}">', key, name),
            name_html,
            escape(item["item_type"] or "—"),
            escape((item["last_modified"] or "—") if is_file else "—"),
            escape((item["size"] or "—") if is_file else "—"),
            escape((item["storage_class"] or "—") if is_file else "—"),
            format_html('<div class="btn-group btn-group-sm">{}</div>',
                        mark_safe("".join(buttons))),
        ])

    crumbs, walked = [], ""
    for part in path.strip("/").split("/"):
        if part:
            walked = f"{walked}{part}/"
            crumbs.append({"name": part, "path": walked})
    return {
        "sEcho": int(request.GET.get("sEcho") or 1),
        "iTotalRecords": total,
        "iTotalDisplayRecords": len(items),
        "aaData": rows,
        # Extra keys DataTables ignores; the shell reads them via xhr.dt.
        "meta": {"bucket": bucket.name, "path": path, "crumbs": crumbs,
                 "versioning": versioning or "disabled",
                 "versioning_enabled": versioning == "Enabled",
                 "can_enable_versioning": versioning != "Enabled",
                 "error": error, "bucket_missing": bucket_missing,
                 "note": bucket.note, "can_edit_note": can_edit_note},
    }


# ── Actions — one catalogue drives the dispatcher and the dialogs ────────────

def _versions_content(request, bucket):
    """Read-only version table for ?key=, as dialog content."""
    key = request.GET.get("key") or ""
    prefix = f"{key.rsplit('/', 1)[0]}/" if "/" in key else ""
    item = next((i for i in bucket.list_folder(prefix, show_deleted=True)
                 if i["key"] == key), None)
    return render_to_string(
        "s3_file_manager/templates/dialog_versions.html",
        {"key": key, "prefix": prefix,
         "versions": item["versions"] if item else [],
         "download_url": reverse("s3_mgmt_download", args=[bucket.resource.id]),
         "objects_url": reverse("s3_mgmt_objects", args=[bucket.resource.id]),
         "dialog_url": reverse("s3_mgmt_dialog", args=[bucket.resource.id])},
        request=request)


def _permissions_content(request, bucket):
    """The read-only half of the permissions dialog (status, owner, grants)."""
    context = {}
    try:
        context["public"] = bucket.policy_is_public
    except Exception as e:
        context["public_error"] = str(e)
    try:
        context["acl"] = bucket.acl
        context["acls_enabled"] = bucket.acls_enabled
    except Exception as e:
        context["acl_error"] = str(e)
    return render_to_string(
        "s3_file_manager/templates/dialog_permissions.html", context,
        request=request)


ACTIONS = {
    "new-folder": {
        "title": "New folder", "submit": "Create",
        "form": lambda request, bucket: forms.NewFolderForm()},
    "rename": {
        "title": "Rename", "submit": "Rename",
        "form": lambda request, bucket: forms.RenameForm(initial={
            "key": request.GET.get("key") or "",
            "new_object_name": (request.GET.get("key") or "")
            .rstrip("/").rsplit("/", 1)[-1]})},
    "upload": {
        "title": "Upload", "submit": "Upload",
        # Filled by the shell script: chosen count/size, then live progress.
        "content": mark_safe(
            '<p id="s3b-upload-meta" class="small text-body-secondary mb-2">'
            'Choose files or a folder.</p>'
            '<div id="s3b-upload-progress" class="progress mb-3 d-none" '
            'role="progressbar" aria-valuemin="0" aria-valuemax="100">'
            '<div class="progress-bar"></div></div>'),
        "form": lambda request, bucket: forms.UploadForm()},
    "delete": {
        "title": "Delete objects", "submit": "Delete",
        "content": "Delete every object ticked in the list? Folders are "
                   "removed with everything beneath them."},
    "enable-versioning": {
        "title": "Enable versioning", "submit": "Enable",
        "content": "S3 will keep every version of every object from now on, "
                   "and storage is charged for all of them. Versioning can "
                   "afterwards be suspended, but never switched off again."},
    "promote-version": {"title": "Promote version", "submit": None},
    "delete-version": {
        "title": "Delete version", "submit": "Delete permanently", "rights": "delete",
        "content": lambda request, bucket: format_html(
            "This permanently destroys version <code>{}</code> of "
            "<strong>{}</strong>. Unlike deleting the object itself, this "
            "cannot be undone, even with versioning enabled — the data is "
            "gone immediately, the same as deleting a version from AWS's "
            "own S3 console.",
            request.GET.get("version_id") or "", request.GET.get("key") or "")},
    "versions": {"title": "Object versions", "submit": None,
                 "content": _versions_content},
    "permissions": {
        "title": "Permissions", "submit": "Save", "rights": "permissions",
        "content": _permissions_content,
        "form": lambda request, bucket: forms.BucketPermissionsForm(
            # bucket.policy is S3's JSON *string*; parse it so the field
            # pretty-prints the document instead of double-encoding it.
            initial={**bucket.public_access_block,
                     **({"policy": json.loads(bucket.policy)}
                        if bucket.policy else {})},
            acls_enabled=bucket.acls_enabled)},
    "assign-group": {
        "title": "Assign to group", "submit": "Assign", "rights": "admin",
        "content": "Group membership controls who can see and manage this "
                   "bucket in CloudBolt. AWS is not touched.",
        "form": lambda request, bucket: forms.AssignGroupForm(
            initial={"group": bucket.resource.group_id})},
    "delete-bucket": {
        "title": "Delete bucket", "submit": "Submit delete order",
        "rights": "delete",
        "content": lambda request, bucket: format_html(
            "This submits a CloudBolt order to permanently delete "
            "<strong>{}</strong> and ALL of its contents, including every object "
            "version. The bucket is deleted only after the order is approved.",
            bucket.name),
        "form": lambda request, bucket:
            forms.DeleteBucketForm(bucket_name=bucket.name)},
    "remove-missing-bucket": {
        "title": "Remove from CloudBolt", "submit": "Remove", "rights": "delete",
        "content": lambda request, bucket: format_html(
            "<strong>{}</strong> was deleted directly in AWS - there is nothing "
            "left to delete. This only removes the CloudBolt resource record.",
            bucket.name)},
    "edit-note": {
        "title": "Edit note", "submit": "Save", "rights": "delete",
        "form": lambda request, bucket: forms.NoteForm(initial={"note": bucket.note})},
}


def _check_rights(action, profile):
    """404 unless the profile holds the right this action demands."""
    rights = ACTIONS[action].get("rights")
    if rights == "permissions" and not models.Authorization.can_edit_permissions(profile):
        raise Http404("Not authorized to change bucket permissions")
    if rights == "delete" and not models.Authorization.can_delete_bucket(profile):
        raise Http404("Not authorized for this destructive action")
    if rights == "admin" and not profile.super_admin:
        raise Http404("Super admin required")


def _run_action(request, bucket, state, action, on_done):
    """Perform one action; the toast, error handling and History row live here."""
    if action not in ACTIONS:
        raise Http404(f"Unknown action: {action}")
    profile = request.get_user_profile()
    _check_rights(action, profile)
    try:
        result = _perform(request, bucket, state, action)
    except Exception as e:
        logger.exception(f"Action '{action}' failed on S3 bucket {bucket.name}")
        messages.error(request, f"{action} failed: {e}")
        bucket.record(f"FAILED — {action}: {e}", profile=profile)
        return on_done()
    if isinstance(result, HttpResponse):
        return result                                   # a form bounced back
    summary, response = result if isinstance(result, tuple) else (result, None)
    if summary:
        # profile fills the History tab's User column; the message stays impersonal.
        messages.success(request, f"{summary}.")
        bucket.record(f"{summary}.", profile=profile)
        logger.info(f"User {profile} — {summary} — S3 bucket: {bucket.name}")
    return response or on_done()


def _perform(request, bucket, state, action):
    """The action itself. Returns the sentence for the toast + History row,
    (sentence, response) to override the redirect, a response to bounce a form
    back, or None when the error was already reported."""
    if action == "new-folder":
        form = forms.NewFolderForm(request.POST)
        if not form.is_valid():
            return _reject(request, form, bucket, state)
        key = bucket.create_folder(state["s3path"], form.cleaned_data["folder_name"])
        return f"Created folder {key}"

    if action == "rename":
        form = forms.RenameForm(request.POST)
        if not form.is_valid():
            return _reject(request, form, bucket, state)
        old_key = form.cleaned_data["key"]
        new_key, moved = bucket.rename(old_key, form.cleaned_data["new_object_name"])
        if moved is None:
            return f"Renamed {old_key} to {new_key}"
        return f"Renamed folder {old_key} to {new_key} ({moved} object(s) moved)"

    if action == "upload":
        # The shell script posts every file as `files` with a parallel `paths`
        # list (relative path inside a chosen folder), in batches.
        files = request.FILES.getlist("files") + request.FILES.getlist("folder")
        if not files:
            messages.error(request, "Choose at least one file to upload.")
            return None
        keys = bucket.upload(state["s3path"], files, request.POST.getlist("paths"))
        return (f"Uploaded {len(keys)} object(s) to /{state['s3path']}: "
                f"{bucket.describe_keys(keys)}")

    if action == "delete":
        selected = request.POST.getlist("keys")
        if not selected:
            messages.error(request, "Select at least one object to delete.")
            return None
        keys = bucket.delete(selected)
        folders = [k for k in selected if k.endswith("/")]
        detail = f" (recursively, from {bucket.describe_keys(folders)})" if folders else ""
        return f"Deleted {len(keys)} object(s){detail}: {bucket.describe_keys(keys)}"

    if action == "enable-versioning":
        bucket.enable_versioning()
        return "Enabled versioning on the bucket"

    if action == "promote-version":
        key = request.POST.get("key") or ""
        version_id = request.POST.get("version_id") or ""
        bucket.promote_version(key, version_id)
        return f"Promoted version {version_id} of {key} to latest"

    if action == "delete-version":
        key = request.GET.get("key") or ""
        version_id = request.GET.get("version_id") or ""
        if not key or not version_id:
            messages.error(request, "Missing key or version id.")
            return None
        if not bucket.delete_version(key, version_id):
            return f"Version {version_id} of {key} was already gone — nothing to delete"
        return f"Permanently deleted version {version_id} of {key}"

    if action == "remove-missing-bucket":
        if not bucket.confirm_missing():
            messages.error(request, "This bucket still exists in AWS - "
                                    "refusing to remove it from CloudBolt.")
            return None
        bucket.resource.lifecycle = "HISTORICAL"
        bucket.resource.save(update_fields=["lifecycle"])
        return "Removed from CloudBolt after confirming the bucket no longer exists in AWS"

    if action == "edit-note":
        form = forms.NoteForm(request.POST)
        if not form.is_valid():
            return _reject(request, form, bucket, state)
        bucket.save_note(form.cleaned_data["note"])
        return "Updated the bucket note"

    if action == "assign-group":
        form = forms.AssignGroupForm(request.POST)
        if not form.is_valid():
            return _reject(request, form, bucket, state)
        was = bucket.resource.group
        bucket.resource.group = form.cleaned_data["group"]
        bucket.resource.save(update_fields=["group"])
        return (f"Assigned this bucket resource to group "
                f"{bucket.resource.group} (was {was})")

    if action == "permissions":
        form = forms.BucketPermissionsForm(request.POST,
                                           acls_enabled=bucket.acls_enabled)
        if not form.is_valid():
            return _reject(request, form, bucket, state)
        data = form.cleaned_data
        flags = {name: data[name] for name in
                 ("BlockPublicAcls", "IgnorePublicAcls",
                  "BlockPublicPolicy", "RestrictPublicBuckets")}
        bucket.save_public_access_block(flags)
        done = ["Block Public Access ("
                + ", ".join(f"{n}={'on' if v else 'off'}"
                            for n, v in sorted(flags.items())) + ")"]
        if data.get("canned_acl"):
            bucket.apply_canned_acl(data["canned_acl"])
            done.append(f"canned ACL '{data['canned_acl']}'")
        if data.get("delete_policy"):
            bucket.delete_policy()
            done.append("deleted the bucket policy")
        elif data.get("policy"):
            bucket.save_policy(data["policy"])
            statements = (data["policy"].get("Statement")
                          if isinstance(data["policy"], dict) else None)
            done.append(f"bucket policy ({len(statements or [])} statement(s))")
        return "Saved permissions — " + "; ".join(done)

    raise Http404(f"Unknown action: {action}")


@require_POST
def object_action(request, resource_id):
    """POST target for every action (?action=<name>)."""
    bucket = _get_bucket(request, resource_id)
    state = _browser_state(request)
    return _run_action(request, bucket, state, request.GET.get("action") or "",
                       lambda: HttpResponseRedirect(_tab_url(bucket.resource, state)))


def download_item(request, resource_id):
    """302 to a presigned URL for one object (optionally one version)."""
    bucket = _get_bucket(request, resource_id)
    key = request.GET.get("key") or ""
    url = key and bucket.presigned_url(
        key, version_id=request.GET.get("version_id") or None)
    if not url:
        raise Http404("No downloadable object")
    logger.info(f"User {request.get_user_profile()} downloaded {key} "
                f"from S3 bucket: {bucket.name}")
    return HttpResponseRedirect(url)


@dialog_view
def action_dialog(request, resource_id):
    """Render (GET) and run (POST) the ACTIONS entry named by ?action=."""
    bucket = _get_bucket(request, resource_id)
    action = request.GET.get("action") or ""
    if action not in ACTIONS:
        raise Http404(f"Unknown dialog: {action}")
    spec = ACTIONS[action]
    _check_rights(action, request.get_user_profile())
    state = {"s3path": _clean_path(request.GET.get("path")),
             "s3flat": "", "s3filter": ""}

    if request.method == "POST":
        if action == "delete-bucket":
            return delete_bucket(request, resource_id)
        return _run_action(
            request, bucket, state, action,
            lambda: HttpResponseRedirect(_tab_url(bucket.resource, state)))

    query = urlencode({k: v for k, v in (("action", action),
                                         ("key", request.GET.get("key") or ""),
                                         ("version_id", request.GET.get("version_id") or ""),
                                         ("path", state["s3path"])) if v})
    dialog = {
        "title": f"{spec['title']} — {bucket.name}",
        "action_url": f"{reverse('s3_mgmt_dialog', args=[bucket.resource.id])}?{query}",
        "use_ajax": True,
        "submit": spec["submit"],
    }
    if "form" in spec:
        dialog["form"] = spec["form"](request, bucket)
    content = spec.get("content")
    if content is not None:
        dialog["top_content"] = content(request, bucket) if callable(content) else content
    return dialog


# ── Delete bucket (through a CloudBolt order) ────────────────────────────────

@require_POST
def delete_bucket(request, resource_id):
    """Submit the delete order; nothing is deleted until it is approved."""
    bucket = _get_bucket(request, resource_id)
    profile = request.get_user_profile()
    if not models.Authorization.can_delete_bucket(profile):
        bucket.record(f"Deletion of this S3 bucket was refused: {profile} is "
                      f"not authorized to request bucket deletion.",
                      profile=profile)
        raise Http404("Not authorized to request bucket deletion")
    state = _browser_state(request)
    form = forms.DeleteBucketForm(request.POST, bucket_name=bucket.name)
    if not form.is_valid():
        return _reject(request, form, bucket, state)
    try:
        result = models.get_or_create_delete_action().run_hook_as_job(
            owner=profile, resources=[bucket.resource], context={})
    except Exception as e:
        logger.exception(f"User {profile} failed to submit delete order "
                         f"for S3 bucket: {bucket.name}")
        messages.error(request, f"Could not submit the delete order: {e}")
        return HttpResponseRedirect(_tab_url(bucket.resource, state))
    # run_hook_as_job returns (order, message), or [] when it swallowed a
    # CloudBoltException internally.
    if not isinstance(result, tuple):
        logger.error(f"Delete-bucket order for {bucket.name} returned {result!r}")
        messages.error(request, "CloudBolt did not accept the delete order; "
                                "check the application logs.")
        return HttpResponseRedirect(_tab_url(bucket.resource, state))
    order, _ = result
    logger.info(f"User {profile} submitted order {order.id} to delete "
                f"S3 bucket: {bucket.name}")
    bucket.record(
        f"Deletion of this S3 bucket was requested by {profile} — "
        f'<a href="{order.get_absolute_url()}">Order #{order.id}</a> '
        f"({order.status}). The bucket is emptied and deleted only once the "
        f"order is approved.", profile=profile)
    messages.success(request, (
        f"Order #{order.id} created and awaiting approval."
        if order.status == "PENDING"
        else f"Order #{order.id} was auto-approved and is running."))
    return HttpResponseRedirect(order.get_absolute_url())


# ── Admin extension ──────────────────────────────────────────────────────────

@admin_extension(
    title="S3 File Manager Admin",
    description="Active configuration and S3 bucket resource inventory for the "
                "S3 File Manager XUI")
def s3_mgmt_admin_panel(request):
    """Tunables, bucket inventory and per-group authorization. Super admins only."""
    profile = request.get_user_profile()
    if not profile.super_admin:
        return HttpResponse("Permission denied: super admin required.")
    config = [
        ("S3_RESOURCE_TYPE", models.S3_RESOURCE_TYPE,
         "ResourceType name that identifies S3 bucket resources."),
        ("AWS_RH_ID_FIELD", models.AWS_RH_ID_FIELD,
         "Per-bucket custom field naming the owning AWS Resource Handler — "
         "see the inventory below for the actual mapping."),
        ("REGION_FIELD", models.REGION_FIELD,
         "Optional per-bucket region field; else the location is looked up."),
        ("DEFAULT_REGION", models.DEFAULT_REGION,
         "Assumed when AWS reports no LocationConstraint."),
        ("PRESIGNED_URL_EXPIRATION", models.PRESIGNED_URL_EXPIRATION,
         "Lifetime (seconds) of download URLs."),
        ("PROMOTE_VERSION_SLEEP_SECONDS", models.PROMOTE_VERSION_SLEEP_SECONDS,
         "Wait after copy before deleting the source version on promote."),
        ("DELETE_BATCH_SIZE", models.DELETE_BATCH_SIZE,
         "Max keys per delete_objects call (S3 API limit)."),
        ("DATE_FORMAT", models.DATE_FORMAT, "Object timestamp display format."),
    ]
    group_ids = models.Authorization.group_ids()
    buckets = []
    for resource in _dedup_by_name(_bucket_queryset(profile).select_related("group")):
        rh_id = resource.get_value_for_custom_field(models.AWS_RH_ID_FIELD)
        buckets.append({
            "resource": resource,
            "handler": AWSHandler.objects.filter(pk=rh_id).first() if rh_id else None,
            "region": resource.get_value_for_custom_field(models.REGION_FIELD)})
    return render(request, "s3_file_manager/templates/admin_panel.html", {
        "uplink": {"url": reverse("admin_home"), "label": "Admin"},
        "connection_info_name": models.Authorization.CONNECTION_INFO_NAME,
        "config": config,
        "buckets": buckets,
        "all_groups": Group.objects.order_by("name"),
        "permissions_edit_group_ids": group_ids[models.Authorization.PERMISSIONS_EDIT_KEY],
        "delete_bucket_group_ids": group_ids[models.Authorization.DELETE_BUCKET_KEY],
    })


@require_POST
def save_admin_settings(request):
    """Persist the group authorization mappings. Super admins only."""
    profile = request.get_user_profile()
    if not profile.super_admin:
        return HttpResponse("Permission denied: super admin required.")
    valid_ids = set(Group.objects.values_list("id", flat=True))

    def _clean(field):
        ids = []
        for raw in request.POST.getlist(field):
            try:
                gid = int(raw)
            except (TypeError, ValueError):
                continue
            if gid in valid_ids:
                ids.append(gid)
        return ids

    models.Authorization.save(
        permissions_edit_group_ids=_clean("permissions_edit_groups"),
        delete_bucket_group_ids=_clean("delete_bucket_groups"))
    logger.info(f"User {profile} updated S3 browser group authorizations")
    messages.success(request, "S3 File Manager authorization saved.")
    return redirect(reverse("render_admin_extension",
                            args=["s3_file_manager", "s3_mgmt_admin_panel"]))
