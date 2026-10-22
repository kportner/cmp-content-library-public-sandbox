"""
Shared actions leveraged across the OneFuse XUI
"""
from c2_wrapper import create_hook, create_custom_field
from common.methods import set_progress
from cbhooks.models import HookPointAction, HookPoint
from onefuse.cloudbolt_admin import Utilities
from utilities.logger import ThreadLogger
from resourcehandlers.models import ResourceTechnology
from externalcontent.models import OSFamily
from xui.onefuse.globals import XUI_PATH

logger = ThreadLogger(__name__)

utilities = Utilities(logger)


def create_onefuse_params():
    # Create Parameters for modules if not exist
    cb_params = get_params()

    for cb_param in cb_params:
        for param_name in cb_param["names"]:
            description = cb_param["description"]
            logger.info(f'Creating Custom Field {param_name} for OneFuse XUI')
            cf = create_custom_field(param_name, param_name, "STR",
                                     required=True, description=description)
            cf.placeholder = cb_param["placeholder"]
            cf.save()


def get_params():
    return [
        {
            "names": ["OneFuse_ADPolicy"],
            "placeholder": "onefuse_endpoint:ad_policy_name",
            "description": "OneFuse Active Directory Policy"
        },
        {
            "names": ["OneFuse_DnsPolicy_Nic0", "OneFuse_DnsPolicy_Nic1",
                      "OneFuse_DnsPolicy_Nic2", "OneFuse_DnsPolicy_Nic3",
                      "OneFuse_DnsPolicy_Nic4", "OneFuse_DnsPolicy_Nic5",
                      "OneFuse_DnsPolicy_Nic6", "OneFuse_DnsPolicy_Nic7",
                      "OneFuse_DnsPolicy_Nic8", "OneFuse_DnsPolicy_Nic9"],
            "placeholder": "onefuse_endpoint:dns_policy_name:zone1:zone2",
            "description": "OneFuse Dns Policy"
        },
        {
            "names": ["OneFuse_IpamPolicy_Nic0", "OneFuse_IpamPolicy_Nic1",
                      "OneFuse_IpamPolicy_Nic2", "OneFuse_IpamPolicy_Nic3",
                      "OneFuse_IpamPolicy_Nic4", "OneFuse_IpamPolicy_Nic5",
                      "OneFuse_IpamPolicy_Nic6", "OneFuse_IpamPolicy_Nic7",
                      "OneFuse_IpamPolicy_Nic8", "OneFuse_IpamPolicy_Nic9"],
            "placeholder": "onefuse_endpoint:ipam_policy_name",
            "description": "OneFuse IPAM Policy"
        },
        {
            "names": ["OneFuse_NamingPolicy"],
            "placeholder": "onefuse_endpoint:naming_policy_name",
            "description": "OneFuse Naming Policy"
        },
        {
            "names": ["OneFuse_PropertyToolkit"],
            "placeholder": "onefuse_endpoint:true",
            "description": "Property to enable OneFuse Property Toolkit"
        },
        {
            "names": ["OneFuse_Tracking_Id"],
            "placeholder": "tracking_id",
            "description": "OneFuse Tracking ID Parameter."
        },
        {
            "names": ["OneFuse_ServiceNowCmdbPolicy"],
            "placeholder": "onefuse:linux",
            "description": "OneFuse ServiceNow CMDB Policy"
        },
    ]


def create_onefuse_actions():
    new_actions = get_actions_json()

    for new_action in new_actions:
        logger.info(f"Creating or updating OneFuse Action: "
                    f"{new_action['name']}")
        hook = create_cloudbolt_hook(new_action)
        hpa = create_hook_point_action(new_action, hook)

    set_failure_action_to_last()


def get_actions_json():
    return [
        {
            "name": "OneFuse - Property Toolkit",
            "source_code_url": f"{XUI_PATH}/actions/propertytoolkit/provision_ptk.py",
            "description": "Execute the OneFuse Property Toolkit",
            "states": [
                {
                    "hook_point": "generated_hostname_overwrite",
                    "run_seq": 1000
                },
                {
                    "hook_point": "pre_create_resource",
                    "run_seq": 1000
                },
                {
                    "hook_point": "pre_application",
                    "run_seq": 1000
                },
                {
                    "hook_point": "post_provision",
                    "run_seq": 1000,
                    "run_on_statuses": "SUCCESS,WARNING"
                }
            ]
        },
        {
            "name": "OneFuse - Provision Scripting",
            "source_code_url": f"{XUI_PATH}/actions/scripting/provision_scripting.py",
            "description": "Execute the OneFuse Scripting Module",
            "states": [
                {
                    "hook_point": "generated_hostname_overwrite",
                    "run_seq": 1005
                },
                {
                    "hook_point": "pre_create_resource",
                    "run_seq": 1005
                },
                {
                    "hook_point": "pre_application",
                    "run_seq": 1005
                },
                {
                    "hook_point": "post_provision",
                    "run_seq": 1005,
                    "run_on_statuses": "SUCCESS,WARNING"
                }
            ]
        },
        {
            "name": "OneFuse - Join AD Domain",
            "source_code_url": f"{XUI_PATH}/samples/cloudbolt_join_domain/onefuse_join_ad_domain.py",
            "description": "For a server that is using the OneFuse AD module, "
                           "complete the domain join from inside the guest OS."
                           " Note the required parameters listed in the "
                           "script.",
            "states": [
                {
                    "hook_point": "post_provision",
                    "run_seq": 1005,
                    "run_on_statuses": "SUCCESS,WARNING"
                }
            ],
            "resource_technologies": ["VMware vCenter"],
            "os_families": ["Windows"]
        },
        {
            "name": "OneFuse - Join AD Domain - Azure",
            "source_code_url": f"{XUI_PATH}/samples/cloudbolt_join_domain/onefuse_azure_join_domain.py",
            "description": "For a server that is using the OneFuse AD module, "
                           "complete the domain join from inside the guest OS"
                           " in Azure. Note the required parameters listed in "
                           "the script.",
            "states": [
                {
                    "hook_point": "post_provision",
                    "run_seq": 1005,
                    "run_on_statuses": "SUCCESS,WARNING"
                }
            ],
            "resource_technologies": ["Azure"],
            "os_families": ["Windows"]
        },
        {
            "name": "OneFuse - Provision Ansible Tower",
            "source_code_url": f"{XUI_PATH}/actions/ansible_tower/provision_ansible_tower.py",
            "description": "Execute the OneFuse Ansible Tower Module",
            "states": [
                {
                    "hook_point": "generated_hostname_overwrite",
                    "run_seq": 1010
                },
                {
                    "hook_point": "pre_create_resource",
                    "run_seq": 1010
                },
                {
                    "hook_point": "pre_application",
                    "run_seq": 1010
                },
                {
                    "hook_point": "post_provision",
                    "run_seq": 1010,
                    "run_on_statuses": "SUCCESS,WARNING"
                }
            ]
        },
        {
            "name": "OneFuse - Provision Pluggable Module",
            "source_code_url": f"{XUI_PATH}/actions/pluggable_modules/provision_module.py",
            "description": "Execute a OneFuse Pluggable Module",
            "states": [
                {
                    "hook_point": "generated_hostname_overwrite",
                    "run_seq": 1015
                },
                {
                    "hook_point": "pre_create_resource",
                    "run_seq": 1015
                },
                {
                    "hook_point": "pre_application",
                    "run_seq": 1015
                },
                {
                    "hook_point": "post_provision",
                    "run_seq": 1015,
                    "run_on_statuses": "SUCCESS,WARNING"
                }
            ]
        },
        {
            "name": "OneFuse - Provision Naming",
            "source_code_url": f"{XUI_PATH}/actions/naming/provision_naming.py",
            "description": "Execute the OneFuse Naming Module",
            "states": [
                {
                    "hook_point": "generated_hostname_overwrite",
                    "run_seq": 1150
                }
            ]
        },
        {
            "name": "OneFuse - Provision IPAM",
            "source_code_url": f"{XUI_PATH}/actions/ipam/provision_ipam.py",
            "description": "Execute the OneFuse IPAM Module",
            "states": [
                {
                    "hook_point": "pre_create_resource",
                    "run_seq": 1200
                }
            ]
        },
        {
            "name": "OneFuse - Provision DNS",
            "source_code_url": f"{XUI_PATH}/actions/dns/provision_dns.py",
            "description": "Execute the OneFuse DNS Module",
            "states": [
                {
                    "hook_point": "pre_create_resource",
                    "run_seq": 1300
                }
            ]
        },
        {
            "name": "OneFuse - Provision AD",
            "source_code_url": f"{XUI_PATH}/actions/ad/provision_ad.py",
            "description": "Execute the OneFuse Active Directory Module",
            "states": [
                {
                    "hook_point": "pre_create_resource",
                    "run_seq": 1500
                }
            ]
        },
        {
            "name": "OneFuse - Move OU - AD",
            "source_code_url": f"{XUI_PATH}/actions/ad/move_ou.py",
            "description": "For the OneFuse AD Module, Move a Computer object to the Final OU if the original execution placed the object in a Build OU.",
            "states": [
                {
                    "hook_point": "post_provision",
                    "run_seq": 1500,
                    "run_on_statuses": "SUCCESS,WARNING"
                }
            ]
        },
        {
            "name": "OneFuse - Provision ServiceNow CMDB",
            "source_code_url": f"{XUI_PATH}/actions/servicenow/provision_cmdb.py",
            "description": "Execute the OneFuse ServiceNow CMDB Module",
            "states": [
                {
                    "hook_point": "post_provision",
                    "run_seq": 1600,
                    "run_on_statuses": "SUCCESS,WARNING"
                }
            ]
        },
        {
            "name": "OneFuse - Update ServiceNow CMDB",
            "source_code_url": f"{XUI_PATH}/actions/servicenow/update_cmdb.py",
            "description": "Execute the OneFuse ServiceNow CMDB Module to update CI Records.",
            "states": [
                {
                    "hook_point": "post_servermodification",
                    "run_seq": 1600
                }
            ]
        },
        {
            "name": "OneFuse - De-Provision Scripting",
            "source_code_url": f"{XUI_PATH}/actions/scripting/deprovision_scripting.py",
            "description": "De-Provision the OneFuse Scripting Module",
            "states": [
                {
                    "hook_point": "post_decom",
                    "run_seq": 10
                }
            ]
        },
        {
            "name": "OneFuse - De-Provision Ansible Tower",
            "source_code_url": f"{XUI_PATH}/actions/ansible_tower/deprovision_ansible_tower.py",
            "description": "De-Provision the OneFuse Ansible Tower Module",
            "states": [
                {
                    "hook_point": "post_decom",
                    "run_seq": 15
                }
            ]
        },
        {
            "name": "OneFuse - De-Provision Pluggable Module",
            "source_code_url": f"{XUI_PATH}/actions/pluggable_modules/deprovision_module.py",
            "description": "De-Provision a pluggable module",
            "states": [
                {
                    "hook_point": "post_decom",
                    "run_seq": 20
                }
            ]
        },
        {
            "name": "OneFuse - De-Provision ServiceNow CMDB",
            "source_code_url": f"{XUI_PATH}/actions/servicenow/deprovision_cmdb.py",
            "description": "De-Provision the OneFuse ServiceNow CMDB Module",
            "states": [
                {
                    "hook_point": "post_decom",
                    "run_seq": 1100
                }
            ]
        },
        {
            "name": "OneFuse - De-Provision AD",
            "source_code_url": f"{XUI_PATH}/actions/ad/deprovision_ad.py",
            "description": "De-Provision the OneFuse Active Directory Module",
            "states": [
                {
                    "hook_point": "post_decom",
                    "run_seq": 1200
                }
            ]
        },
        {
            "name": "OneFuse - De-Provision DNS",
            "source_code_url": f"{XUI_PATH}/actions/dns/deprovision_dns.py",
            "description": "De-Provision the OneFuse DNS Module",
            "states": [
                {
                    "hook_point": "post_decom",
                    "run_seq": 1300
                }
            ]
        },
        {
            "name": "OneFuse - De-Provision IPAM",
            "source_code_url": f"{XUI_PATH}/actions/ipam/deprovision_ipam.py",
            "description": "De-Provision the OneFuse IPAM Module",
            "states": [
                {
                    "hook_point": "post_decom",
                    "run_seq": 1400
                }
            ]
        },
        {
            "name": "OneFuse - De-Provision Naming",
            "source_code_url": f"{XUI_PATH}/actions/naming/deprovision_naming.py",
            "description": "De-Provision the OneFuse Naming Module",
            "states": [
                {
                    "hook_point": "post_decom",
                    "run_seq": 1500
                }
            ]
        }
    ]


def create_cloudbolt_hook(new_action):
    try:
        description = new_action["description"]
    except:
        description = "OneFuse Plugin Action"
    try:
        resource_technologies = new_action["resource_technologies"]
        # rts = [ResourceTechnology.objects.get(name=rt) for rt in rt_names]
    except KeyError:
        resource_technologies = None
    try:
        os_families = new_action["os_families"]
        # os_families = [(OSFamily.objects.get(name=f) for f in osf_names)]
    except KeyError:
        os_families = None
    # create_hook does a get_or_create against just the name, all other params
    # are passed as defaults, so this will not overwrite any changes made
    # in a users environment
    hook = create_hook(
        name=new_action["name"],
        hook_point=None,
        module=new_action["source_code_url"],
        description=description,
        shared=True,
        enabled=True,
        resource_technologies=resource_technologies,
        os_families=os_families,
    )
    return hook


def set_failure_action_to_last():
    # Ensure that the Automatically decom server when provisioning fails HPA
    # Runs last (after all OneFuse)
    hpa_name = 'Automatically decom server when provisioning fails'
    run_seq = 2000
    try:
        hpa = HookPointAction.objects.get(name=hpa_name)
        # set_progress(f'Updating HPA: {hpa_name} to run_seq: {run_seq}')
        hpa.run_seq = run_seq
        hpa.save()
    except:
        # set_progress(f'"{hpa_name}" does not exist, ignoring.')
        pass


def create_hook_point_action(new_action, hook):
    # Create HookPointAction
    # set_progress(
    #    f'Starting hook point action creation for {new_action["name"]}')
    for state in new_action["states"]:
        # set_progress(f'Starting state: {state["hook_point"]}')
        hp_id = HookPoint.objects.get(name=state["hook_point"]).id
        try:
            description = new_action["description"]
        except:
            description = "OneFuse Plugin Action"
        defaults = {
            "enabled": True,
            "continue_on_failure": False,
            "run_seq": state["run_seq"],
            "description": description,
        }
        if state["hook_point"] == "post_provision":
            try:
                defaults.run_on_statuses = state["run_on_statuses"]
            except:
                pass
        hpa, _ = HookPointAction.objects.get_or_create(
            name=new_action["name"],
            hook=hook,
            hook_point_id=hp_id,
            defaults=defaults,
        )
        return hpa
