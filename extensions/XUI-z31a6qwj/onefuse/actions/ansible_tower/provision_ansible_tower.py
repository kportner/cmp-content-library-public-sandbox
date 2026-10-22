if __name__ == '__main__':
    import os
    import sys
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
    sys.path.append('/opt/cloudbolt')
    django.setup()

import json
from common.methods import set_progress
from onefuse.cloudbolt_admin import CbOneFuseManager, Utilities
from utilities.logger import ThreadLogger
from jobs.models import Job

logger = ThreadLogger(__name__)


def run(job, **kwargs):
    server = job.server_set.first()
    if server:
        utilities = Utilities(logger)
        logger.debug(f"Checking server {server} for provision_at")
        logger.debug(f"Dictionary of keyword args passed to this "
                                  f"plug-in: {kwargs.items()}")
        hook_point = kwargs.get("hook_point")
        if hook_point is None:
            # hostname overwrite isn't passing the hook_point in to the job
            hook_point = 'generated_hostname_overwrite'
        properties_stack = utilities.get_cb_object_properties(server,
                                                              hook_point)
        module_prefix = 'OneFuse_AnsibleTowerPolicy_'
        if hook_point == "generated_hostname_overwrite":
            hook_point_string = "HostnameOverwrite"
        elif hook_point == "pre_create_resource":
            hook_point_string = "PreCreateResource"
        elif hook_point == "pre_application":
            hook_point_string = "PreApplication"
        elif hook_point == "post_provision":
            hook_point_string = "PostProvision"
        else:
            logger.debug(
                "Ansible Tower action launched at an unsupported hook "
                f"point: {hook_point}. Exiting")
            return "SUCCESS", "", ""
        endpoint_policies = utilities.get_connection_and_policy_values(
            f'{module_prefix}{hook_point_string}_', properties_stack)
        logger.debug(f'endpoint_policies: {endpoint_policies}')
        # Loop through endpoint policies and execute applicable AT policies
        if endpoint_policies:
            # Sort AT policies for hook point alphanumerically on suffix
            endpoint_policies.sort(key=lambda x: x["suffix"], reverse=False)
            for endpoint_policy in endpoint_policies:
                onefuse_endpoint = endpoint_policy["endpoint"]
                policy_name = endpoint_policy["policy"]
                suffix = endpoint_policy["suffix"]
                hosts = endpoint_policy["extras"]
                limit = endpoint_policy["extras2"]
                logger.debug(f"Starting OneFuse AT Policy: {policy_name}, "
                            f"Endpoint: {onefuse_endpoint}, suffix: {suffix}, "
                            f"hosts: {hosts}, limit: {limit}")
                try:
                    tracking_id = server.OneFuse_Tracking_Id
                except:
                    tracking_id = ""
                from xui.onefuse.globals import VERIFY_CERTS
                ofm = CbOneFuseManager(onefuse_endpoint, VERIFY_CERTS,
                                       logger=logger)
                set_progress(f'Calling OneFuse to provision Ansible Tower '
                             f'Managed Object. Policy: {policy_name}')
                response_json = ofm.provision_ansible_tower(policy_name,
                                                            properties_stack,
                                                            hosts, limit,
                                                            tracking_id)
                response_json["endpoint"] = onefuse_endpoint
                response_json["OneFuse_CBHookPointString"] = hook_point_string
                response_json["OneFuse_Suffix"] = suffix
                output_property = f'OneFuse_AnsibleTower_{suffix}'
                response_json = utilities.delete_output_job_results(
                    response_json, 'ansible_tower')
                utilities.check_or_create_cf(output_property, "TXT")
                server.set_value_for_custom_field(output_property,
                                                  json.dumps(response_json))
                server.OneFuse_Tracking_Id = response_json["trackingId"]
                server.save()
                logger.info(f"OneFuse Ansible Tower execution complete. for "
                             f"policy: {policy_name}")
            return "SUCCESS", "", ""
        else:
            logger.debug(
                "OneFuse_AnsibleTowerPolicy_ parameter for hook point:"
                f" {hook_point} is not set on the server, OneFuse "
                f"Ansible Tower will not be executed for hook point.")
    else:
        logger.debug("Server was not found")
        return "FAILURE", "", "Server was not found"


if __name__ == '__main__':
    job_id = sys.argv[1]
    job = Job.objects.get(id=job_id)
    run = run(job)
    if run[0] == 'FAILURE':
        set_progress(run[1])
