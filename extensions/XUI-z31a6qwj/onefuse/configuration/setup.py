# module imports
from c2_wrapper import create_hook
from infrastructure.models import CustomField
from common.methods import set_progress
from cbhooks.models import CloudBoltHook, HookPointAction, HookPoint
from utilities.logger import ThreadLogger
from resourcehandlers.models import ResourceTechnology
from externalcontent.models import OSFamily
from utilities.run_command import execute_command
from packaging import version
from xui.onefuse.globals import XUI_PATH

logger = ThreadLogger(__name__)


def create_onefuse_params():
    from onefuse.cloudbolt_admin import Utilities
    utilities = Utilities(logger)
    # Create Parameters for modules if not exist
    cb_params = [
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

    for cb_param in cb_params:
        for param_name in cb_param["names"]:
            set_progress(f'Creating or updating param: {param_name}')
            utilities.check_or_create_cf(param_name)
            cf = CustomField.objects.get(name=param_name)
            cf.required = True
            cf.placeholder = cb_param["placeholder"]
            cf.description = cb_param["description"]
            cf.save()


def create_onefuse_actions():
    new_actions = [
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

    for new_action in new_actions:
        # Create Action (CloudBoltHook)
        onefuse_hook = {
            'name': new_action["name"],
            'hook_point': None,
            'module': new_action["source_code_url"],
        }
        hook = create_hook(**onefuse_hook)

        try:
            hook.description = new_action["description"]
        except:
            hook.description = "OneFuse Plugin Action"
        hook.shared = True
        hook.save()
        # Link Resource Technologies if present
        try:
            resource_technologies = new_action["resource_technologies"]
            for technology in resource_technologies:
                resource_technology = ResourceTechnology.objects.get(
                    name=technology)
                hook.resource_technologies.add(resource_technology)
        except KeyError:
            pass
        # Link OS Families if present
        try:
            os_families = new_action["os_families"]
            for family in os_families:
                os_family = OSFamily.objects.get(
                    name=family)
                hook.os_families.add(os_family)
        except KeyError:
            pass

        # Create HookPointAction
        # set_progress(
        #     f'Starting hook point action creation for {new_action["name"]}')
        for state in new_action["states"]:
            set_progress(f'Starting state: {state["hook_point"]}')
            hp_id = HookPoint.objects.get(name=state["hook_point"]).id
            try:
                hpa = HookPointAction.objects.get(
                    name=new_action["name"],
                    hook=hook,
                    hook_point_id=hp_id
                )
                set_progress(f'State exists: {state["hook_point"]}')
            except:
                set_progress(
                    f'State does not exist, creating: {state["hook_point"]}')
                hpa = HookPointAction(
                    name=new_action["name"],
                    hook=hook,
                    hook_point_id=hp_id
                )
                hpa.enabled = True
            hpa.continue_on_failure = False
            hpa.run_seq = state["run_seq"]
            try:
                hpa.description = new_action["description"]
            except:
                hpa.description = "OneFuse Plugin Action"
            if state["hook_point"] == "post_provision":
                try:
                    hpa.run_on_statuses = state["run_on_statuses"]
                except:
                    pass
            hpa.save()

    # Ensure that the Automatically decom server when provisioning fails HPA
    # Runs last (after all OneFuse)
    hpa_name = 'Automatically decom server when provisioning fails'
    run_seq = 2000
    try:
        hpa = HookPointAction.objects.get(
            name=hpa_name,
        )
        set_progress(f'Updating HPA: {hpa_name} to run_seq: {run_seq}')
        hpa.run_seq = run_seq
        hpa.save()
    except:
        set_progress(f'"{hpa_name}" does not exist, ignoring.')
        pass


def check_onefuse_version():
    minimum_version = '2022.3.2'
    try:
        import onefuse
    except ModuleNotFoundError:
        execute_command("pip install onefuse")
        import onefuse
    current_version = onefuse.__version__
    set_progress(f"OneFuse Python Version: {current_version}")
    upgrade_version = version.parse(current_version) < version.parse(
        minimum_version)
    if upgrade_version:
        set_progress("Upgrading OneFuse PIP Package")
        execute_command("pip install onefuse --upgrade")


def run(job, **kwargs):
    set_progress(f'Starting OneFuse Configuration Script')


if __name__ == '__main__':
    run()
