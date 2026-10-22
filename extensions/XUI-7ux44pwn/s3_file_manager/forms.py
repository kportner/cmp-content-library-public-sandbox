"""
C2Forms for the dialogs; @dialog_view (views.action_dialog) renders each one
with crispy inside CloudBolt's own dialog.
"""

import json

from accounts.models import Group
from common.forms import C2Form
from django import forms

from xui.s3_file_manager import models


class _PolicyJSONField(forms.JSONField):
    """Pretty-prints the document; empty instead of "null" when there is none."""

    def prepare_value(self, value):
        if value in (None, ""):
            return ""
        if isinstance(value, str):  # already serialized (e.g. re-shown input)
            return value
        return json.dumps(value, indent=2)


class NewFolderForm(C2Form):
    folder_name = forms.CharField(label="Folder name", max_length=1024)

    def clean_folder_name(self):
        name = self.cleaned_data["folder_name"].strip().strip("/")
        if not name:
            raise forms.ValidationError("Enter a folder name.")
        if "/" in name:
            raise forms.ValidationError("Create one folder at a time (no '/').")
        return name


class RenameForm(C2Form):
    key = forms.CharField(widget=forms.HiddenInput)
    new_object_name = forms.CharField(label="New name", max_length=1024)

    def clean_new_object_name(self):
        name = self.cleaned_data["new_object_name"].strip().lstrip("/")
        if not name:
            raise forms.ValidationError("Enter a new name.")
        return name


class NoteForm(C2Form):
    note = forms.CharField(
        label="Description", required=False,
        widget=forms.TextInput(attrs={"placeholder": "Add a description here"}),
        help_text="A short note, shown next to the bucket name.")

    def clean_note(self):
        value = self.cleaned_data.get("note", "").strip()
        if len(value) > models.NOTE_MAX_LENGTH:
            raise forms.ValidationError(
                f"Keep it to {models.NOTE_MAX_LENGTH} characters or fewer.")
        return value


class _MultiFileInput(forms.ClearableFileInput):
    """Django rejects `multiple` unless the widget opts in (allow_multiple_selected)."""

    allow_multiple_selected = True


class UploadForm(C2Form):
    # Both are optional at the form layer: the view reports "choose a file"
    # itself, because a browser sends nothing at all for an untouched input.
    files = forms.FileField(
        label="Files", required=False,
        widget=_MultiFileInput(attrs={"multiple": True}))
    folder = forms.FileField(
        label="Or a whole folder", required=False,
        widget=_MultiFileInput(attrs={"multiple": True, "webkitdirectory": True}),
        help_text="The folder's structure is preserved.")


class DeleteBucketForm(C2Form):
    confirm_name = forms.CharField(
        label="Type the bucket name to confirm",
        help_text="Everything in the bucket, including every object version, "
                  "is deleted once the order is approved.",
    )

    def __init__(self, *args, bucket_name="", **kwargs):
        super().__init__(*args, **kwargs)
        self.bucket_name = bucket_name

    def clean_confirm_name(self):
        typed = self.cleaned_data["confirm_name"].strip()
        if typed != self.bucket_name:
            raise forms.ValidationError(
                f"Type '{self.bucket_name}' exactly to confirm."
            )
        return typed


class BucketPermissionsForm(C2Form):
    """Block Public Access, canned ACL and policy in one dialog. Only BPA is
    written on every save; ACL/policy only when filled in (no silent wipe)."""

    BlockPublicAcls = forms.BooleanField(
        label="Block new public ACLs", required=False)
    IgnorePublicAcls = forms.BooleanField(
        label="Ignore public ACLs", required=False)
    BlockPublicPolicy = forms.BooleanField(
        label="Block new public bucket policies", required=False)
    RestrictPublicBuckets = forms.BooleanField(
        label="Restrict public bucket access", required=False)
    canned_acl = forms.ChoiceField(
        label="Apply a canned ACL", required=False, choices=[],
        help_text="Leave blank to keep the current ACL.")
    policy = _PolicyJSONField(
        label="Bucket policy (JSON)", required=False,
        widget=forms.Textarea(attrs={"rows": 8, "spellcheck": "false",
                                     "class": "font-monospace"}),
        help_text="Leave blank to keep the policy as it is.")
    delete_policy = forms.BooleanField(
        label="Delete the bucket policy instead", required=False)

    def clean_policy(self):
        value = self.cleaned_data.get("policy")
        if value in (None, ""):
            return None
        if not isinstance(value, dict):
            raise forms.ValidationError(
                "The policy must be a JSON object, e.g. "
                '{"Version": "2012-10-17", "Statement": [...]}.')
        return value

    def __init__(self, *args, acls_enabled=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["canned_acl"].choices = [("", "— keep current —")] + [
            (acl, acl) for acl in models.CANNED_BUCKET_ACLS
        ]
        if not acls_enabled:
            # Object Ownership is "Bucket owner enforced": AWS refuses every
            # put_bucket_acl, so offering the control would only produce errors.
            del self.fields["canned_acl"]


class AssignGroupForm(C2Form):
    group = forms.ModelChoiceField(
        label="Group", queryset=Group.objects.order_by("name"),
        help_text="Group membership controls who can see and manage this bucket.")
