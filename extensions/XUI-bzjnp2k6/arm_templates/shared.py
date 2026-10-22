"""
Methods for the ARM Template XUI that need to be used in different actions
are stored in this module.
"""
import json

import base64
from decimal import Decimal

import requests
import urllib
import html

from datetime import datetime
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.template import Template, Context

from behavior_mapping.models import SequencedItem, CustomFieldMapping
from cbhooks.models import CloudBoltHook, HookPoint, HookPointAction, \
    OrchestrationHook
from common.methods import set_progress
from infrastructure.models import (
    Environment,
    CustomField,
    FieldDependency,
    Server,
    Namespace,
)
from orders.models import CustomFieldValue
from resourcehandlers.azure_arm.azure_wrapper import (
    TechnologyWrapper,
    AzureARMResourceWrapper,
    _configure_arm_client,
)
from resources.models import ResourceType
from servicecatalog.models import RunCloudBoltHookServiceItem, \
    TearDownServiceItem
from tags.models import CloudBoltTag
from utilities.events import add_server_event
from utilities.exceptions import CloudBoltException
from utilities.logger import ThreadLogger
from utilities.models import ConnectionInfo

logger = ThreadLogger(__name__)

# CloudBolt 2026.2+ ships azure-mgmt-resource 25+, which no longer exposes
# ResourceManagementClient.deployments. ARM deploys require this package:
_AZURE_DEPLOYMENTS_INSTALL = (
    "ARM template deployment requires azure-mgmt-resource-deployments. "
    "Install in the CloudBolt application Python environment, e.g.: "
    "pip install azure-mgmt-resource-deployments==1.0.0b1"
)


def deploy_arm_template_sdk_compat(
    wrapper,
    deployment_name,
    resource_group,
    template,
    parameters,
    timeout=3600,
):
    """
    Resource-group ARM deployment for azure-mgmt-resource 25+ via
    ``azure-mgmt-resource-deployments`` (DeploymentsMgmtClient).
    """
    try:
        from azure.mgmt.resource.deployments import DeploymentsMgmtClient
    except ImportError:
        set_progress(_AZURE_DEPLOYMENTS_INSTALL)
        raise RuntimeError(_AZURE_DEPLOYMENTS_INSTALL) from None

    parameters_dict = {k: {"value": v} for k, v in parameters.items()}
    deployment_body = {
        "properties": {
            "mode": "Incremental",
            "template": template,
            "parameters": parameters_dict,
        }
    }
    deployments_client = _configure_arm_client(wrapper, DeploymentsMgmtClient)
    poller = deployments_client.deployments.begin_create_or_update(
        resource_group_name=resource_group,
        deployment_name=deployment_name,
        parameters=deployment_body,
    )
    return wrapper._wait_on_operation(poller, timeout=timeout)


def get_supported_conn_info_labels():
    # Returns a tuple of conn_info_types, label_queries, conn_info_queries
    # label_queries used when filtering labels, conn_info
    conn_info_types = ["github", "gitlab", "azure_devops"]
    conn_info_queries = []
    for l in conn_info_types:
        conn_info_queries.append(f'Q(labels__name="{l}")')
    conn_info_queries = " | ".join(conn_info_queries)
    label_queries = []
    for l in conn_info_types:
        label_queries.append(f'Q(name="{l}")')
    label_queries = " | ".join(label_queries)
    return conn_info_types, label_queries, conn_info_queries


def get_conn_info_type(conn_info):
    _, queries, _ = get_supported_conn_info_labels()
    labels = conn_info.labels.filter(eval(queries))
    if len(labels) > 1:
        raise CloudBoltException(
            f"More than one valid label found on {conn_info} Connection."
        )
    if len(labels) == 0:
        raise CloudBoltException(
            f"No valid source control labels found on conn info: {conn_info}."
        )
    conn_info_type = labels.first().name
    logger.debug(
        f"Connection info: {conn_info.name} determined to be type of "
        f"{conn_info_type}"
    )
    return conn_info_type


def generate_options_for_resource_type(**kwargs):
    rts = ResourceType.objects.filter(lifecycle='ACTIVE')
    initial_rt = kwargs.get("initial_rt")
    options = []
    if initial_rt:
        options.append((initial_rt,
                        ResourceType.objects.get(id=initial_rt).label))
    for rt in rts:
        if rt.id == initial_rt:
            continue
        options.append((rt.id, rt.label))

    return options


def generate_options_for_connection_info(server=None, **kwargs):
    _, _, queries = get_supported_conn_info_labels()
    cis = ConnectionInfo.objects.filter(eval(queries))
    initial_ci = kwargs.get("initial_ci")
    options = [(0, "Public Repository")]
    logger.info(f'arm - initial_ci: {initial_ci}')
    if initial_ci:
        if int(initial_ci) != 0:
            initial = (
            initial_ci, ConnectionInfo.objects.get(id=initial_ci).name)
            options.insert(0, initial)

    for ci in cis:
        if ci.name == "CloudBolt Content Library":
            continue
        if ci.id == initial_ci:
            continue
        ci_type = get_conn_info_type(ci)
        options.append((ci.id, f"{ci.name}: {ci_type}"))
    return options


def generate_options_for_allowed_environments(server=None, **kwargs):
    options = [("all_capable", " All Capable")]
    envs = Environment.objects.filter(
        resource_handler__resource_technology__modulename__contains="azure_arm"
    )
    options += [(env.id, env.name) for env in envs]

    return options


def create_param_name(param_prefix, bp_id):
    return f"{param_prefix}_{bp_id}"


def create_custom_field_option(blueprint, value, field, cf_type):
    """
    Create a CustomFieldValue for a Custom Field, then add that value to the
    Blueprint level Parameter. This will check first to see if the value
    already exists for that parameter on the blueprint, and if so, not re-add
    to the Blueprint
    """
    logger.debug(
        f"Creating Parameter: {field.name} option, type: {cf_type}," f" Value: {value}"
    )
    if cf_type == "STR":
        cfv = CustomFieldValue.objects.get_or_create(str_value=value,
                                                     field=field)[0]
    elif cf_type == "INT":
        cfv = CustomFieldValue.objects.get_or_create(int_value=value,
                                                     field=field)[0]
    elif cf_type == "BOOL":
        cfv = CustomFieldValue.objects.get_or_create(boolean_value=value,
                                                     field=field)[0]
    elif cf_type == "CODE":
        cfv = CustomFieldValue.objects.get_or_create(txt_value=value,
                                                     field=field)[0]
    else:
        logger.warn(
            f"Unknown Parameter type: {cf_type}, passed in, not "
            f"creating custom field option for field: {field}"
        )
        return None
    cfvs = blueprint.get_cfvs_for_custom_field(field.name)
    if cfv not in cfvs:
        # Don't want to re-add a value if it already exists on the BP
        blueprint.custom_field_options.add(cfv.id)
    return cfv


def add_cfvs_for_field(blueprint, cf, cf_type, new_values: list):
    """
    Add new values to the blueprint for a field, remove CFVs that are not in
    new_values
    """
    existing_cfvs = blueprint.custom_field_options.filter(field__id=cf.id)
    new_cfvs = []
    for value in new_values:
        cfv = create_custom_field_option(blueprint, value, cf, cf_type)
        if cfv:
            new_cfvs.append(cfv)
    remove_old_cfvs(blueprint, existing_cfvs, new_cfvs)


def remove_old_cfvs(blueprint, existing_cfvs, new_cfvs):
    for cfv in existing_cfvs:
        if cfv not in new_cfvs:
            logger.debug(f'Removing CustomFieldValue: {cfv} from options')
            blueprint.custom_field_options.remove(cfv)


def create_cf(
        cf_name,
        cf_label,
        description,
        cf_type="STR",
        allow_multiple=False,
        required=True,
        **kwargs,
):
    namespace, _ = Namespace.objects.get_or_create(name="azure_arm_templates")

    # You can pass in show_on_servers, show_as_attribute as kwargs
    defaults = {
        "label": cf_label,
        "description": description,
        "required": required,
        "allow_multiple": allow_multiple,
        "namespace": namespace,
    }
    for key, value in kwargs.items():
        defaults[key] = value

    cf = CustomField.objects.get_or_create(
        name=cf_name, type=cf_type, defaults=defaults
    )
    return cf


def create_cloudbolt_hook(new_action_name, source_file):
    root_dir = "/var/opt/cloudbolt/proserv/xui/arm_templates/actions/"
    hook, hook_created = CloudBoltHook.objects.get_or_create(
        name=new_action_name, source_code_url=f"file://{root_dir}{source_file}"
    )
    hook.get_runtime_module()
    hook.description = "Used for ARM Template Builder"
    hook.shared = True
    hook.save()
    if hook_created:
        set_progress(f"CloudBolt Hook created: {new_action_name}")
    else:
        set_progress(f"CloudBolt Hook retrieved: {new_action_name}")
    return hook


def create_generated_options_action(new_action_name, source_file):
    # Create Action (CloudBoltHook)
    hook = create_cloudbolt_hook(new_action_name, source_file)

    # Create HookPointAction
    hp_id = HookPoint.objects.get(name="generated_custom_field_options").id
    hpa = HookPointAction.objects.get_or_create(
        name=new_action_name, hook=hook, hook_point_id=hp_id
    )[0]
    hpa.enabled = True
    hpa.continue_on_failure = False
    hpa.save()

    oh = OrchestrationHook.objects.get_or_create(
        name=new_action_name, cloudbolthook=hook
    )[0]
    oh.hookpointaction_set.add(hpa)
    oh.save()

    return oh


def create_param_label(param):
    param_label = " ".join(camel_case_split(param)).title()
    # Handles QuickStart templates where underscores are used
    param_label = param_label.replace("_", " ")
    return param_label


def camel_case_split(string):
    words = [[string[0]]]
    for c in string[1:]:
        if words[-1][-1].islower() and c.isupper():
            words.append(list(c))
        else:
            words[-1].append(c)
    return ["".join(word) for word in words]


def get_arm_from_source(connection_info_id, url):
    if int(connection_info_id) != 0:
        conn_info = ConnectionInfo.objects.get(id=connection_info_id)
        conn_info_type = get_conn_info_type(conn_info)
    else:
        conn_info = None
        conn_info_type = 'public'
    function_call = f'get_template_from_{conn_info_type}(conn_info, url)'
    arm_template = eval(function_call)
    if not arm_template:
        raise Exception(
            f"ARM Template could not be found for conn_info: {conn_info}, and "
            f"URL: {url}")
    return arm_template


def get_template_from_azure_devops(conn_info, url):
    try:
        if url.find("/_git/") > -1:
            raw_url = generate_raw_ado_url(url)
        else:
            raw_url = url
    except Exception as e:
        raise Exception("Raw URL could not be determined for Azure DevOps File"
                        f". Error: {e}")
    username = conn_info.username
    token = conn_info.password
    user_pass = f'{username}:{token}'
    b64 = base64.b64encode(user_pass.encode()).decode()
    headers = {"Authorization": f"Basic {b64}"}
    response = requests.get(raw_url, headers=headers)
    response.raise_for_status()
    r_json = response.json()
    arm_template = json.dumps(r_json)
    return arm_template


def generate_raw_ado_url(file_url):
    """
    Generate the raw URL needed in CloudBolt to use the "Fetch from URL" option
    in a CloudBolt action. This method assumes that you are able to use TfsGit
    As your source provider, and that your Project and Repo Names are the same
    :param file_url: The URL of the file in Azure DevOps
    Ex: https://dev.azure.com/cloudbolt-sales-demo/_git/CMP?path=/python_samples/xaas_build.py
    """
    if file_url.find('/_git/') == -1:
        raise Exception('The URL entered appears to not be a GIT file')
    if file_url.find('?path=') == -1:
        raise Exception('The URL entered does not include a path, the URL '
                        'should point to a file')
    url_parse = urllib.parse.urlparse(file_url)
    scheme = url_parse.scheme
    server = url_parse.netloc
    url_prefix = f'{scheme}://{server}'
    url_path = url_parse.path
    org = url_path.split('/')[1]
    project = url_path.split('/')[3]
    query = url_parse.query
    args_split = query.split('&')
    branch = ''
    path = ''
    for arg in args_split:
        key, value = arg.split('=')
        if key == 'path':
            path = urllib.parse.quote(urllib.parse.unquote(value), safe='')
        if key == 'version' and value.find('GB') == 0:
            branch = value[2:]
    if not path:
        raise Exception('Path was not found in the URL entered')
    if not branch:
        branch = 'main'
    raw_url = f'{url_prefix}/{org}/{project}/_apis/sourceProviders/TfsGit/' \
              f'filecontents?repository={project}&path={path}&commitOrBranch=' \
              f'{branch}&api-version=5.0-preview.1'
    return raw_url


def get_template_from_public(conn_info, url):
    if url.find('raw') == -1:
        raise CloudBoltException(f'URL entered was not in raw format, please '
                                 f're-submit request using a raw formatted '
                                 f'URL')
    response = requests.get(url)
    response.raise_for_status()
    return response.content.decode("utf-8")


def get_template_from_gitlab(conn_info, url):
    # For gitlab, it doesn't matter if the URL passed is the Raw or the normal
    # URL. The URL needs to be reconstructed to make an API call. The token
    # created for auth will need at a minimum read_api and read_repository
    base_url = f"https://{url.split('/')[2]}:443/api/v4"
    project_path = "/".join(url.split("/-/")[0].split("/")[-2:])
    project_id = urllib.parse.quote(project_path, safe="")
    url_split = url.split("/-/")[1].split("/")
    branch = url_split[1]
    file_path = urllib.parse.quote("/".join(url_split[2:]), safe="")
    path = f"/projects/{project_id}/repository/files/{file_path}/raw" f"?ref={branch}"
    set_progress(f"Submitting request to GitLab URL: {path}")
    headers = {
        "PRIVATE-TOKEN": conn_info.password,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    request_url = f"{base_url}{path}"
    r = requests.get(request_url, auth=None, headers=headers)
    r.raise_for_status()
    r_json = r.json()
    raw_file_json = json.dumps(r_json)
    return raw_file_json


def get_template_from_github(conn_info, cft_url):
    import base64

    url_split = cft_url.split("/")
    username = url_split[3]
    repo = url_split[4]
    allowed_hosts = [
        "github.com"
    ]
    host = urllib.parse.urlparse(cft_url).hostname
    if host and host in allowed_hosts:
        branch = url_split[6]
    else:
        branch = url_split[5]
    file_path = cft_url.split(f"/{branch}/")[1].split("?")[0]

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {conn_info.password}",
    }
    git_url = (
        f"https://api.github.com/repos/{username}/{repo}/contents/"
        f"{file_path}?ref={branch}"
    )
    response = requests.get(git_url, headers=headers)
    response.raise_for_status()
    data = response.json()
    content = data["content"]
    file_content_encoding = data.get("encoding")
    if file_content_encoding == "base64":
        content = base64.b64decode(content).decode()
    return content


def add_blueprint_label(blueprint):
    # Create Label if it doesn't exist
    label = CloudBoltTag.objects.get_or_create(
        name="ARM Template", model_name="serviceblueprint"
    )[0]
    # Add Label to Blueprint
    blueprint.tags.add(label)
    return None


def create_cf_bp_options(
        cf_name,
        cf_label,
        description,
        blueprint,
        values: list,
        cf_type="STR",
        allow_multiple=False,
        required=True,
        **kwargs,
):
    # Create the Custom Field
    cf = create_cf(
        cf_name, cf_label, description, cf_type, allow_multiple, required,
        **kwargs
    )[0]

    # Add it to the Blueprint
    blueprint.custom_fields_for_resource.add(cf)

    add_cfvs_for_field(blueprint, cf, cf_type, values)

    return cf


def create_blueprint_level_params(
        blueprint, template_json, arm_url, allowed_environments, conn_info_id
):
    set_progress(f"conn_info_id: {conn_info_id}")
    # Save Cloud Formation Template
    create_cf_bp_options(
        "arm_template",
        "ARM Template",
        "ARM Template Contents",
        blueprint,
        [template_json],
        cf_type="CODE",
    )

    # Save Allowed Environments
    env_ids = ",".join(allowed_environments)
    allowed_envs_cf = create_cf_bp_options(
        "arm_allowed_env_ids",
        "Allowed Environments",
        "A list of the IDs of Environments " "allowed for the ARM Template",
        blueprint,
        [env_ids],
    )

    # Save ARM URL
    create_cf_bp_options(
        "arm_url",
        "ARM Template URL",
        "The URL where the ARM Template is located in Source" " Control",
        blueprint,
        [arm_url],
    )

    # Save Connection Info ID
    create_cf_bp_options(
        "arm_conn_info_id",
        "ConnectionInfo ID",
        "The ID of the Connection Info for Source Control",
        blueprint,
        [conn_info_id],
    )

    # Create Environment Parameter, add to Blueprint
    env_cf = create_cf_bp_options(
        "arm_env_id", "Environment", "Azure Environment", blueprint, []
    )
    SequencedItem.objects.get_or_create(custom_field=env_cf)

    # Create Resource Group Parameter, add to Blueprint
    rg_cf, cf_created = create_cf(
        "arm_resource_group",
        "Resource Group",
        "Azure Resource Group",
        show_on_servers=True,
        show_as_attribute=True,
    )
    # Create Programmatically Gen Options action for Resource group
    oh = create_generated_options_action(
        "Generate options for 'arm_resource_group'",
        "generate_options_for_resource_group.py",
    )
    rg_cf.orchestration_hooks.add(oh)
    rg_cf.save()
    blueprint.custom_fields_for_resource.add(rg_cf)

    # Create field dependency for Resource Group
    create_field_dependency(env_cf, rg_cf)

    SequencedItem.objects.get_or_create(custom_field=rg_cf)

    # Create ARM Deployment Name param
    cf = create_cf_bp_options(
        "arm_deployment_name",
        "ARM Deployment Name",
        "Name of the deployment in Azure",
        blueprint,
        [],
        show_on_servers=True,
    )
    SequencedItem.objects.get_or_create(custom_field=cf)

    # Create Programmatically Gen Options action for environment
    oh = create_generated_options_action(
        "Generate options for 'arm_env_id'", "generate_options_for_env_id.py"
    )
    env_cf.orchestration_hooks.add(oh)
    env_cf.save()
    blueprint.custom_fields_for_resource.add(env_cf)

    # Create Field Dependency for Environment to read from list of allowed envs
    create_field_dependency(allowed_envs_cf, env_cf)


def create_field_dependency(
        control_field, dependent_field, dependency_type: str = "REGENOPTIONS"
):
    dependency, _ = FieldDependency.objects.get_or_create(
        controlling_field=control_field,
        dependent_field=dependent_field,
        dependency_type=dependency_type,
    )
    return dependency


def add_bp_items(blueprint):
    # Add Build Item
    hook = create_cloudbolt_hook("ARM Template Build",
                                 "deploy_arm_template.py")
    oh, _ = OrchestrationHook.objects.get_or_create(
        name="ARM Template Build", cloudbolthook=hook
    )
    rcbhsi, _ = RunCloudBoltHookServiceItem.objects.get_or_create(
        name="ARM Template Build",
        hook=oh,
        blueprint=blueprint,
        show_on_order_form=False,
        run_on_scale_up=False,
    )

    # Add Teardown Item
    hook = create_cloudbolt_hook("ARM Template Teardown",
                                 "teardown_arm_template.py")
    oh, _ = OrchestrationHook.objects.get_or_create(
        name="ARM Template Teardown", cloudbolthook=hook
    )
    tdsi, _ = TearDownServiceItem.objects.get_or_create(
        name="ARM Template Teardown", hook=oh, blueprint=blueprint,
        deploy_seq=-1
    )


def create_params(blueprint, template_json):
    bp_id = blueprint.id
    template_content = json.loads(template_json)

    template_params = template_content.get("parameters", None)
    if template_params:
        param_prefix = f"arm_{bp_id}_"
        for key in template_params.keys():
            create_param(key, template_params, param_prefix, blueprint)


def create_param(key, template_params, param_prefix, blueprint):
    param = template_params[key]
    param_type = param["type"]
    new_param_name = f"{param_prefix}{key}"
    param_label = create_param_label(key)
    description = param.get("metadata", {}).get(
        "description", "ARM Template Builder Param"
    )

    allow_multiple = False
    required = True
    # Forcing to lower because of ARM Template case insensitivity
    if param_type.lower() == "securestring":
        cf_type = "PWD"
    elif param_type.lower() == "string":
        cf_type = "STR"
    elif param_type.lower() == "int":
        cf_type = "INT"
    elif param_type.lower() == "bool":
        cf_type = "BOOL"
    elif param_type.lower() == "object":
        cf_type = "CODE"

    else:
        logger.warn(
            f"Unable to find a known type for parameter: {key}."
            f"This parameter will not be considered in the created"
            f"blueprint"
        )
        return

    # Create the parameter
    logger.debug(
        f"Creating Parameter: {new_param_name}, type: {type}, " f"label: {param_label}"
    )
    cf, cf_created = create_cf(
        new_param_name,
        param_label,
        description,
        cf_type,
        allow_multiple,
        required,
        show_on_servers=True,
    )

    # Add it to the Blueprint
    blueprint.custom_fields_for_resource.add(cf)

    # Do not want to set a value for passwords, just exit
    if cf_type == "PWD":
        return
    add_param_values(blueprint, cf, cf_type, param, cf_created)

    if cf_created:
        # On the first time the param is created want to add the param to
        # param display sequence. When first creating the blueprint this will
        # ensure that the params show in the BP in the order they are listed
        # in the ARM. Later added params will need to be manually moved in the
        # display sequence
        SequencedItem.objects.get_or_create(custom_field=cf)

    check_and_set_constraints(param, cf)


def check_and_set_constraints(param, cf):
    # See if any valid constraints exist on the Parameter. Currently supported:
    # minLength, minValue, maxLength, maxValue, AllowedPattern
    constraints = {}
    min_keys = ["minlength", "minvalue"]
    max_keys = ["maxlength", "maxvalue"]
    for key in param.keys():
        value = param[key]
        if key.lower() in min_keys:
            constraints["minimum"] = Decimal(value)
        if key.lower() in max_keys:
            constraints["maximum"] = Decimal(value)

    # Regex validation of parameters is not currently supported in ARM
    # Templates
    # constraints["regex_constraint"] = param["AllowedPattern"]

    if constraints:
        set_constraints_for_cf(cf, constraints)


def set_constraints_for_cf(cf, constraints: dict):
    """
    Set Global Constraints for a Custom Field.
    Constraints dictionary can include the following fields:
    - minimum
    - maximum
    - slider_increment
    - regex_constraint
    """
    cfm = CustomFieldMapping.global_constraints.filter(custom_field=cf).first()
    if cfm is None:
        try:
            cfm, __ = CustomFieldMapping.global_mappings_not_defaults.get_or_create(
                custom_field=cf
            )
        except AttributeError:
            # Prior to 9.4.7 the above method did not exist. Will create a new
            # global constraint
            cfm, __ = CustomFieldMapping.global_constraints.get_or_create(
                custom_field=cf
            )
    cf.set_constraints_in_cfm(cfm, constraints)


def add_param_values(blueprint, cf, cf_type, param, cf_created: False):
    # Create Add value from parameters file as selection in dropdown
    # If a list of allowed values exists, then we want to create a dropdown
    # with those values. If allowed values are not set, check the params
    # file for a value and then the template itself for a default value
    # to set a single value for the parameter options
    allowed_values = get_case_insensitive_property(param, "AllowedValues")
    if allowed_values:
        add_cfvs_for_field(blueprint, cf, cf_type, allowed_values)
    else:
        if cf_created:
            # Only want to create default value on the first import. After that
            # This should be controlled by the parameter in CB.
            default_value = get_case_insensitive_property(param,
                                                          "DefaultValue")
            if default_value:
                add_cfvs_for_field(blueprint, cf, cf_type, [default_value])


def get_case_insensitive_property(param, key_to_find):
    # Because ARM Template Parameter keys can be case insensitive there were
    # many cases during testing where one ARM Template would use AllowedValues
    # but another would use allowedValues. This function allows handling of
    # that scenario.
    key_value = None
    for key in param.keys():
        if key.lower() == key_to_find.lower():
            key_value = param[key]
            break
    return key_value


def create_resource_type(type_name, **kwargs):
    defaults = {}
    for key, value in kwargs.items():
        defaults[key] = value
    resource_type, _ = ResourceType.objects.get_or_create(
        name=type_name, defaults=defaults
    )
    return resource_type


def get_or_create_cfs():
    create_cf(
        "arm_deployment_id",
        "ARM Deployment ID",
        "Used by the ARM Template blueprint",
        show_on_servers=True,
    )


def get_location_from_environment(env):
    return env.node_location


def get_provider_type_from_id(resource_id):
    return resource_id.split("/")[6]


def get_resource_type_from_id(resource_id):
    return resource_id.split("/")[7]


def get_azure_server_name(id_value):
    return id_value.split("/")[8]


def create_field_set_value(field_name, label, value, description, resource,
                           cf_type="STR"):
    create_cf(field_name, label, description, cf_type, show_on_servers=True)
    resource.set_value_for_custom_field(field_name, value)
    return resource


def get_arm_template_for_resource(resource):
    try:
        # First try to get the latest version from source, then try stored
        arm_url = resource.get_cfv_for_custom_field("arm_url").value
        conn_info_id = resource.get_cfv_for_custom_field(
            "arm_conn_info_id").value
        arm_template = get_arm_from_source(conn_info_id, arm_url)
    except:
        arm_template = resource.get_cfv_for_custom_field("arm_template").value
    return arm_template


def get_arm_deploy_params(resource, env):
    # Override params set in the params file by params included set on the
    # Resource
    cfvs = resource.get_cf_values_as_dict()
    bp_id = resource.blueprint_id
    arm_prefix = f"arm_{bp_id}_"
    parameters = {}
    for key in cfvs.keys():
        if key.find(arm_prefix) == 0:
            param_key = key.replace(arm_prefix, "")
            value = cfvs[key]
            if value == "[resourceGroup().location]":
                value = get_location_from_environment(env)
            parameters[param_key] = value
            cf = CustomField.objects.get(name=key)
            if cf.type == "PWD":
                logger.debug(f"Setting password: {param_key} to: ******")
            else:
                logger.debug(f"Setting param: {param_key} to: {value}")
    return parameters


def submit_arm_template_request(
        deployment_name, resource_group, template, parameters, wrapper,
        timeout=None
):
    # Submit the template request
    if timeout:
        timeout = int(timeout)
    else:
        timeout = 3600
    logger.debug(
        f"Submitting request for ARM template. deployment_name: "
        f"{deployment_name}, resource_group: {resource_group}, "
        f"template: {template}"
    )
    set_progress(
        f"Submitting ARM request to Azure. This can take a while."
        f" Timeout is set to: {timeout}"
    )
    deployment = deploy_arm_template_sdk_compat(
        wrapper,
        deployment_name,
        resource_group,
        template,
        parameters,
        timeout=timeout,
    )
    set_progress(f"Deployment created successfully")
    logger.debug(f"deployment info: {deployment}")
    return deployment


def create_deployment_params(
        resource, deployment, rh, env, resource_group, wrapper, group, job
):
    deploy_props = deployment.properties
    logger.debug(f"deployment properties: {deploy_props}")
    resource.azure_region = env.node_location
    resource.arm_deployment_id = deployment.id
    resource.resource_group = resource_group
    resource.save()
    i = 0
    for output_resource in deploy_props.additional_properties[
        "outputResources"]:
        id_value = output_resource["id"]
        type_value = id_value.split("/")[-2]

        # If a server, create the CloudBolt Server object
        if type_value == "virtualMachines":
            resource_client = wrapper.resource_client
            api_version = get_api_version(resource_client, id_value)
            vm = resource_client.resources.get_by_id(id_value, api_version)
            vm_dict = vm.__dict__
            svr_id = vm_dict["properties"]["vmId"]
            location = vm_dict["location"]
            node_size = vm_dict["properties"]["hardwareProfile"]["vmSize"]
            disk_ids = [
                vm_dict["properties"]["storageProfile"]["osDisk"][
                    "managedDisk"]["id"]
            ]
            for disk in vm_dict["properties"]["storageProfile"]["dataDisks"]:
                disk_ids.append(disk["managedDisk"]["id"])
            if svr_id:
                # Server manager does not have the create_or_update method,
                # so we do this manually.
                try:
                    server = Server.objects.get(resource_handler_svr_id=svr_id)
                    server.resource = resource
                    server.group = group
                    server.owner = resource.owner
                    server.environment = env
                    server.save()
                    logger.info(f"Found existing server record: '{server}'")
                except Server.DoesNotExist:
                    logger.info(
                        f"Creating new server with resource_handler_svr_id "
                        f"'{svr_id}', resource '{resource}', group '{group}', "
                        f"owner '{resource.owner}', and "
                        f"environment '{env}'"
                    )
                    server_name = get_azure_server_name(id_value)
                    server = Server(
                        hostname=server_name,
                        resource_handler_svr_id=svr_id,
                        resource=resource,
                        group=group,
                        owner=resource.owner,
                        environment=env,
                        resource_handler=rh,
                    )
                    server.save()
                    server.resource_group = resource_group
                    server.save()

                    tech_dict = {
                        "location": location,
                        "resource_group": resource_group,
                        "storage_account": None,
                        "extensions": [],
                        "availability_set": None,
                        "node_size": node_size,
                    }
                    rh.update_tech_specific_server_details(server, tech_dict,
                                                           None)
                    create_cf("created_by_arm", "Created by ARM Template",
                              "Server was created by the ARM Template XUI",
                              "BOOL", show_on_servers=True,
                              show_as_attribute=True)
                    server.set_value_for_custom_field("created_by_arm", True)
                    server.refresh_info()
                # Add server to the job.server_set, and set creation event
                job.server_set.add(server)
                job.save()
                msg = "Server created by ARM Template job"
                add_server_event("CREATION", server, msg, profile=job.owner,
                                 job=job)
                for disk_id in disk_ids:
                    field_name = f"output_resource_{i}_id"
                    description = f"ARM Resource Disk {i}"

                    resource = create_field_set_value(
                        field_name, field_name, disk_id, description, resource
                    )
                    i += 1
                    resource.save()
        field_name = f"output_resource_{i}_id"
        description = f'ARM Created Resource ID: {i}'
        resource = create_field_set_value(
            field_name, field_name, id_value, description, resource
        )
        i += 1
        resource.save()


def get_api_version(resource_client: AzureARMResourceWrapper, resource_id: str,
                    default: bool = False):
    """
    :param resource_client: Azure ARM Azure Technology Wrapper - Resource Client
    :param resource_id: Azure Resource ID
    :param default: Use the Default value for API if set for Resource Type. If
    not will use the latest API Version available
    :return: str: API Version
    """
    provider = get_provider_type_from_id(resource_id)
    resource_type = get_resource_type_from_id(resource_id)
    resource_types = resource_client.providers.get(provider).resource_types
    for rt in resource_types:
        if rt.resource_type == resource_type:
            api_version = None
            if default:
                try:
                    api_version = rt.additional_properties.get(
                        "defaultApiVersion")
                except AttributeError:
                    pass
            if not api_version:
                api_versions = rt.api_versions
                api_version = get_latest_api_version(api_versions)
            if not api_version:
                raise Exception(f'API Version could not be determined for '
                                f'provider: {provider}, resource_type: '
                                f'{resource_type}')
    return api_version


def get_latest_api_version(api_versions):
    api_dates = []
    for version in api_versions:
        version_split = version.split('-')
        api_dates.append(datetime(int(version_split[0]), int(version_split[1]),
                                  int(version_split[2])))
    api_version = max(api_dates).strftime('%Y-%m-%d')
    return api_version


def write_outputs_to_resource(resource, deployment):
    """
    Write the outputs of the executed CFT back to the Resource as Parameters
    """
    arm_prefix = f"cft_{resource.blueprint_id}_"
    try:
        outputs = deployment.as_dict()["properties"]["outputs"]
    except KeyError:
        logger.debug("No outputs defined for ARM Template, skipping outputs.")
        return
    for key in outputs.keys():
        output = outputs[key]
        label = f'Output: {key}'
        field_name = f"{arm_prefix}output_{label}"
        value = output["value"]
        arm_type = output["type"]
        cf_type, value = get_cb_type_from_arm_type(arm_type, value)
        logger.debug(
            f"Writing output to Resource. Label: {label}, value: " f"{value}")
        create_field_set_value(field_name, label, value, "", resource, cf_type)


def get_cb_type_from_arm_type(arm_type, value):
    arm_type = arm_type.lower()
    if arm_type == "string" or arm_type == "array" or arm_type == "object":
        cb_type = "STR"
    elif arm_type == "array":
        value = json.dumps(value)
    elif arm_type == "bool":
        cb_type = "BOOL"
        value = bool(value)
    elif arm_type == "int":
        cb_type = "INT"
        value = int(value)
    elif (arm_type == "object" or arm_type == "array" or
          arm_type == "secureobject"):
        value = json.dumps(value)
    elif arm_type == "securestring":
        cb_type = "PWD"
    elif arm_type.lower() == "secureobject":
        cb_type = "ETXT"
    else:
        raise Exception(f"ARM Type not recognized: {arm_type}")
    return cb_type, value


def render_parameters(resource, environment, job):
    # Go through all parameters on the resource and render them with Django
    # Templating
    params = resource.get_cf_values_as_dict()
    context = {
        "resource": resource,
        "environment": environment,
        "group": resource.group,
        "job": job,
    }
    context = Context(context)
    for key in params.keys():
        value = params[key]
        if type(value) == str:
            if value.find('{{') > -1 or value.find('{%') > -1:
                template = Template(value)
                # Hit some instances where strings were rendering with unicode hex
                # html.unescape fixes this
                rendered_value = html.unescape(template.render(context))
                if rendered_value != value:
                    logger.info(f'Rendered value: {value} to '
                                f'rendered_value: {rendered_value}')
                    resource.set_value_for_custom_field(key, rendered_value)
    return resource
