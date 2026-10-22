from common.methods import set_progress
import json
from onefuse.cloudbolt_admin import CbOneFuseManager, Utilities


def run(job, *args, **kwargs):
    resource = job.resource_set.first()
    if resource:
        utilities = Utilities()
        set_progress(f"This plug-in is running for resource {resource}")
        utilities.verbose_logging(f"Dictionary of keyword args passed to this "
                                  f"plug-in: {kwargs.items()}")
        onefuse_endpoint = "{{onefuse_endpoint}}"
        at_policy_name = "{{at_policy_name}}"
        tracking_id = ""
        hosts = "{{hosts}}"
        limit = "{{limit}}"
        set_progress(f"Starting OneFuse Ansible Tower Policy: "
                     f"{at_policy_name}, Endpoint: {onefuse_endpoint}")
        ofm = CbOneFuseManager(onefuse_endpoint)
        properties_stack = utilities.get_cb_object_properties(resource)
        response_json = ofm.provision_ansible_tower(at_policy_name,
                                                    properties_stack, hosts,
                                                    limit, tracking_id)
        utilities.check_or_create_cf("OneFuse_AnsibleTower_Resource")
        response_json["endpoint"] = onefuse_endpoint
        resource.OneFuse_AnsibleTower_Resource = json.dumps(response_json)
        resource.OneFuse_Tracking_Id = response_json.get("trackingId")
        resource.save()
        set_progress(f"Resource name being set to: {resource.name}")
        return "SUCCESS", "Ansible Tower successful", ""
    else:
        set_progress("Resource was not found")
