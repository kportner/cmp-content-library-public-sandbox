"""
The non-HTTP half of the S3 File Manager XUI: tunables, the Authorization
store, the S3Bucket wrapper (all AWS work + audit), and the delete-bucket
plug-in entry points. views.py holds the request/response layer.
"""

import json
import os
import time

import boto3
import botocore
from botocore.exceptions import ClientError

from common.methods import set_progress
from django.template.defaultfilters import filesizeformat
from resourcehandlers.aws.models import AWSHandler
from utilities.events import add_resource_event
from utilities.logger import ThreadLogger
from utilities.models import ConnectionInfo

logger = ThreadLogger(__name__)


# ── Tunables — edit here, then restart Apache ────────────────────────────────

# ResourceType.name that identifies S3 bucket resources in CMP.
S3_RESOURCE_TYPE = "s3_bucket"
# Custom field on each bucket resource holding its AWS Resource Handler id.
AWS_RH_ID_FIELD = "aws_rh_id"
# Optional custom field holding the bucket region; else looked up from AWS.
REGION_FIELD = "s3_bucket_region"
# Optional custom field holding a short note/icon shown next to the bucket name.
NOTE_FIELD = "s3_bucket_note"
NOTE_ICON_MAX_LENGTH = 4
NOTE_MAX_LENGTH = 300
# Assumed when AWS reports no LocationConstraint.
DEFAULT_REGION = "us-east-1"
# Lifetime (seconds) of presigned download URLs.
PRESIGNED_URL_EXPIRATION = 3600
# Wait after copy before deleting the source version on promote.
PROMOTE_VERSION_SLEEP_SECONDS = 5
# delete_objects accepts at most 1000 keys per request (S3 API limit).
DELETE_BATCH_SIZE = 1000
# Display format for object timestamps.
DATE_FORMAT = "%B %d, %Y, %I:%M %p"
# Canned ACLs offered by the permissions dialog.
CANNED_BUCKET_ACLS = ["private", "public-read", "public-read-write",
                      "authenticated-read"]


class MissingHandler(Exception):
    """The bucket resource has no usable AWS Resource Handler."""


class Authorization:
    """Who may change permissions / request deletion: super admins, plus members
    of the groups stored as JSON in one ConnectionInfo row's description."""

    CONNECTION_INFO_NAME = "S3 File Manager Authorization"
    PERMISSIONS_EDIT_KEY = "permissions_edit_group_ids"
    DELETE_BUCKET_KEY = "delete_bucket_group_ids"

    @classmethod
    def group_ids(cls):
        """Both lists, keyed by the *_KEY constants. Bad JSON = unconfigured."""
        record = ConnectionInfo.objects.filter(name=cls.CONNECTION_INFO_NAME).first()
        try:
            data = json.loads(record.description) if record and record.description else {}
        except ValueError:
            logger.warning(f"{cls.CONNECTION_INFO_NAME} description is not valid "
                           f"JSON; authorizing super admins only")
            data = {}
        if not isinstance(data, dict):
            data = {}
        return {key: [gid for gid in data.get(key) or [] if isinstance(gid, int)]
                for key in (cls.PERMISSIONS_EDIT_KEY, cls.DELETE_BUCKET_KEY)}

    @classmethod
    def save(cls, permissions_edit_group_ids, delete_bucket_group_ids):
        """Replace both lists in the backing row."""
        # The built-in Connection Info dialog requires IP/Hostname, so seed a
        # placeholder host on create.
        record, _ = ConnectionInfo.objects.get_or_create(
            name=cls.CONNECTION_INFO_NAME,
            defaults={"protocol": "https", "ip": "s3.amazonaws.com"})
        record.description = json.dumps({
            cls.PERMISSIONS_EDIT_KEY: permissions_edit_group_ids,
            cls.DELETE_BUCKET_KEY: delete_bucket_group_ids}, indent=2)
        record.save()
        logger.info(f"S3 authorization saved: edit={permissions_edit_group_ids}, "
                    f"delete={delete_bucket_group_ids}")
        return record

    @classmethod
    def can_edit_permissions(cls, profile):
        return cls._allowed(profile, cls.PERMISSIONS_EDIT_KEY)

    @classmethod
    def can_delete_bucket(cls, profile):
        return cls._allowed(profile, cls.DELETE_BUCKET_KEY)

    @classmethod
    def _allowed(cls, profile, key):
        if profile is None:
            return False
        if profile.super_admin:
            return True
        allowed_ids = cls.group_ids()[key]
        return bool(allowed_ids) and profile.get_groups().filter(
            id__in=allowed_ids).exists()


class S3Bucket:
    """One S3 bucket, addressed through its CloudBolt Resource.

    All boto3 work and the audit entries live here; views never touch AWS.
    """

    # Friendly names for the predefined grantee groups AWS uses in ACLs.
    ACL_GROUP_LABELS = {
        "http://acs.amazonaws.com/groups/global/AllUsers": "Everyone (public)",
        "http://acs.amazonaws.com/groups/global/AuthenticatedUsers":
            "Any authenticated AWS user",
        "http://acs.amazonaws.com/groups/s3/LogDelivery": "S3 log delivery group",
    }

    def __init__(self, resource):
        self.resource = resource
        self.name = resource.name
        self._handler = None
        self._region = None
        self._client = None

    # ── connection ──

    @property
    def handler(self):
        if self._handler is None:
            rh_id = self.resource.get_value_for_custom_field(AWS_RH_ID_FIELD)
            self._handler = AWSHandler.objects.filter(pk=rh_id).first() if rh_id else None
            if self._handler is None:
                raise MissingHandler(f"No AWS handler is set on this resource "
                                     f"(custom field '{AWS_RH_ID_FIELD}').")
        return self._handler

    @property
    def region(self):
        """The region custom field, else the bucket's real location."""
        if self._region is None:
            self._region = self.resource.get_value_for_custom_field(REGION_FIELD)
        if self._region:
            return self._region
        try:
            location = self._connect(DEFAULT_REGION).get_bucket_location(
                Bucket=self.name)
            region = location.get("LocationConstraint")
            if region == "EU":  # legacy value on pre-2009 eu-west-1 buckets
                region = "eu-west-1"
            self._region = region or DEFAULT_REGION  # us-east-1 reports None
        except Exception:
            logger.exception(f"Could not determine region for {self.name}")
            self._region = DEFAULT_REGION
        return self._region

    @property
    def client(self):
        if self._client is None:
            self._client = self._connect(self.region)
        return self._client

    def _connect(self, region):
        # Signature v4 explicitly, so presigned URLs work in every region.
        return boto3.client(
            "s3",
            aws_access_key_id=self.handler.serviceaccount,
            aws_secret_access_key=self.handler.servicepasswd,
            region_name=region,
            config=botocore.client.Config(signature_version="s3v4"))

    # ── audit ──

    def record(self, message, profile=None, job=None, event_type="INFO"):
        """One ResourceHistory row on this bucket's History tab."""
        add_resource_event(event_type, self.resource, message,
                           profile=profile, job=job)

    @staticmethod
    def describe_keys(keys):
        """A few key names for a history message, without unbounded growth."""
        shown = ", ".join(keys[:5])
        return f"{shown} and {len(keys) - 5} more" if len(keys) > 5 else shown

    # ── reads ──

    @property
    def versioning(self):
        """"Enabled", "Suspended" (history remains!) or "" (never enabled)."""
        try:
            return self.client.get_bucket_versioning(Bucket=self.name).get("Status") or ""
        except Exception:
            logger.exception(f"Could not read versioning status of {self.name}")
            return ""

    @property
    def note(self):
        return self.resource.get_value_for_custom_field(NOTE_FIELD) or ""

    def save_note(self, value):
        from infrastructure.models import CustomField
        CustomField.objects.get_or_create(
            name=NOTE_FIELD,
            defaults={
                "label": "S3 Bucket Note",
                "description": "Short note or icon shown in the S3 File Manager tab",
                "type": "STR",
                "required": False,
                "show_on_servers": False,
            })
        self.resource.set_value_for_custom_field(NOTE_FIELD, value)

    def presigned_url(self, key, version_id=None):
        """Presigned GET URL, or None when signing fails."""
        params = {"Bucket": self.name, "Key": key}
        if version_id:
            params["VersionId"] = version_id
        try:
            return self.client.generate_presigned_url(
                "get_object", Params=params, ExpiresIn=PRESIGNED_URL_EXPIRATION)
        except botocore.exceptions.ClientError:
            logger.exception(f"Could not presign URL for {self.name}/{key}")
            return None

    def list_folder(self, prefix, flat=False, show_deleted=False):
        """One folder's entries: folders first, files with version history.

        Deleted objects (latest version = delete marker) are omitted unless
        `show_deleted`. `flat` lists every key beneath the prefix by full key.
        """
        delimiter = "" if flat else "/"
        paginator = self.client.get_paginator("list_object_versions")
        versions_by_key, common_prefixes, seen = {}, [], set()
        for page in paginator.paginate(Bucket=self.name, Prefix=prefix,
                                       Delimiter=delimiter):
            for obj in page.get("Versions", []):
                if obj.get("Key") != prefix:
                    versions_by_key.setdefault(obj["Key"], []).append(
                        self._version_dict(obj, False))
            for marker in page.get("DeleteMarkers", []):
                if marker.get("Key") != prefix:
                    versions_by_key.setdefault(marker["Key"], []).append(
                        self._version_dict(marker, True))
            for cp in page.get("CommonPrefixes", []):
                if cp["Prefix"] not in seen:
                    seen.add(cp["Prefix"])
                    common_prefixes.append(cp["Prefix"])

        entries = []
        for key, versions in versions_by_key.items():
            # Keys ending in "/" are folder placeholders; non-flat mode already
            # reports folders via CommonPrefixes.
            is_file = not key.endswith("/")
            if not is_file and not flat:
                continue
            versions.sort(key=lambda v: v["last_modified_iso"], reverse=True)
            latest = next((v for v in versions if v["is_latest"]), versions[0])
            if latest["is_delete_marker"] and not show_deleted:
                continue
            name = key if flat else key.split("/")[-1] or key.rstrip("/").split("/")[-1]
            entries.append({
                "key": key, "name": name, "is_file": is_file,
                "item_type": self._file_type(name) if is_file else "Folder",
                "is_deleted": latest["is_delete_marker"],
                "versions": versions, "version_count": len(versions),
                **{k: v for k, v in latest.items() if k not in ("is_latest",)},
            })

        if not flat:
            # CommonPrefixes hide the keys beneath them, so folder deleted-state
            # needs a second, non-delimited listing.
            live, dead = set(), set()
            if common_prefixes:
                for page in paginator.paginate(Bucket=self.name, Prefix=prefix):
                    for m in page.get("DeleteMarkers", []):
                        if m.get("IsLatest"):
                            dead.add(m["Key"])
                    for o in page.get("Versions", []):
                        if o.get("IsLatest"):
                            live.add(o["Key"])
            for folder in common_prefixes:
                deleted = (any(k.startswith(folder) for k in dead)
                           and not any(k.startswith(folder) for k in live))
                if deleted and not show_deleted:
                    continue
                entries.append({
                    "key": folder,
                    # An S3 key may start with "/": the prefix "/" trims to an
                    # empty name, so fall back to the raw prefix.
                    "name": folder[len(prefix):].rstrip("/") or folder,
                    "is_file": False, "item_type": "Folder",
                    "is_deleted": deleted, "version_count": 0,
                })

        entries.sort(key=lambda e: (e["is_file"], str(e["name"]).lower()))
        return entries

    # ── writes ──

    def create_folder(self, prefix, name):
        """A folder is a zero-byte key ending in "/". Returns the key."""
        key = f"{prefix}{name}/"
        self.client.put_object(Bucket=self.name, Key=key)
        return key

    def upload(self, prefix, files, rel_paths):
        """Upload files under prefix (multipart for big ones), keeping relative paths."""
        keys = []
        for index, item in enumerate(files):
            rel = rel_paths[index] if index < len(rel_paths) else item.name
            key = f"{prefix}{rel.lstrip('/')}"
            self.client.upload_fileobj(item, self.name, key)
            keys.append(key)
        return keys

    def delete(self, keys):
        """Delete keys, expanding folder prefixes recursively. Returns them all.

        Raises if any key fails to delete (e.g. Object Lock) instead of
        silently reporting success — delete_objects itself never raises.
        """
        expanded = []
        for key in keys:
            expanded.extend(self._iter_keys(key) if key.endswith("/") else [key])
        errors = []
        for start in range(0, len(expanded), DELETE_BATCH_SIZE):
            batch = expanded[start:start + DELETE_BATCH_SIZE]
            response = self.client.delete_objects(Bucket=self.name, Delete={
                "Objects": [{"Key": k} for k in batch], "Quiet": True})
            errors.extend(response.get("Errors", []))
        if errors:
            raise RuntimeError(
                f"{len(errors)} of {len(expanded)} object(s) could not be deleted: "
                + "; ".join(f"{e['Key']}: {e.get('Message')}" for e in errors[:5]))
        return expanded

    def rename(self, old_key, new_name):
        """S3 has no rename: copy then delete. A folder moves every key under it.

        Returns (new_key, moved_count); moved_count is None for a single object.
        """
        stem = old_key.rstrip("/")
        parent = f"{stem.rsplit('/', 1)[0]}/" if "/" in stem else ""
        is_folder = old_key.endswith("/")
        new_key = f"{parent}{new_name.strip('/')}{'/' if is_folder else ''}"
        if not is_folder:
            self.client.copy(CopySource={"Bucket": self.name, "Key": old_key},
                             Bucket=self.name, Key=new_key)
            self.client.delete_object(Bucket=self.name, Key=old_key)
            return new_key, None
        keys = list(self._iter_keys(old_key))
        for key in keys:
            self.client.copy(CopySource={"Bucket": self.name, "Key": key},
                             Bucket=self.name, Key=f"{new_key}{key[len(old_key):]}")
        self.delete([old_key])
        return new_key, len(keys)

    def enable_versioning(self):
        """S3 can later suspend versioning, never remove it."""
        self.client.put_bucket_versioning(
            Bucket=self.name, VersioningConfiguration={"Status": "Enabled"})

    def promote_version(self, key, version_id):
        """Copy an old version to the top of the stack, then drop the source."""
        self.client.copy_object(
            Bucket=self.name, Key=key,
            CopySource={"Bucket": self.name, "Key": key, "VersionId": version_id})
        # S3 needs a moment before the copy is listed as latest.
        time.sleep(PROMOTE_VERSION_SLEEP_SECONDS)
        self.client.delete_object(Bucket=self.name, Key=key, VersionId=version_id)

    def delete_version(self, key, version_id):
        """Permanently delete one version/marker. Returns False if already gone."""
        exists = any(
            v.get("VersionId") == version_id
            for page in self.client.get_paginator("list_object_versions").paginate(
                Bucket=self.name, Prefix=key)
            for v in page.get("Versions", []) + page.get("DeleteMarkers", []))
        if not exists:
            return False
        self.client.delete_object(Bucket=self.name, Key=key, VersionId=version_id)
        return True

    def empty(self):
        """Delete every version and marker. Returns (deleted_count, errors).

        Per-key failures (e.g. Object Lock) don't raise — Quiet mode reports
        them only in the response's "Errors" list.
        """
        deleted, errors = 0, []
        for page in self.client.get_paginator("list_object_versions").paginate(
                Bucket=self.name):
            targets = [{"Key": v["Key"], "VersionId": v["VersionId"]}
                       for section in ("Versions", "DeleteMarkers")
                       for v in page.get(section, [])]
            for start in range(0, len(targets), DELETE_BATCH_SIZE):
                batch = targets[start:start + DELETE_BATCH_SIZE]
                response = self.client.delete_objects(
                    Bucket=self.name, Delete={"Objects": batch, "Quiet": True})
                errors.extend(response.get("Errors", []))
                deleted += len(batch) - len(response.get("Errors", []))
        return deleted, errors

    def destroy(self):
        self.client.delete_bucket(Bucket=self.name)

    def retire(self, message, job=None):
        """Mark the resource HISTORICAL and record why, who and which order.

        The requester also goes into the message text: the history owner FK is
        SET_NULL, so the audit must survive the user being deleted.
        """
        self.resource.lifecycle = "HISTORICAL"
        self.resource.save(update_fields=["lifecycle"])
        requester = getattr(job, "owner", None)
        order = job.get_order() if job else None
        parts = [message, f"Requested by {requester}." if requester else ""]
        if order is not None:
            parts.append(f'Approved order: <a href="{order.get_absolute_url()}">'
                         f'Order #{order.id}</a>.')
        self.record(" ".join(p for p in parts if p),
                    profile=requester, job=job, event_type="DECOMMISSION")

    def confirm_missing(self):
        """True only when AWS confirms the bucket itself no longer exists."""
        try:
            self.client.head_bucket(Bucket=self.name)
            return False
        except botocore.exceptions.ClientError as e:
            return e.response.get("Error", {}).get("Code") in ("404", "NoSuchBucket")
        except Exception:
            return False

    # ── permissions ──

    @property
    def policy(self):
        """The policy JSON string, or None when none is attached."""
        try:
            return self.client.get_bucket_policy(Bucket=self.name)["Policy"]
        except botocore.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchBucketPolicy":
                return None
            raise

    @property
    def policy_is_public(self):
        """AWS's own verdict; None when there is no policy."""
        try:
            status = self.client.get_bucket_policy_status(Bucket=self.name)
            return status["PolicyStatus"].get("IsPublic", False)
        except botocore.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchBucketPolicy":
                return None
            raise

    @property
    def acl(self):
        """{"owner": ..., "grants": [{grantee, grantee_type, permission}]}."""
        response = self.client.get_bucket_acl(Bucket=self.name)
        grants = []
        for grant in response.get("Grants", []):
            grantee = grant.get("Grantee", {})
            uri = grantee.get("URI")
            grants.append({
                "permission": grant.get("Permission"),
                "grantee_type": grantee.get("Type"),
                "grantee": (self.ACL_GROUP_LABELS.get(uri, uri)
                            or grantee.get("DisplayName") or grantee.get("ID")
                            or grantee.get("EmailAddress")),
            })
        owner = response.get("Owner", {})
        return {"owner": owner.get("DisplayName") or owner.get("ID"),
                "grants": grants}

    @property
    def acls_enabled(self):
        """False when Object Ownership is "Bucket owner enforced" — AWS then
        refuses every put_bucket_acl (the default since April 2023)."""
        try:
            rules = self.client.get_bucket_ownership_controls(
                Bucket=self.name)["OwnershipControls"]["Rules"]
        except botocore.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "OwnershipControlsNotFoundError":
                return True
            raise
        return all(r.get("ObjectOwnership") != "BucketOwnerEnforced" for r in rules)

    @property
    def public_access_block(self):
        """The four flags; all False when never configured."""
        try:
            return self.client.get_public_access_block(
                Bucket=self.name)["PublicAccessBlockConfiguration"]
        except botocore.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchPublicAccessBlockConfiguration":
                return {"BlockPublicAcls": False, "IgnorePublicAcls": False,
                        "BlockPublicPolicy": False, "RestrictPublicBuckets": False}
            raise

    def save_public_access_block(self, flags):
        self.client.put_public_access_block(
            Bucket=self.name, PublicAccessBlockConfiguration=flags)

    def apply_canned_acl(self, canned_acl):
        self.client.put_bucket_acl(Bucket=self.name, ACL=canned_acl)

    def save_policy(self, document):
        """Takes parsed JSON; S3 wants the document as a string."""
        self.client.put_bucket_policy(Bucket=self.name, Policy=json.dumps(document))

    def delete_policy(self):
        self.client.delete_bucket_policy(Bucket=self.name)

    # ── private ──

    def _iter_keys(self, prefix):
        """Every key under a prefix, paginated past the 1000-key cap."""
        for page in self.client.get_paginator("list_objects_v2").paginate(
                Bucket=self.name, Prefix=prefix):
            for obj in page.get("Contents", []):
                yield obj["Key"]

    def _version_dict(self, obj, is_delete_marker):
        last_modified = obj.get("LastModified")
        entry = {
            "version_id": obj.get("VersionId"),
            "is_latest": obj.get("IsLatest", False),
            "is_delete_marker": is_delete_marker,
            "last_modified": last_modified.strftime(DATE_FORMAT) if last_modified else "",
            "last_modified_iso": last_modified.isoformat() if last_modified else "",
        }
        if is_delete_marker:
            return {**entry, "size": "Deleted", "storage_class": None,
                    "type": "Delete Marker"}
        return {**entry,
                "size": filesizeformat(obj.get("Size", 0)),
                "actual_size": obj.get("Size"),
                "storage_class": (obj.get("StorageClass") or "").title(),
                "type": self._file_type(obj.get("Key", ""))}

    @staticmethod
    def _file_type(key):
        return key.rsplit(".", 1)[-1] if "." in key else "No extension"


# ── CloudBolt plug-in entry points — resolved by name, so module-level ───────

def run(job, resource=None, resources=None, **kwargs):
    """Empty and delete the bucket, then retire the CMP resource."""
    if resource is None and resources is not None:
        resource = resources.first()
    if resource is None:
        return "FAILURE", "", "No resource was passed to the plug-in."

    # A ResourceAction is reachable through the normal UI and API no matter how
    # the XUI gates its endpoints — re-validate type and requester here.
    resource_type = getattr(resource, "resource_type", None)
    if not resource_type or resource_type.name != S3_RESOURCE_TYPE:
        return ("FAILURE", "", f"Refusing to run: resource {resource.name} is "
                               f"not of type '{S3_RESOURCE_TYPE}'.")
    requester = getattr(job, "owner", None)
    bucket = S3Bucket(resource)
    if not Authorization.can_delete_bucket(requester):
        bucket.record(f"S3 bucket deletion refused: {requester} is not "
                      f"authorized (see the S3 File Manager Admin page).",
                      profile=requester, job=job)
        return ("FAILURE", "", f"Refusing to run: user {requester} is not "
                               f"authorized to delete S3 buckets.")

    try:
        bucket.handler
    except MissingHandler:
        # Nothing to delete in AWS; still retire so it doesn't linger.
        bucket.retire(f"Resource retired in CMP without deleting anything in "
                      f"AWS: no AWS handler is set on it (custom field "
                      f"'{AWS_RH_ID_FIELD}').", job=job)
        return ("WARNING", f"Resource {bucket.name} retired in CMP.",
                f"No AWS handler found via custom field '{AWS_RH_ID_FIELD}'.")

    try:
        set_progress(f"Emptying S3 bucket {bucket.name}...")
        deleted, errors = bucket.empty()
        if errors:
            sample = "; ".join(f"{e.get('Key')} ({e.get('Code')}: {e.get('Message')})"
                               for e in errors[:5])
            bucket.record(f"S3 bucket deletion failed: {len(errors)} object(s) "
                          f"could not be deleted (e.g. Object Lock); the bucket "
                          f"was left in place. First failures: {sample}",
                          profile=requester, job=job)
            return ("FAILURE", "", f"{len(errors)} object(s) in {bucket.name} "
                                   f"could not be deleted. {sample}")
        set_progress(f"Deleted {deleted} version(s); deleting {bucket.name}...")
        bucket.destroy()
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchBucket", "404"):
            bucket.retire(f"Resource retired in CMP: bucket {bucket.name} no "
                          f"longer existed in AWS.", job=job)
            return ("WARNING", f"Bucket {bucket.name} no longer exists in AWS; "
                               f"resource retired in CMP.", "")
        logger.exception(f"Failed to delete S3 bucket {bucket.name}")
        bucket.record(f"S3 bucket deletion failed with an AWS error; bucket and "
                      f"resource left in place: {e}", profile=requester, job=job)
        return "FAILURE", "", f"AWS error deleting {bucket.name}: {e}"

    bucket.retire(f"S3 bucket {bucket.name} was emptied ({deleted} object "
                  f"version(s) removed) and deleted in AWS; this resource is "
                  f"now retired.", job=job)
    set_progress(f"S3 bucket {bucket.name} deleted.")
    return "SUCCESS", f"S3 bucket {bucket.name} deleted.", ""


def should_display(resource=None, request=None):
    """Always False: the tab's dialog is the only entry point; run() re-checks
    authorization, so hiding the action costs no security."""
    return False


def get_or_create_delete_action():
    """Idempotently provision the delete-bucket hook rows + ResourceAction.
    requires_approval + auto_submit_order turn every run into an approval Order;
    the always-False condition keeps it out of every resource's action list."""
    # Imported here: this module loads during app-registry population.
    from cbhooks.models import CloudBoltHook, ResourceAction
    from servicecatalog.models import ServiceBlueprint

    import xui.s3_file_manager as package
    # Not __file__: CloudBolt's plug-in loader execs this file without one.
    module_path = os.path.join(os.path.dirname(package.__file__), "models.py")

    rows = []
    for name, description in (
        ("S3 File Manager: Delete Bucket",
         "Empties and deletes an S3 bucket, then retires the CMP resource. "
         "Created by the S3 File Manager XUI."),
        ("S3 File Manager: Delete Bucket Condition",
         "Display condition keeping the delete-bucket action out of every "
         "resource's action list. Created by the S3 File Manager XUI."),
    ):
        row, created = CloudBoltHook.objects.get_or_create(
            name=name, defaults={"module_file": module_path, "shared": False,
                                 "description": description})
        # A stale module_file (package moved) fails silently at run time.
        if not created and row.module_file != module_path:
            row.module_file = module_path
            row.save(update_fields=["module_file"])
        rows.append(row)
    hook, condition_hook = rows

    action, _ = ResourceAction.objects.get_or_create(
        label="Delete S3 Bucket (S3 File Manager)", hook=hook,
        defaults={"enabled": True, "requires_approval": True,
                  "auto_submit_order": True, "dangerous": True,
                  "targets": ["default"],
                  "dialog_message": "Permanently deletes the bucket and ALL of "
                                    "its contents once the order is approved."})
    updates = {}
    if not action.enabled:
        action.enabled = True
        updates["enabled"] = True
    if action.condition_id != condition_hook.id:
        action.condition = condition_hook
        updates["condition"] = condition_hook
    if updates:
        action.save(update_fields=list(updates))
    s3_blueprints = ServiceBlueprint.objects.filter(
        resource_type__name=S3_RESOURCE_TYPE)
    if s3_blueprints.exists():
        action.blueprints.set(s3_blueprints)
    return action
