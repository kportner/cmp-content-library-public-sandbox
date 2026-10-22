if __name__ == "__main__":
    import os
    import sys
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
    sys.path.append("/opt/cloudbolt")
    sys.path.append("/var/opt/cloudbolt/proserv")
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
        logger.debug(f"Dictionary of keyword args passed to this "
                     f"plug-in: {kwargs.items()}")
        hook_point = kwargs.get("hook_point")
        properties_stack = utilities.get_cb_object_properties(server,
                                                              hook_point)
        logger.debug(f'properties_stack: {properties_stack}')
        endpoint_policies = utilities.get_connection_and_policy_values(
            'OneFuse_ADPolicy', properties_stack)
        logger.debug(f'endpoint_policies: {endpoint_policies}')
        main_policy = None
        additional_policies = []
        for endpoint_policy in endpoint_policies:
            if endpoint_policy["suffix"] == "":
                if main_policy:
                    logger.error(f'More than one '
                                 f'OneFuse_ADPolicy was returned. '
                                 f'endpoint_policies: {endpoint_policies}')
                    return ("FAILURE", 
                            "",
                            f"More than one main AD policy was found.")
                else:
                    main_policy = endpoint_policy
            else:
                if endpoint_policy["suffix"].startswith("_Additional_"):
                    endpoint_policy["suffix"] = endpoint_policy["suffix"][12:]
                    additional_policies.append(endpoint_policy)
        
        if main_policy:
            onefuse_endpoint = main_policy["endpoint"]
            policy_name = main_policy["policy"]
            try:
                tracking_id = server.OneFuse_Tracking_Id
            except:
                tracking_id = ""
            from xui.onefuse.globals import VERIFY_CERTS
            ofm = CbOneFuseManager(onefuse_endpoint, VERIFY_CERTS,
                                   logger=logger)
            hostname = server.hostname
            set_progress(f'Calling OneFuse to provision Active Directory '
                         f'Managed Object. Policy: {policy_name}')
            response_json = ofm.provision_ad(policy_name, properties_stack,
                                             hostname, tracking_id)
            response_json["endpoint"] = onefuse_endpoint
            state = response_json["state"]
            utilities.check_or_create_cf("OneFuse_AD_State")
            server.set_value_for_custom_field("OneFuse_AD_State", state)
            utilities.check_or_create_cf("OneFuse_AD")
            server.set_value_for_custom_field("OneFuse_AD",
                                              json.dumps(response_json))
            server.OneFuse_Tracking_Id = response_json["trackingId"]
            server.save()
            logger.info(f"AD object completed for: {server.hostname}")
        else:
            logger.info("OneFuse_ADPolicy parameter is not set on "
                        "the server.")
                        
        if len(additional_policies) > 0:
            for additional_policy in additional_policies:
                onefuse_endpoint = additional_policy["endpoint"]
                policy_name = additional_policy["policy"]
                suffix = additional_policy["suffix"]
                properties_stack["OneFuse_Suffix"] = suffix
                try:
                    tracking_id = server.OneFuse_Tracking_Id
                except:
                    tracking_id = ""
                from xui.onefuse.globals import VERIFY_CERTS
                ofm = CbOneFuseManager(onefuse_endpoint, VERIFY_CERTS,
                                       logger=logger)
                try:
                    name_key = f'OneFuse_Naming_Additional_{suffix}'
                    name_prop = properties_stack[name_key]
                    additional_hostname = name_prop["name"]
                except KeyError:
                    logger.info(f"Unable to find "
                                f"OneFuse_Naming_Additional_{suffix} property. "
                                f"Constructing baisc additional name: "
                                f"{server.hostname}-{suffix}")  
                    additional_hostname = f'{server.hostname}-{suffix}'
                set_progress(f'Calling OneFuse to provision Additional '
                             f'Active Directory Managed Object. '
                             f'Hostname: {additional_hostname} '
                             f'Policy: {policy_name}')
                response_json = ofm.provision_ad(policy_name, properties_stack,
                                                 additional_hostname, 
                                                 tracking_id)
                response_json["endpoint"] = onefuse_endpoint
                state = response_json["state"]
                additional_prop = f'OneFuse_AD_Additional_{suffix}'
                additional_state_prop = f'OneFuse_AD_AdditionalState_{suffix}'
                utilities.check_or_create_cf(additional_state_prop)
                server.set_value_for_custom_field(additional_state_prop, state)
                utilities.check_or_create_cf(additional_prop)
                server.set_value_for_custom_field(additional_prop,
                                                  json.dumps(response_json))
                server.OneFuse_Tracking_Id = response_json["trackingId"]
                server.save()
                logger.info(f"Additional AD object completed for Suffix: "
                            f"{suffix}")  
        else:
            logger.info("OneFuse_ADPolicy_Additional_ parameter(s) is not set "
                        "on the server.")
            
        return "SUCCESS", "", ""

    else:
        logger.error("Server was not found")
        return "FAILURE", "", "Server was not found"


if __name__ == "__main__":
    job_id = sys.argv[1]
    j = Job.objects.get(id=job_id)
    run = run(j)
    if run[0] == "FAILURE":
        set_progress(run[1])