if __name__ == '__main__':
    import os
    import sys
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
    sys.path.append('/opt/cloudbolt')
    django.setup()

import json
from common.methods import set_progress
from jobs.models import Job
from onefuse.cloudbolt_admin import CbOneFuseManager, Utilities
from utilities.logger import ThreadLogger

logger = ThreadLogger(__name__)


def run(job, **kwargs):
    server = job.server_set.first()
    if server:
        utilities = Utilities(logger)
        logger.debug(f"Dictionary of keyword args passed to this "
                     f"plug-in: {kwargs.items()}")
        hook_point = kwargs.get("hook_point")
        properties_stack = utilities.get_cb_object_properties(server,
                                                              hook_point)
        endpoint_policies = utilities.get_connection_and_policy_values(
            'OneFuse_ServiceNowCmdbPolicy', properties_stack)
        logger.debug(f'endpoint_policies: {endpoint_policies}')
        if len(endpoint_policies) > 0:
            main_policy = None
            cmdb_policies = []
            for endpoint_policy in endpoint_policies:
                suffix = endpoint_policy["suffix"]
                if suffix == '':
                    main_policy = endpoint_policy
                elif suffix.find("_") == 0:
                    # Remove the leading underscore from suffix
                    endpoint_policy["suffix"] = endpoint_policy["suffix"][1:]
                    cmdb_policies.append(endpoint_policy)

            cmdb_policies = sorted(cmdb_policies, key=lambda k: k['suffix'])
            # Process the main_policy first
            cmdb_policies.insert(0, main_policy)

            for endpoint_policy in cmdb_policies:
                onefuse_endpoint = endpoint_policy["endpoint"]
                policy_name = endpoint_policy["policy"]
                suffix = endpoint_policy["suffix"]
                logger.debug(f"Starting OneFuse ServiceNow CMDB Policy: "
                             f"{policy_name}, Endpoint: {onefuse_endpoint}")
                try:
                    tracking_id = server.OneFuse_Tracking_Id
                except:
                    tracking_id = ""
                from xui.onefuse.globals import VERIFY_CERTS
                ofm = CbOneFuseManager(onefuse_endpoint, VERIFY_CERTS,
                                       logger=logger)
                set_progress(f'Calling OneFuse to provision CMDB '
                             f'Managed Object. Policy: {policy_name}')
                response_json = ofm.provision_cmdb(policy_name,
                                                   properties_stack,
                                                   tracking_id)
                response_json["endpoint"] = onefuse_endpoint
                cf_name = f'OneFuse_ServiceNowCmdb'
                if endpoint_policy["suffix"] != '':
                    cf_name += f'_{endpoint_policy["suffix"]}'
                utilities.check_or_create_cf(cf_name)
                # Deleting the execution details from the CF. Execution makes
                # the MO too large for the CB DB
                del response_json["executionDetails"]
                response_json["OneFuse_Suffix"] = suffix
                server.set_value_for_custom_field(cf_name,
                                                  json.dumps(response_json))
                server.OneFuse_Tracking_Id = response_json["trackingId"]
                server.save()
                logger.info(f"CMDB object completed for: {server.hostname}")
            return "SUCCESS", "", ""
        else:
            logger.info("OneFuse_ServiceNowCmdbPolicy parameter is not set on "
                        "the server, OneFuse ServiceNow CMDB will not be "
                        "executed.")

    else:
        logger.error("Server was not found")
        return "FAILURE", "", "Server was not found"


if __name__ == '__main__':
    job_id = sys.argv[1]
    job = Job.objects.get(id=job_id)
    run = run(job)
    if run[0] == 'FAILURE':
        set_progress(run[1])
