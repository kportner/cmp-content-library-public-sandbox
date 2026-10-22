if __name__ == '__main__':
    import os
    import sys
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
    sys.path.append('/opt/cloudbolt')
    django.setup()

import json
from jobs.models import Job
from common.methods import set_progress
from onefuse.cloudbolt_admin import CbOneFuseManager, Utilities
from utilities.logger import ThreadLogger

logger = ThreadLogger(__name__)


def run(job, **kwargs):
    server = job.server_set.first()
    if server:
        utilities = Utilities(logger)
        logger.debug(f"Dictionary of keyword args passed to this plug-in: "
                     f"{kwargs.items()}")
        hook_point = 'generated_hostname_overwrite'

        properties_stack = utilities.get_cb_object_properties(server,
                                                              hook_point)
        logger.debug(f'properties_stack: {properties_stack}')
        endpoint_policies = utilities.get_connection_and_policy_values(
            'OneFuse_NamingPolicy', properties_stack)
        logger.debug(f'endpoint_policies: {endpoint_policies}')
        main_policy = None
        additional_policies = []
        for endpoint_policy in endpoint_policies:
            if endpoint_policy["suffix"] == "":
                if main_policy:
                    logger.error(f'More than one '
                                 f'OneFuse_NamingPolicy was returned. '
                                 f'endpoint_policies: {endpoint_policies}')
                    return ("FAILURE", 
                            "",
                            f"More than one main naming policy was found.")
                else:
                    main_policy = endpoint_policy
            else:
                if endpoint_policy["suffix"].startswith("_Additional_"):
                    endpoint_policy["suffix"] = endpoint_policy["suffix"][12:]
                    additional_policies.append(endpoint_policy)
                    
        logger.debug(f'main_policy: {main_policy}')
        if main_policy:
            onefuse_endpoint = main_policy["endpoint"]
            policy_name = main_policy["policy"]
            logger.debug(f"Starting OneFuse Naming Policy: "
                         f"{policy_name}, Endpoint: "
                         f"{onefuse_endpoint}")
            try:
                tracking_id = server.OneFuse_Tracking_Id
            except:
                tracking_id = ""
            from xui.onefuse.globals import VERIFY_CERTS
            ofm = CbOneFuseManager(onefuse_endpoint, VERIFY_CERTS,
                                   logger=logger)
            set_progress(f'Calling OneFuse to provision Name '
                         f'Managed Object. Policy: {policy_name}')
            name_json = ofm.provision_naming(policy_name, properties_stack,
                                                 tracking_id)
            logger.debug(f'name_json: {name_json}')
            machine_name = name_json.get("name")
            server.hostname = machine_name
            name_json["endpoint"] = onefuse_endpoint
            utilities.check_or_create_cf("OneFuse_Naming")
            server.OneFuse_Naming = json.dumps(name_json)
            server.OneFuse_Tracking_Id = name_json.get("trackingId")
            server.save()
            logger.info(f"hostname being set to: {server.hostname}")
        else:
            logger.info("OneFuse_NamingPolicy parameter is not set on "
                        "the server, OneFuse Naming will not be "
                        "executed. Keeping existing hostname")
        
        logger.debug(f'additional_policies: {additional_policies}')
        if additional_policies:
            for additional_policy in additional_policies:
                onefuse_endpoint = additional_policy["endpoint"]
                additional_policy_name = additional_policy["policy"]
                suffix = additional_policy["suffix"]
                logger.debug(f"Starting OneFuse Additional Naming Policy: "
                             f"{additional_policy_name}, Endpoint: "
                             f"{onefuse_endpoint}, Suffix: {suffix},")
                try:
                    tracking_id = server.OneFuse_Tracking_Id
                except:
                    tracking_id = ""
                from xui.onefuse.globals import VERIFY_CERTS
                ofm = CbOneFuseManager(onefuse_endpoint, VERIFY_CERTS,
                                       logger=logger)
                set_progress(f'Calling OneFuse to provision Additional Name '
                             f'Managed Object. Policy: '
                             f'{additional_policy_name}')
                additional_name_json = ofm.provision_naming(
                                                    additional_policy_name,
                                                    properties_stack,
                                                    tracking_id)
                logger.debug(f'additional_name_json: {name_json}')
                additional_name_json["endpoint"] = onefuse_endpoint
                additional_prop = f'OneFuse_Naming_Additional_{suffix}'
                utilities.check_or_create_cf(additional_prop)
                server.set_value_for_custom_field(
                                            additional_prop, 
                                            json.dumps(additional_name_json))
                server.OneFuse_Tracking_Id = additional_name_json.get(
                                                                "trackingId")
                server.save()
        else:
            logger.info("OneFuse_NamingPolicy_Additional_ parameter "
                        "is not set on the server, Additional OneFuse Naming "
                        "will not be executed.")
        if machine_name:
            return "SUCCESS", machine_name, ""
        else:
            return "SUCCESS", "", ""
    else:
        logger.error("Server was not found")
        return "FAILURE", "", f"Server was not found."


if __name__ == '__main__':
    job_id = sys.argv[1]
    job = Job.objects.get(id=job_id)
    run = run(job)
    if run[0] == 'FAILURE':
        set_progress(run[1])