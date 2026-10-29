from django.db.models import CharField, Value
from django.db.models.functions import Concat, Substr
from django.template.defaultfilters import pluralize
from django.utils.translation import gettext as _
from accounts.models import Group, UserProfile
from resources.forms import ResourceChangeAttributesValidationHelper
from infrastructure.helper_functions import check_permitted_action_on_resources
from resources.models import Resource
from utilities import events
from utilities.models import GlobalPreferences
from utilities.logger import ThreadLogger

logger = ThreadLogger(__name__)


def generate_options_for_owner(resource=None, resources=None, profile=None, **kwargs):
    """
    Generate the options for the owner field in the change attributes dialog.

    User options are labeled according to the global default user display scheme
    (full_name, first_initial_last, username, or last_first) and are scoped to
    the acting profile.

    Args:
        resource (Resource, optional): The single resource being edited, used
            to set the initial owner value.
        resources (list, optional): The resources being edited in bulk.
        profile (UserProfile, optional): The acting user, used to scope which
            users are shown.
        **kwargs: Additional keyword arguments (unused).

    Returns:
        dict: Field options. Contains ``{"hidden": True}`` when there is no
        resource(s) or profile; otherwise an ``options`` list of (id, label)
        tuples plus an ``initial_value`` (and, for the no-resource case, a "---"
        placeholder and ``required``: False).
    """
    if (not resource and not resources) or not profile:
        return {"hidden": True}

    user_display_option = (
        GlobalPreferences.get().default_user_display_scheme or "username"
    )

    userprofile_qs = UserProfile.objects_for_profile(profile).filter(
        user__is_active=True
    )

    if user_display_option == "full_name":
        options = list(
            userprofile_qs.annotate(
                full_name=Concat(
                    "user__first_name",
                    Value(" "),
                    "user__last_name",
                    output_field=CharField(),
                )
            )
            .order_by("full_name")
            .values_list("id", "full_name")
        )
    elif user_display_option == "first_initial_last":
        options = list(
            userprofile_qs.annotate(
                first_initial_last=Concat(
                    Substr("user__first_name", 1, 1),
                    Value(". "),
                    "user__last_name",
                )
            )
            .order_by("first_initial_last")
            .values_list("id", "first_initial_last")
        )
    elif user_display_option == "username":
        options = list(
            userprofile_qs.order_by("user__username").values_list(
                "id", "user__username"
            )
        )
    elif user_display_option == "last_first":
        options = list(
            userprofile_qs.annotate(
                last_first=Concat(
                    "user__last_name",
                    Value(", "),
                    "user__first_name",
                    output_field=CharField(),
                )
            )
            .order_by("last_first")
            .values_list("id", "last_first")
        )

    ret = {"options": options}
    if resource and resource.owner and resource.owner.id in dict(options):
        initial = (
            resource.owner.id,
            dict(options)[resource.owner.id],
        )
        ret["initial_value"] = initial
    if not resource:
        ret["options"].insert(0, (None, "---"))
        ret["initial_value"] = (None, "---")
        ret["required"] = False

    return ret


def generate_options_for_group(resource=None, resources=None, profile=None, **kwargs):
    """
    Generate the options for the group field in the change attributes dialog.

    Args:
        resource (Resource, optional): The single resource being edited, used
            to set the initial group value.
        resources (list, optional): The resources being edited in bulk.
        profile (UserProfile, optional): The acting user, used to scope which
            groups are shown.
        **kwargs: Additional keyword arguments (unused).

    Returns:
        dict: Field options. Contains ``{"hidden": True}`` when there is no
        resource(s) or profile; otherwise an ``options`` list of (id, name)
        tuples plus an ``initial_value`` (and, for the no-resource case, a "---"
        placeholder and ``required``: False).
    """
    if (not resource and not resources) or not profile:
        return {"hidden": True}
    ret = {
        "options": list(Group.objects_for_profile(profile).values_list("id", "name"))
    }
    if resource:
        initial = (resource.group.id, resource.group.name)
        if initial not in ret["options"]:
            ret["options"].append(initial)
        ret["initial_value"] = initial
    else:
        ret["options"].insert(0, (None, "---"))
        ret["initial_value"] = (None, "---")
        ret["required"] = False
    return ret


def get_current_status_choice(resource):
    """
    Return the (slug, display name) choice matching the resource's lifecycle.

    Args:
        resource (Resource): The resource whose lifecycle choice is looked up.

    Returns:
        Tuple[Optional[str], str]: The matching (slug, ui_facing_name) tuple
        from ``Resource.RESOURCE_LIFECYCLE_CHOICES``, or (None, "Unrecognized
        Status") if no choice matches.
    """
    for slug, ui_facing_name in Resource.RESOURCE_LIFECYCLE_CHOICES:
        if resource.lifecycle == slug:
            return slug, ui_facing_name
    return None, "Unrecognized Status"


def generate_options_for_lifecycle(resource=None, resources=None, **kwargs):
    """
    Generate the options for the lifecycle field in the dialog.

    Offers only the ACTIVE and HISTORICAL lifecycle choices; the resource's
    current lifecycle is added and used as the initial value if not already
    present.

    Args:
        resource (Resource, optional): The single resource being edited, used
            to set the initial lifecycle value.
        resources (list, optional): The resources being edited in bulk.
        **kwargs: Additional keyword arguments (unused).

    Returns:
        dict: Field options. Contains ``{"hidden": True}`` when there is no
        resource(s); otherwise an ``options`` list of lifecycle choices plus an
        ``initial_value`` (and, for the no-resource case, a "---" placeholder
        and ``required``: False).
    """
    if not resource and not resources:
        return {"hidden": True}
    status_options = ["ACTIVE", "HISTORICAL"]
    ret = {}

    status_choices = [
        choice
        for choice in Resource.RESOURCE_LIFECYCLE_CHOICES
        if choice[0] in status_options
    ]
    ret["options"] = status_choices
    if resource:
        current_status_choice = get_current_status_choice(resource)
        if current_status_choice not in ret["options"]:
            ret["options"].append(current_status_choice)
        ret["initial_value"] = current_status_choice

    if not resource:
        ret["options"].insert(0, (None, "---"))
        ret["initial_value"] = (None, "---")
        ret["required"] = False
    return ret


def update_resource(kwargs, profile, resource) -> int:
    """
    Apply the submitted attribute changes to a single resource.

    Updates the resource's owner and group foreign keys and its lifecycle where
    the submitted values differ from the current ones, saves the resource, and
    records a MODIFICATION event.

    Args:
        kwargs (dict): The submitted field values (owner, group, lifecycle).
        profile (UserProfile): The acting user, recorded on the event.
        resource (Resource): The resource to update.

    Returns:
        int: The number of fields that were changed.
    """
    field_count = 0
    event_strings = []
    for fk_attr_name in [
        "owner",
        "group",
    ]:
        new_val = kwargs.get(fk_attr_name)
        if new_val:
            new_val = int(new_val)
            if new_val == getattr(resource, fk_attr_name + "_id"):
                # no change
                continue
            setattr(resource, fk_attr_name + "_id", new_val)
            field_count += 1
            event_strings.append(
                _("{attr_label} changed to {value}").format(
                    attr_label=fk_attr_name, value=getattr(resource, fk_attr_name)
                )
            )
    status = kwargs.get("lifecycle")
    if status and status != resource.lifecycle:
        resource.lifecycle = status
        event_strings.append(_("status changed to {value}").format(value=status))
        field_count += 1
    resource.save()

    events.add_resource_event(
        "MODIFICATION",
        resource,
        "\n".join(event_strings),
        profile=profile,
    )

    return field_count


def run(request=None, resource=None, resources=None, profile=None, *args, **kwargs):
    """
    Change attributes on one or more resources, validating submitted values.

    Checks that the profile is permitted to change attributes on the resources,
    validates the submitted owner/group combination (returning a failure result
    without saving if invalid), then updates each resource via
    :func:`update_resource`.

    Args:
        request: The originating request (unused).
        resource (Resource, optional): A single resource to change; promoted
            into ``resources`` if provided.
        resources (list, optional): The resources to change.
        profile (UserProfile, optional): The acting user; required.
        *args: Positional arguments (unused).
        **kwargs: Submitted field values.

    Returns:
        Tuple[str, str, str]: On success, a ("SUCCESS", message, "") tuple; on
        validation failure, a ("FAILURE", errors, message) tuple.

    Raises:
        PermissionError: If no profile is supplied.
    """
    if not profile:
        raise PermissionError(
            "Could not find user profile, which is required to change attributes"
        )

    if resource and not resources:
        resources = [resource]

    check_permitted_action_on_resources(
        profile, "resource.change_attributes", resources
    )

    validation_errors = gather_validation_errors(kwargs)
    if validation_errors:
        return (
            "FAILURE",
            " ".join(validation_errors),
            _("The changes were not saved as the selections were not valid"),
        )

    for resource in resources:
        field_count = update_resource(kwargs, profile, resource)
    if len(resources) == 1:
        return (
            "SUCCESS",
            _("Updated {} field{} on {}").format(
                field_count, pluralize(field_count), resources[0].name
            ),
            "",
        )
    else:
        return (
            "SUCCESS",
            _("Updated {} field{} on {} resources").format(
                field_count, pluralize(field_count), len(resources)
            ),
            "",
        )


def gather_validation_errors(kwargs):
    """
    Validate the submitted owner/group combination for a resource.

    If a new group is selected together with a new owner, checks that the owner
    is valid for that group.

    Args:
        kwargs (dict): The submitted field values (group, owner).

    Returns:
        List[str]: A list of validation error messages; empty if valid.
    """
    validation_errors = []
    new_group_id = kwargs.get("group")
    new_owner_id = kwargs.get("owner")
    if new_group_id:
        new_group = Group.objects.get(id=new_group_id)
        if new_owner_id:
            is_valid, msg = ResourceChangeAttributesValidationHelper.valid_owner_group(
                UserProfile.objects.get(id=new_owner_id), new_group
            )
            if not is_valid:
                validation_errors.append(msg)

    return validation_errors


# These are here to ensure that when this plug-in code is modified from the
# CB UI, the action inputs and all their attributes are preserved. These are
# defined in cb_minimal.py.
# {{ owner }}
# {{ group }}
# {{ lifecycle }}
