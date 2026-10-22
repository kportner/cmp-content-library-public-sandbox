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
    utilities = Utilities(logger)
    for server in job.server_set.all():
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
            cmdb_exec_keys.sort(reverse=True)
            # Process the main_policy last
            if main_policy:
                cmdb_exec_keys.append(main_policy)
            logger.debug(f'cmdb_exec_keys: {cmdb_exec_keys}')

            if len(cmdb_exec_keys) > 0:
                for cmdb_exec_key in cmdb_exec_keys:
                    cfv = server.get_cfv_for_custom_field(cmdb_exec_key).str_value
                    logger.debug(f'cfv: {cfv}, cmdb_exec_key: {cmdb_exec_key}')
                    mo = json.loads(cfv)
                    onefuse_endpoint = mo["endpoint"]
                    mo_id = mo["id"]
                    if onefuse_endpoint and mo_id:
                        logger.debug(f"Starting OneFuse Delete CMDB "
                                     f" Object. Endpoint: {onefuse_endpoint}, "
                                     f"CMDB ID: {mo_id}")
                        # Delete Name Object
                        from xui.onefuse.globals import \
                            VERIFY_CERTS
                        ofm = CbOneFuseManager(onefuse_endpoint, VERIFY_CERTS,
                                               logger=logger)
                        set_progress(f'Calling OneFuse to deprovision CMDB '
                                     f'Managed Object. ID: {mo_id}')
                        deleted_obj_name = ofm.deprovision_cmdb(mo_id)
                        return_str = f"CMDB Record was successfully deleted " \
                                     f"from the OneFuse database. Name: " \
                                     f"{deleted_obj_name}"
                        return "SUCCESS", return_str, ""
                    else:
                        logger.info(f"OneFuse ServiceNow CMDB endpoint or ID "
                                    f"was missing, Execution skipped")
                        return "SUCCESS", "", ""
            else:
                logger.info(f"No matching OneFuse CMDB properties found, "
                            f"Execution skipped")
                return "SUCCESS", "", ""
        else:
            logger.error(f"No matching OneFuse CMDB properties found, "
                         f"Execution skipped")
            return "SUCCESS", "", ""


if __name__ == '__main__':
    job_id = sys.argv[1]
    job = Job.objects.get(id=job_id)
    run = run(job)
    if run[0] == 'FAILURE':
        set_progress(run[1])
