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
from utilities.logger import ThreadLogger
from jobs.models import Job
from onefuse.cloudbolt_admin import CbOneFuseManager, Utilities


logger = ThreadLogger(__name__)


def run(job, *args, **kwargs):
    utilities = Utilities(logger)
    for server in job.server_set.all():
        logger.debug(f"Dictionary of keyword args passed to this "
                     f"plug-in: {kwargs.items()}")
        hook_point = 'post_provision'
        properties_stack = utilities.get_cb_object_properties(server,
                                                                  hook_point)
        ad_state = server.get_cfv_for_custom_field("OneFuse_AD_State")
        logger.debug(f'ad_state: {ad_state}')
        if ad_state and ad_state.value_as_string == 'build':
            object_json = server.get_cfv_for_custom_field("OneFuse_AD")
            if object_json:
                object_json = object_json.value_as_string
                mo = json.loads(object_json)
                onefuse_endpoint = mo["endpoint"]
                mo_name = mo["name"]
                mo_id = mo["id"]
                if onefuse_endpoint and mo_id:
                    logger.info(f"Starting OneFuse AD Move OU. Name: "
                                f"{mo_name}, Endpoint: "
                                f"{onefuse_endpoint}, AD ID: {mo_id}")
                    from xui.onefuse.globals import VERIFY_CERTS
                    ofm = CbOneFuseManager(onefuse_endpoint, VERIFY_CERTS,
                                       logger=logger)
                    set_progress(f'Calling OneFuse to move Active Directory '
                                 f'OU for Managed Object. ID: {mo_id}')
                    response_json = ofm.move_ou(mo_id)
                    response_json["endpoint"] = onefuse_endpoint
                    state = response_json["state"]
                    utilities.check_or_create_cf("OneFuse_AD_State")
                    server.set_value_for_custom_field("OneFuse_AD_State", state)
                    utilities.check_or_create_cf("OneFuse_AD")
                    server.set_value_for_custom_field("OneFuse_AD",
                                                      json.dumps(response_json))
                    server.OneFuse_Tracking_Id = response_json["trackingId"]
                    server.save()
                    return_str = f"Move OU was successfully completed for " \
                                 f"{server.hostname}"
                else:
                    logger.info(f"OneFuse AD endpoint or ID was missing, "
                                f"Execution skipped")
        else:
            logger.info(f"OneFuse AD state was either missing or not equal "
                        f"to 'Build', Execution skipped")
                
        additional_prop = 'OneFuse_AD_Additional_'
        additional_objects = utilities.get_key_value_objects(additional_prop,
                                                             properties_stack)
        logger.debug(f'additional_objects: {additional_objects}')
        for additional_object in additional_objects:
            mo = additional_object["value"]
            suffix = additional_object["suffix"]
            onefuse_endpoint = mo["endpoint"]
            mo_name = mo["name"]
            mo_id = mo["id"]
            mo_state = mo["state"]
            if mo_state and mo_state == 'build':
                logger.info(f"Starting OneFuse Additional AD Move OU. "
                            f"Suffix: {suffix}, "
                            f"Policy: {mo_name}, Endpoint: "
                            f"{onefuse_endpoint}, AD ID: {mo_id}")
                from xui.onefuse.globals import VERIFY_CERTS
                ofm = CbOneFuseManager(onefuse_endpoint, VERIFY_CERTS,
                                   logger=logger)
                set_progress(f'Calling OneFuse to move Additional '
                             f'Active Directory Move OU '
                             f'for Managed Object. ID: {mo_id}')
                response_json = ofm.move_ou(mo_id)
                response_json["endpoint"] = onefuse_endpoint
                state = response_json["state"]
                additional_prop = f'OneFuse_AD_Additional_{suffix}'
                additional_state_prop = (f'OneFuse_AD_AdditionalState'+
                                         f'_{suffix}')
                utilities.check_or_create_cf(additional_state_prop)
                server.set_value_for_custom_field(additional_state_prop, 
                                                  state)
                utilities.check_or_create_cf(additional_prop)
                server.set_value_for_custom_field(additional_prop,
                                                  json.dumps(response_json))
                server.OneFuse_Tracking_Id = response_json["trackingId"]
                server.save()
                return_str = f"Move OU was successfully completed for " \
                             f"{server.hostname}"
            else:
                logger.info(f"OneFuse Additional AD state for "
                            f"Suffix {suffix} "
                            f"was either missing or not equal "
                            f"to 'Build', Execution skipped")
        
        return "SUCCESS", "", ""

if __name__ == "__main__":
    job_id = sys.argv[1]
    j = Job.objects.get(id=job_id)
    run = run(j)
    if run[0] == "FAILURE":
        set_progress(run[1])