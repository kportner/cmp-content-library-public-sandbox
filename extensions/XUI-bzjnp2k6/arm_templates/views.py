from django.contrib import messages
from django.db.models import ProtectedError, Q
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext as _

from extensions.views import admin_extension
from infrastructure.models import Environment, CustomField
from orders.models import CustomFieldValue
from resources.models import Resource
from servicecatalog.models import ServiceBlueprint
from tabs.views import TabGroup
from tags.models import CloudBoltTag
from utilities.decorators import dialog_view
from utilities.exceptions import CloudBoltException
from utilities.models import ConnectionInfo
from utilities.templatetags import helper_tags
from xui.arm_templates.shared import (
    create_params,
    get_conn_info_type,
    get_arm_from_source,
    add_cfvs_for_field,
    get_supported_conn_info_labels,
)
from xui.arm_templates.forms import NewBlueprintForm, CIForm
from utilities.logger import ThreadLogger

logger = ThreadLogger(__name__)


@dialog_view
def create_arm_blueprint(request):
    action_url = reverse("create_arm_blueprint")

    if request.method == "POST":
        form = NewBlueprintForm(request.POST)
        if form.is_valid():
            blueprint = form.save()
            msg = f"New Azure ARM Template Blueprint Created: {blueprint.name}"
            messages.success(request, msg)
            return HttpResponseRedirect(request.META["HTTP_REFERER"])
    else:
        form = NewBlueprintForm()

    return {
        "title": "Add Azure ARM Template Blueprint",
        "form": form,
        "use_ajax": True,
        "action_url": action_url,
        "submit": "Save",
    }


@dialog_view()
def edit_arm_blueprint(request, blueprint_id):
    blueprint = ServiceBlueprint.objects.get(id=blueprint_id)
    action_url = reverse("edit_arm_blueprint", args=[blueprint_id])

    if request.method == "POST":
        form = NewBlueprintForm(request.POST)
        if form.is_valid():
            form.save()
            msg = f"Azure ARM Template Blueprint ({blueprint.name}) has been updated."
            messages.success(request, msg)
            return HttpResponseRedirect(request.META["HTTP_REFERER"])
    else:
        initial_envs = []
        for i in blueprint.arm_allowed_env_ids.split(","):
            if i == 'all_capable':
                initial_envs.append("all_capable")
            else:
                initial_envs.append(i)
        logger.info(f'arm - initial_envs: {initial_envs}')
        initial = {
            "name": blueprint.name,
            "allowed_environments": initial_envs,
            "resource_type":blueprint.resource_type_id,
            "connection_info": blueprint.arm_conn_info_id,
            "arm_url": blueprint.arm_url,
            "id": blueprint_id,
        }
        form = NewBlueprintForm(initial=initial)

    return {
        "title": "Edit Azure ARM Template Blueprint",
        "form": form,
        "use_ajax": True,
        "action_url": action_url,
        "submit": "Save",
    }


@dialog_view
def delete_arm_blueprint(request, blueprint_id):
    blueprint = ServiceBlueprint.objects.get(id=blueprint_id)
    if request.method == "POST":
        bp_cfs = CustomField.objects.filter(name__startswith=f"arm_{blueprint.id}_")
        for cf in bp_cfs:
            for cfv in cf.customfieldvalue_set.all():
                cfv.delete()
            for cfm in cf.customfieldmapping_set.all():
                cfm.delete()
            for cfr in cf.customfieldrate_set.all():
                cfr.delete()

            cf.delete()

        blueprint.status = "HISTORICAL"
        blueprint.save()
        msg = "The Azure ARM Template Blueprint has been removed."
        messages.success(request, msg)
        return HttpResponseRedirect(request.META["HTTP_REFERER"])

    if blueprint.resource_set.filter(lifecycle="ACTIVE").count() != 0:
        msg = "Blueprints cannot be removed when there are active resources " \
              "assigned to the Blueprint. First remove the resources then" \
              "try again"
        raise CloudBoltException(msg)

    return {
        "title": "Remove Azure ARM Template Blueprint?",
        "content": "Are you sure you want to delete this Azure ARM Template Blueprint?",
        "use_ajax": True,
        "action_url": reverse("delete_arm_blueprint", args=[blueprint_id]),
        "submit": "Remove",
    }


@dialog_view
def create_connection_info(request):
    action_url = reverse("arm_ci_create")

    if request.method == "POST":
        form = CIForm(request.POST)
        if form.is_valid():
            ci = form.save()
            msg = f"New Git Connection info created {ci}"
            messages.success(request, msg)
            return HttpResponseRedirect(request.META["HTTP_REFERER"])
    else:
        form = CIForm()

    return {
        "title": "Add Git Connection Info",
        "form": form,
        "action_url": action_url,
        "submit": "Save",
    }


@dialog_view
def edit_connectioninfo(request, ci_id):
    ci = ConnectionInfo.objects.get(id=ci_id)
    if request.method == "POST":
        form = CIForm(request.POST)
        if form.is_valid():
            ci = form.save()
            msg = f"Git Connection Info updated."
            messages.success(request, msg)
            return HttpResponseRedirect(request.META["HTTP_REFERER"])
    else:
        form = CIForm(instance=ci)

    return {
        "title": _('Edit Connection Info "{}"').format(ci.name),
        "form": form,
        "use_ajax": True,
        "action_url": reverse("arm_ci_edit", args=[ci_id]),
        "submit": _("Save"),
    }


@dialog_view
def delete_connectioninfo(request, ci_id):
    ci = ConnectionInfo.objects.get(id=ci_id)

    if request.method == "POST":
        # User pressed the submit button on the dialog

        try:
            ci.delete()
            messages.success(
                request,
                format_html(
                    _("The Connection Info <b>{}</b> was deleted."), ci.name
                ),
            )
        except ProtectedError:
            msg = _("Connection Info {} is in use and cannot be deleted.").format(
                ci.name
            )
            messages.error(request, msg)

        return HttpResponseRedirect(request.META["HTTP_REFERER"])

    else:
        content = format_html(
            _('<p>Delete Connection Info "{}"?  This action is not reversible.</p>'),
            ci.name,
        )
        submit = _("Delete")
        action_url = reverse("arm_ci_delete", args=[ci_id])
        return {
            "title": _("Delete Connection Info {}?").format(ci.name),
            "content": content,
            "use_ajax": True,
            "action_url": action_url,
            "submit": submit,
        }


def get_arm_connection_infos():
    _, _, queries = get_supported_conn_info_labels()
    cis = ConnectionInfo.objects.filter(eval(queries))
    conn_infos = []
    for ci in cis:
        if ci.name == "CloudBolt Content Library":
            continue
        conn_infos.append(ci)
    return conn_infos


def get_arm_blueprints():
    tags = CloudBoltTag.objects.filter(
        name="ARM Template", model_name="serviceblueprint"
    )
    arm_bps = []
    for tag in tags:
        bps = ServiceBlueprint.objects.filter(tags=tag, status="ACTIVE")
        for bp in bps:
            bp_dict = {'ci_error': None}
            bp_dict["bp"] = bp
            bp_dict["resource_count"] = bp.resource_set.filter(
                lifecycle="ACTIVE").count()
            conn_info_id = int(bp.arm_conn_info_id)
            if conn_info_id == 0:
                bp_dict["conn_info"] = 0
                bp_dict["conn_info_type"] = 'public'
            else:
                try:
                    conn_info = ConnectionInfo.objects.get(id=conn_info_id)
                    bp_dict["conn_info"] = conn_info
                    bp_dict["conn_info_type"] = get_conn_info_type(conn_info)
                except ConnectionInfo.DoesNotExist:
                    bp_dict['ci_error'] = helper_tags.warning_icon(
                        _(
                            "Blueprint ConnectionInfo has been removed and requires updating."
                        )
                    )
            bp_dict["url"] = bp.arm_url
            bp_dict["filename"] = bp.arm_url.split("/")[-1:][0].split('?')[0]
            allowed_env_ids = bp.arm_allowed_env_ids
            bp_dict["resource_type"] = bp.resource_type
            if allowed_env_ids.find('all_capable') > -1:
                bp_dict["allowed_envs"] = 'all_capable'
            else:
                allowed_envs = [env.strip() for env in bp.arm_allowed_env_ids.split(",")]
                bp_dict["allowed_envs"] = []
                for env in allowed_envs:
                    try:
                        env = Environment.objects.get(id=env)
                        bp_dict["allowed_envs"].append(env)
                    except Environment.DoesNotExist:
                        logger.warning(f'Did not find Environment with ID: {env}')
            arm_bps.append(bp_dict)
    return arm_bps


def get_params_from_resource(resource):
    cfv_dict = resource.get_cf_values_as_dict()
    pfx = f"arm_{resource.blueprint_id}_"
    otp = f"{pfx}output_"
    return {
        get_cf_label(k): v
        for k, v in cfv_dict.items()
        if k.startswith(pfx) and not k.startswith(otp)
    }


def get_cf_label(cf_name):
    return CustomField.objects.get(name=cf_name).label


@admin_extension(
    title="Azure ARM Template Library", description="Azure ARM Template library for CloudBolt."
)
def library(request, **kwargs):
    context = {
        "connection_infos": get_arm_connection_infos(),
        "arm_blueprints": get_arm_blueprints(),
    }

    admin_context = {
        "tabs": TabGroup(
            template_dir="arm_templates/templates",
            context=context,
            request=request,
            tabs=[
                # First tab uses template 'groups/tabs/tab-main.html'
                # (_("Configuration"), 'configuration', {}),
                # Tab 2 is conditionally-shown in this slot and
                # uses template 'groups/tabs/tab-related-items.html'
                (_("Blueprints"), "blueprints", {}),
                (_("Source Control"), "sourcecontrol", {}),
            ],
        )
    }

    return render(request, "arm_templates/templates/admin.html", context=admin_context)


@dialog_view
def sync_arm_blueprint(request, blueprint_id):
    """
    View for synchronizing CB Blueprint with ARM. The latest ARM Template version is
    always pulled at execution, BUT parameters are not updated there, this
    allows for the updating of parameters.
    """
    blueprint = ServiceBlueprint.objects.get(id=blueprint_id)
    if request.method == 'POST':
        # Get the latest version of the CFT from Source Code Repo
        conn_info_id = blueprint.arm_conn_info_id
        arm_url = blueprint.arm_url
        try:
            template_json = get_arm_from_source(conn_info_id, arm_url)

            # Add the new template value to the Blueprint
            cf = CustomField.objects.get(name="arm_template")
            add_cfvs_for_field(blueprint, cf, cf.type, [template_json])

            create_params(blueprint, template_json)
            messages.success(request, f'Updated parameters for {blueprint.name}')
        except ConnectionInfo.DoesNotExist:
            messages.error(request, 'Connection Info not found, please edit the Blueprint first.')
        return HttpResponseRedirect(request.META["HTTP_REFERER"])

    return {
        "title": "Synchronize CloudFormation Blueprint",
        "content": f"Fetch and update all parameters on {blueprint.name} Blueprint",
        "action_url": reverse("sync_arm_blueprint", args=[blueprint_id]),
        "use_ajax": True,
        "submit": "Update",
    }
