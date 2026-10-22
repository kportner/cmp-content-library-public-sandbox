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
        endpoint_policies = utilities.get_connection_and_policy_values(
            'OneFuse_DnsPolicy_Nic', properties_stack)
        logger.debug(f'endpoint_policies: {endpoint_policies}')
        if endpoint_policies:
            for endpoint_policy in endpoint_policies:
                onefuse_endpoint = endpoint_policy["endpoint"]
                policy_name = endpoint_policy["policy"]
                zones = []
                for zone in endpoint_policy["extras"].split(","):
                    zones.append(zone.strip())
                nic_suffix = int(endpoint_policy["suffix"])
                nic_ip_prop = f'sc_nic_{nic_suffix}_ip'
                try:
                    ip_address = server.get_cfvs_for_custom_field(
                        nic_ip_prop).first().value
                except:
                    err_msg = (
                        f"An IP address could not be determined for NIC "
                        f"{nic_suffix}. To use the OneFuse DNS module, "
                        f"you must use the {nic_ip_prop} property.")
                    raise Exception(err_msg)
                logger.debug(f"Starting OneFuse DNS Policy: "
                             f"{policy_name}, Endpoint: {onefuse_endpoint}, "
                             f"IP: {ip_address}, Zones: {zones}, NIC suffix: "
                             f"{nic_suffix}")
                try:
                    tracking_id = server.OneFuse_Tracking_Id
                except:
                    tracking_id = ""
                hostname = server.hostname
                from xui.onefuse.globals import VERIFY_CERTS
                ofm = CbOneFuseManager(onefuse_endpoint, VERIFY_CERTS,
                                       logger=logger)
                set_progress(f'Calling OneFuse to provision DNS '
                             f'Managed Object. Policy: {policy_name}')
                dns_json = ofm.provision_dns(policy_name, properties_stack,
                                             hostname, ip_address, zones,
                                             tracking_id)
                dns_json["endpoint"] = onefuse_endpoint
                nic_property = f'OneFuse_Dns_Nic{nic_suffix}'
                utilities.check_or_create_cf(nic_property)
                server.set_value_for_custom_field(nic_property,
                                                  json.dumps(dns_json))
                server.OneFuse_Tracking_Id = dns_json["trackingId"]
                server.save()
                logger.info(f"DNS record creation complete.")
        else:
            logger.info("OneFuse_DnsPolicy_NicN parameter is not set on "
                        "the server.")
        
        additional_policies = utilities.get_connection_and_policy_values(
            'OneFuse_DnsPolicy_Additional_', properties_stack)
        logger.debug(f'additional_policies: {additional_policies}')
        if additional_policies:
            for additional_policy in additional_policies:
                onefuse_endpoint = additional_policy["endpoint"]
                policy_name = additional_policy["policy"]
                zones = []
                for zone in additional_policy["extras"].split(","):
                    zones.append(zone.strip())
                suffix = additional_policy["suffix"]
                additional_ip = None
                try:
                    ip_key = f'OneFuse_IP_Additional_{suffix}'
                    additional_ip = properties_stack[ip_key]
                except KeyError:
                    logger.debug(f"Did not find a matching "
                                 f"OneFuse_IP_Additional_{suffix} "
                                 f"property. Searching for "
                                 f"OneFuse_Ipam_Additional_{suffix}")
                if not additional_ip:
                    try:
                        ipam_key = f'OneFuse_Ipam_Additional_{suffix}'
                        additional_ip = properties_stack[ipam_key]["ipAddress"]
                    except KeyError:
                        err_msg = (
                        f"An IP address could not be determined for Additional "
                        f"{suffix}. To use the OneFuse DNS module, "
                        f"you must use either use the {ip_key} property or "
                        f"have a matching {ipam_key} IPAM in place")
                        raise Exception(err_msg)
                    
                logger.debug(f"Starting OneFuse DNS Policy: "
                             f"{policy_name}, Endpoint: {onefuse_endpoint}, "
                             f"IP: {additional_ip}, "
                             f"Zones: {zones}, Additional Suffix: "
                             f"{suffix}")
                try:
                    tracking_id = server.OneFuse_Tracking_Id
                except:
                    tracking_id = ""
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
                from xui.onefuse.globals import VERIFY_CERTS
                ofm = CbOneFuseManager(onefuse_endpoint, VERIFY_CERTS,
                                       logger=logger)
                set_progress(f'Calling OneFuse to provision Additional DNS '
                             f'Managed Object. '
                             f'Hostname: {additional_hostname} '
                             f'IP: {additional_ip} '
                             f'Policy: {policy_name}')
                dns_json = ofm.provision_dns(policy_name, properties_stack,
                                             additional_hostname, 
                                             additional_ip, zones,
                                             tracking_id)
                dns_json["endpoint"] = onefuse_endpoint
                nic_property = f'OneFuse_Dns_Additional_{suffix}'
                utilities.check_or_create_cf(nic_property)
                server.set_value_for_custom_field(nic_property,
                                                  json.dumps(dns_json))
                server.OneFuse_Tracking_Id = dns_json["trackingId"]
                server.save()
                logger.info(f"DNS record creation complete.")
        else:
            logger.info("OneFuse_Dns_Additional_ parameter is not set on "
                        "the server.")
        
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