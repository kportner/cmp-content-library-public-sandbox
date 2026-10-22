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


def run(job, *args, **kwargs):
    utils = Utilities(logger)
    for server in job.server_set.all():
        logger.debug(f"Dictionary of keyword args passed to this "
                     f"plug-in: {kwargs.items()}")
        hook_point = 'post_decom'
        properties_stack = utils.get_cb_object_properties(server,
                                                                  hook_point)
        object_json = server.get_cfv_for_custom_field("OneFuse_AD")
        logger.debug(f'object_json: {object_json}')
        if object_json:
            object_json = object_json.value_as_string
            mo = json.loads(object_json)
            onefuse_endpoint = mo["endpoint"]
            mo_name = mo["name"]
            mo_id = mo["id"]
            if onefuse_endpoint and mo_id:
                logger.debug(f"Starting OneFuse Delete AD Object. Policy: "
                             f"{mo_name}, Endpoint: {onefuse_endpoint}, AD ID: "
                             f"{mo_id}")
                # Delete Name Object
                from xui.onefuse.globals import VERIFY_CERTS
                ofm = CbOneFuseManager(onefuse_endpoint, VERIFY_CERTS,
                                       logger=logger)
                set_progress(f'Calling OneFuse to delete Active Directory '
                             f'Managed Object. ID: {mo_id}')
                deleted_obj_name = ofm.deprovision_ad(mo_id)
                logger.info(f"AD Computer was successfully deleted from the " 
                             f"OneFuse database. Name: {deleted_obj_name}")
            else:
                logger.info(f"OneFuse AD endpoint or ID was missing, "
                             f"Execution skipped")

        else:
            logger.info(f"OneFuse AD policy, endpoint or AD was "
                         f"missing, Execution skipped")
        
        additional_prop = 'OneFuse_AD_Additional_'
        additional_objects = utils.get_key_value_objects(additional_prop,
                                                         properties_stack)
        logger.debug(f'additional_objects: {additional_objects}')
        for additional_object in additional_objects:
            mo = additional_object["value"]
            suffix = additional_object["suffix"]
            onefuse_endpoint = mo["endpoint"]
            mo_name = mo["name"]
            mo_id = mo["id"]
            logger.debug(f"Starting OneFuse Delete "
                         f"Additional AD Object. "
                         f"Suffix: {suffix}, "
                         f"Policy: {mo_name}, "
                         f"Endpoint: {onefuse_endpoint}, AD ID: "
                         f"{mo_id}")
            from xui.onefuse.globals import VERIFY_CERTS
            ofm = CbOneFuseManager(onefuse_endpoint, VERIFY_CERTS,
                                   logger=logger)
            set_progress(f'Calling OneFuse to delete Additional '
                         f'Active Directory '
                         f'Managed Object. ID: {mo_id}')
            deleted_obj_name = ofm.deprovision_ad(mo_id)
            logger.info(f"Additional AD Computer was successfully "
                        f"deleted from the " 
                        f"OneFuse database. Name: {deleted_obj_name}")
        
        return "SUCCESS", "", ""

if __name__ == "__main__":
    job_id = sys.argv[1]
    j = Job.objects.get(id=job_id)
    run = run(j)
    if run[0] == "FAILURE":
        logger.error(run[1])