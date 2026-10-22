"""
This module is used to store the methods for setting up a CloudBolt XUI. This
could be reused for other XUIs. with minimal changes needed. The following
directories are supported:
- blueprints - Any blueprints must be exported from API v2 and placed in a
  /blueprints/ directory in an extracted format. The directory structure must
  be the same as the export.
- inbound_webhooks - Any inbound webhooks must be exported from API v3 and
  placed an /inbound_webhooks/ directory in an extracted format. The directory
  structure must be the same as the export.
- parameters - One or more json files can be placed in the /parameters/
  directory - each json file should contain a single param or a list of params.
  See the docstring for configure_params for more details.
- recurring_jobs - Any recurring jobs must be exported from API v3 and placed
  in a /recurring_jobs/ directory in an extracted format. The directory
  structure must be the same as the export.

XUI Requirements:
- In __init__.py you must have at least the following three lines. Replace
  <xui_name> with the name of your XUI.
    from xui.<xui_name>.config import run_config
    __version__ = "1.0"
    run_config(__version__)
- With every release of the XUI, the __version__ variable must be updated.
"""
import json
import os
from os import path
from packaging import version
from django.utils.text import slugify
from c2_wrapper import create_custom_field
from cbhooks.models import CloudBoltHook, InboundWebHook, RecurringActionJob
from externalcontent.models import OSFamily
from jobs.models import RecurringJob
from resourcehandlers.models import ResourceTechnology
from servicecatalog.models import ServiceBlueprint
from utilities.run_command import execute_command
from utilities.logger import ThreadLogger

logger = ThreadLogger(__name__)

XUI_PATH = path.dirname(path.abspath(__file__))
XUI_NAME = XUI_PATH.split("/")[-1]
CONFIG_FILE = f'/var/opt/cloudbolt/proserv/xui/xui_versions.json'
BASE_NAME = __package__.split(".")[-1]
SETTINGS_FILE = __file__
ONEFUSE_PYTHON_MINIMUM_VERSION = '2023.1.1.1'


def get_data_from_config_file(property_key):
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)
        data = config[XUI_NAME][property_key]
    return data


# If we find a Blueprint with the same name, should it be overwritten? Since
# Remote source for blueprints is still set to use API V2, we can't use the
# Global ID to check if the blueprint is the same. We can only check the name.
try:
    get_data_from_config_file('OVERWRITE_EXISTING_BLUEPRINTS')
except Exception:
    OVERWRITE_EXISTING_BLUEPRINTS = False
# From what I can tell, when a Blueprint is using a remote source, the actions
# are only updated at initial creation. Setting this toggle to True would
# set each action to use the remote source - forcing update of the actions when
# the XUI gets updated
try:
    get_data_from_config_file('SET_ACTIONS_TO_REMOTE_SOURCE')
except Exception:
    SET_ACTIONS_TO_REMOTE_SOURCE = True


def run_config(xui_version):
    config_needed = False
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
            current_version = config[XUI_NAME]["current_version"]
            if version.parse(current_version) < version.parse(xui_version):
                logger.info(f"Current Version: {current_version} is less than"
                            f" {xui_version}. Running config.")
                config_needed = True
    except (FileNotFoundError, KeyError):
        logger.info(f"Config file or key not found going to run configuration")
        config_needed = True
    if config_needed:
        logger.info("Running Configuration")
        # OneFuse Specific Configuration:
        logger.debug(f'Checking OneFuse Python Module is installed.')

        try:
            import onefuse
        except ModuleNotFoundError:
            logger.info("Installing OneFuse PIP Package")
            execute_command("pip install onefuse")
            import onefuse
        current_version = onefuse.__version__
        # logger.debug(f"OneFuse Python Version: {current_version}")
        upgrade_version = version.parse(current_version) < version.parse(
            ONEFUSE_PYTHON_MINIMUM_VERSION)
        if upgrade_version:
            logger.info("Upgrading OneFuse PIP Package")
            execute_command("pip install onefuse --upgrade")
            import onefuse

        from xui.onefuse.shared import create_onefuse_params, \
            create_onefuse_actions
        create_onefuse_params()
        create_onefuse_actions()

        # Other Configuration
        configure_xui()
        try:
            config
        except NameError:
            config = {}
        config[XUI_NAME] = {
            "current_version": xui_version,
            "SET_ACTIONS_TO_REMOTE_SOURCE": SET_ACTIONS_TO_REMOTE_SOURCE,
            "OVERWRITE_EXISTING_BLUEPRINTS": OVERWRITE_EXISTING_BLUEPRINTS
        }

        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)


def configure_xui():
    configure_params()
    configure_blueprints()
    configure_inbound_webhooks()
    configure_recurring_jobs()


def configure_params():
    """
    Read any json files under /params/ to create any necessary params. These
    files can be structured as either a dict with a single param or a list of
    params in dict format. name, type, and label are required fields.

    Valid keys for the param are: name (str), label (str), type (str: STR,
    TXT, INT, IP, DT, ETXT, CODE, BOOL, DEC, PWD, TUP, URL), required (bool),
    namespace (str), show_on_servers (bool), available_all_servers (bool),
    show_as_attribute (bool), description (str), allow_multiple (bool)
    :return:
    """
    params_dir = f'{XUI_PATH}/parameters/'
    try:
        param_files = os.listdir(params_dir)
    except FileNotFoundError:
        logger.info(f"No params directory found at {params_dir}")
        return
    if param_files:
        for param_file in param_files:
            logger.info(f"Starting import of param file : {param_file}")
            param_path = f'{params_dir}{param_file}'
            with open(param_path, 'r') as f:
                param_json = json.load(f)
            if type(param_json) == dict:
                cf = create_param_from_dict(param_json)
            elif type(param_json) == list:
                for param in param_json:
                    cf = create_param_from_dict(param)
            else:
                logger.info(f"Param file {param_file} is not a dict or list")


def create_param_from_dict(param_dict):
    cf = create_custom_field(**param_dict)
    return cf


def configure_blueprints():
    blueprints_dir = f'{XUI_PATH}/blueprints/'
    try:
        bps = os.listdir(blueprints_dir)
    except FileNotFoundError:
        logger.info(f"No blueprints directory found at {blueprints_dir}")
        return
    for bp in bps:
        logger.info(f"Starting import of blueprint: {bp}")
        bp_dir = f'{blueprints_dir}{bp}/'
        bp_path = f'{bp_dir}{bp}.json'
        with open(bp_path, 'r') as f:
            bp_json = json.load(f)
        bp_name = bp_json["name"]
        try:
            # You can manually add an id to the blueprint json file to check
            # for blueprint by global_id instead of name
            global_id = bp_json["id"]
            logger.info(f"Get or create for blueprint with global id: "
                        f"{global_id}, bp_name: {bp_name}")
            bp, created = ServiceBlueprint.objects.get_or_create(
                global_id=global_id,
                )
            bp.name = bp_name
            bp.status = 'ACTIVE'
            bp.save()
        except KeyError:
            logger.info(f"No global ID found for blueprint {bp_name}, creating"
                        f" by name instead")
            bp, created = ServiceBlueprint.objects.get_or_create(
                name=bp_name,
                status='ACTIVE')
        if not created:
            if OVERWRITE_EXISTING_BLUEPRINTS:
                logger.info(f"Overwriting Blueprint: {bp_name}")
            else:
                logger.info(f"Blueprint: {bp_name} already exists. Skipping")
                continue
        # Setting Remote source URL here pulls in all actions from the remote
        # source. We then remove the remote source setting so groups can be set
        # on the template BP if desired
        bp.remote_source_url = f'file://{bp_path}'
        bp.save()
        bp.refresh_from_remote_source()
        bp.remote_source_url = ""
        bp.save()
        logger.info(f"Finished refreshing: {bp_name} from remote source")
        set_actions_to_remote_source(bp_dir, bp_json, created)


def configure_inbound_webhooks():
    iwh_dir = f'{XUI_PATH}/inbound_webhooks/'
    try:
        iwhs = os.listdir(iwh_dir)
    except FileNotFoundError:
        logger.info(f"No inbound webhooks directory found at {iwh_dir}")
        return
    for iwh in iwhs:
        logger.info(f"Starting import of Inbound Webhook: {iwh}")
        iwh_file = f'{iwh}.json'
        iwh_path = f'{iwh_dir}{iwh}/{iwh_file}'
        with open(iwh_path, 'r') as f:
            iwh_json = json.load(f)
        hook_name = slugify(iwh_json["base_action_name"]).replace("-", "_")
        hook_json_path = f'{iwh_dir}{iwh}/{hook_name}/{hook_name}.json'
        with open(hook_json_path, 'r') as f:
            hook_json = json.load(f)
        script_filename = hook_json["script_filename"]
        hook_py_path = f'{iwh_dir}{iwh}/{hook_name}/{script_filename}'
        hook = create_cloudbolt_hook(hook_json, hook_py_path)
        create_inbound_webhook(iwh_json, hook)


def configure_recurring_jobs():
    recurring_jobs_dir = f'{XUI_PATH}/recurring_jobs/'
    try:
        recurring_jobs = os.listdir(recurring_jobs_dir)
    except FileNotFoundError:
        logger.info(f"No inbound webhooks directory found at "
                    f"{recurring_jobs_dir}")
        return
    for rj in recurring_jobs:
        logger.info(f"Starting import of Recurring Job: {rj}")
        rj_file = f'{rj}.json'
        rj_path = f'{recurring_jobs_dir}{rj}/{rj_file}'
        with open(rj_path, 'r') as f:
            rj_json = json.load(f)
        hook_name = slugify(rj_json["name"]).replace("-", "_")
        hook_json_path = f'{recurring_jobs_dir}{rj}/{hook_name}/{hook_name}.json'
        with open(hook_json_path, 'r') as f:
            hook_json = json.load(f)
        script_filename = hook_json["script_filename"]
        hook_py_path = f'{recurring_jobs_dir}{rj}/{hook_name}/{script_filename}'
        hook = create_cloudbolt_hook(hook_json, hook_py_path)
        create_recurring_job(rj_json, hook)


def set_actions_to_remote_source(bp_dir, bp_json, created):
    if SET_ACTIONS_TO_REMOTE_SOURCE or created:
        logger.info(f'Starting to set actions to remote source for BP: '
                    f'{bp_json["name"]}')
        action_datas = []  # Tuples of (action_name, action_path)
        elements = ["teardown-items", "build-items", "management-actions"]
        for element in elements:
            for action in bp_json[element]:
                action_data = get_action_data(action, bp_dir, element)
                action_datas.append(action_data)
        for action_data in action_datas:
            action_name, action_path = action_data
            logger.info(f"Setting action: {action_name} to remote source")
            set_action_to_remote_source(action_name, action_path)
    else:
        logger.info("Not setting actions to remote source. Update the "
                    "SET_ACTIONS_TO_REMOTE_SOURCE variable to True if you "
                    "want to do this")
    return None


def create_inbound_webhook(iwh_config, hook):
    global_id = iwh_config["id"]

    defaults = {
        "label": iwh_config["label"],
        "maximum_version_required": iwh_config["maximum_version_required"],
        "minimum_version_required": iwh_config["minimum_version_required"],
        "hook": hook.orchestrationhook_ptr,
    }
    iwh, created = InboundWebHook.objects.get_or_create(
        global_id=global_id,
        defaults=defaults)
    if not created:
        iwh.hook = hook.orchestrationhook_ptr
        iwh.save()
    return iwh


def create_recurring_job(rj_json, hook):
    global_id = rj_json["id"]

    defaults = {
        "name": rj_json["name"],
        "description": rj_json["description"],
        "schedule": rj_json["schedule"],
        "enabled": rj_json["enabled"],
        "allow_parallel_jobs": rj_json["allow_parallel_jobs"],
        "hook": hook.orchestrationhook_ptr,
    }
    rj, created = RecurringActionJob.objects.get_or_create(
        global_id=global_id,
        defaults=defaults)
    if not created:
        rj.hook = hook.orchestrationhook_ptr
        rj.save()
    return rj


def create_cloudbolt_hook(hook_config, hook_file):
    global_id = hook_config["id"]
    resource_technologies = hook_config["resource_technologies"]
    target_os_families = hook_config["target_os_families"]
    defaults = {
        "name": hook_config["name"],
        "description": hook_config["description"],
        "max_retries": hook_config["max_retries"],
        "maximum_version_required": hook_config["maximum_version_required"],
        "minimum_version_required": hook_config["minimum_version_required"],
        "shared": hook_config["shared"],
        "module_file": hook_file,
        "ootb_module_file": hook_file,
    }
    hook, created = CloudBoltHook.objects.get_or_create(global_id=global_id,
                                                        defaults=defaults)
    if created or SET_ACTIONS_TO_REMOTE_SOURCE:
        hook.source_code_url = f'file://{hook_file}'
        hook.save()
        hook.fetch_remote_content()
        logger.info(f"Finished refreshing: {hook.name} from remote source")
    if resource_technologies:
        for rt_name in resource_technologies:
            rt = ResourceTechnology.objects.get(name=rt_name)
            hook.resource_technologies.add(rt)
    if target_os_families:
        for os_fam_name in target_os_families:
            os_fam = OSFamily.objects.get(name=os_fam_name)
            hook.os_families.add(os_fam)
    return hook


def set_action_to_remote_source(action_name, action_path):
    try:
        action = CloudBoltHook.objects.get(name=action_name)
        action.source_code_url = f'file://{action_path}'
        action.save()
    except:
        logger.warning(f"Could not find action: {action_name}, will not be "
                       f"able to set to remote source")


def get_action_data(action, bp_dir, item_name):
    if item_name == 'management-actions':
        action_name = action["label"]
        action_slug = slugify(action_name).replace("-", "_")
        json_file = f'{action_slug}.json'
        json_path = f'{bp_dir}{action_slug}/{action_slug}/{json_file}'
    else:
        action_name = action["name"]
        action_slug = slugify(action_name).replace("-", "_")
        json_file = f'{action_slug}.json'
        json_path = f'{bp_dir}{action_slug}/{action_slug}.json'
    action_path = get_action_path_from_json(json_path, json_file)
    return action_name, action_path


def get_action_path_from_json(json_path, json_file):
    with open(json_path, 'r') as f:
        action_json = json.load(f)
    action_file = action_json["script-filename"]
    action_path = json_path.replace(json_file, action_file)
    return action_path
