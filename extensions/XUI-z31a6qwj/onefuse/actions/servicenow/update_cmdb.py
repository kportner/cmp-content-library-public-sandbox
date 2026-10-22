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


def run(job, *args, **kwargs):
    for server in job.server_set.all():
        utilities = Utilities(logger)
        logger.debug(f"Dictionary of keyword args passed to this "
                     f"plug-in: {kwargs.items()}")
        hook_point = kwargs.get("hook_point")
        properties_stack = utilities.get_cb_object_properties(server,
                                                              hook_point)
        prefix = 'OneFuse_ServiceNowCmdb'
        matching_props = utilities.get_matching_property_names(prefix,
                                                               properties_stack)
        if len(matching_props) > 0:
            main_policy = None
            cmdb_exec_keys = []
            for matching_prop in matching_props:
                suffix = matching_prop.replace(prefix, '')
                if suffix == '':
                    main_policy = matching_prop
                elif suffix.find("_") == 0:
                    cmdb_exec_keys.append(matching_prop)
            cmdb_exec_keys.sort()
            # Process the main_policy first
            if main_policy:
                cmdb_exec_keys.insert(0, main_policy)
            logger.debug(f'cmdb_exec_keys: {cmdb_exec_keys}')

            for cmdb_exec_key in cmdb_exec_keys:
                cfv = server.get_cfv_for_custom_field(cmdb_exec_key).str_value
                logger.debug(f'cfv: {cfv}, cmdb_exec_key: {cmdb_exec_key}')
                mo = json.loads(cfv)
                onefuse_endpoint = mo["endpoint"]
                mo_id = mo["id"]
                if onefuse_endpoint and mo_id:
                    logger.debug(f"Starting OneFuse Update CMDB Object. "
                                 f"Endpoint: {onefuse_endpoint}, CMDB ID: "
                                 f"{mo_id}")
                    # Delete Name Object
                    from xui.onefuse.globals import VERIFY_CERTS
                    ofm = CbOneFuseManager(onefuse_endpoint, VERIFY_CERTS,
                                           logger=logger)
                    set_progress(f'Calling OneFuse to update CMDB '
                                 f'Managed Object. ID: {mo_id}')
                    response_json = ofm.update_cmdb(properties_stack, mo_id)
                    response_json["endpoint"] = onefuse_endpoint
                    cf_name = cmdb_exec_key
                    utilities.check_or_create_cf(cf_name)
                    # Deleting the execution details from the CF. Execution
                    # makes the MO too large for the CB DB
                    del response_json["executionDetails"]
                    response_json["OneFuse_Suffix"] = mo["OneFuse_Suffix"]
                    server.set_value_for_custom_field(cf_name,
                                                      json.dumps(
                                                          response_json))
                    server.OneFuse_Tracking_Id = response_json["trackingId"]
                    server.save()
                    return_str = f"CMDB Record was successfully Updated. "
                    return "SUCCESS", return_str, ""
                else:
                    logger.info(f"OneFuse ServiceNow CMDB endpoint or ID was "
                                f"missing, Execution skipped")
                    return "SUCCESS", "", ""
        else:
            logger.info(f"Existing OneFuse CMDB policy, not found. "
                        f"Execution skipped")
            return "SUCCESS", "", ""


if __name__ == '__main__':
    job_id = sys.argv[1]
    job = Job.objects.get(id=job_id)
    run = run(job)
    if run[0] == 'FAILURE':
        set_progress(run[1])
