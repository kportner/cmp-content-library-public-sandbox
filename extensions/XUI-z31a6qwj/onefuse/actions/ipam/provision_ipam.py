if __name__ == '__main__':
    import os
    import sys
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
    sys.path.append('/opt/cloudbolt')
    django.setup()

import json
from common.methods import set_progress
from resourcehandlers.models import ResourceNetwork
from onefuse.cloudbolt_admin import CbOneFuseManager, Utilities
from xui.onefuse.globals import VERIFY_CERTS
from utilities.logger import ThreadLogger
from jobs.models import Job

logger = ThreadLogger(__name__)


def run(job, **kwargs):
    server = job.server_set.first()
    if server:
        utils = Utilities(logger)
        logger.debug(f"Dictionary of keyword args passed to this"
                     f" plug-in: {kwargs.items()}")
        hook_point = kwargs.get("hook_point")
        properties_stack = utils.get_cb_object_properties(server,
                                                              hook_point)
        endpoint_policies = utils.get_connection_and_policy_values(
            'OneFuse_IpamPolicy_Nic', properties_stack)
        logger.debug(f'endpoint_policies: {endpoint_policies}')
        if endpoint_policies:
            for endpoint_policy in endpoint_policies:
                provision_ipam(server, endpoint_policy, properties_stack, utils)
        else:
            logger.info("OneFuse_IpamPolicy_NicN parameter is not set on "
                         "the server")

        additional_policies = utils.get_connection_and_policy_values(
            'OneFuse_IpamPolicy_Additional_', properties_stack)
        logger.debug(f'additional_policies: {additional_policies}')
        if additional_policies:
            for additional_policy in additional_policies:
                provision_additional_ipam(server, additional_policy,
                                          properties_stack, utils)
        else:
             logger.info("OneFuse_Ipam_Additional_ parameters is not set on "
                         "the server")

        return "SUCCESS", "", ""

    else:
        logger.error("Server was not found")
        return "FAILURE", "", "Server was not found"


def provision_ipam(server, endpoint_policy, properties_stack, utils):
    onefuse_endpoint = endpoint_policy["endpoint"]
    policy_name = endpoint_policy["policy"]
    nic_suffix = int(endpoint_policy["suffix"])
    ipam_json = request_onefuse_ipam(server, onefuse_endpoint, policy_name,
                                     server.hostname, properties_stack)
    ipam_json["endpoint"] = onefuse_endpoint
    ip_address = ipam_json.get("ipAddress")
    nic_property = f'OneFuse_Ipam_Nic{nic_suffix}'
    utils.check_or_create_cf(nic_property)
    server.set_value_for_custom_field(nic_property,
                                      json.dumps(ipam_json))
    ip_network = ipam_json.get("network")
    dns_domain = ipam_json.get("dnsSuffix")
    domain_name_server = get_domain_name_server(ipam_json)
    server.set_value_for_custom_field(f'sc_nic_{nic_suffix}_ip', ip_address)
    if ip_network:
        # The Network Name is an optional field in an IPAM Policy. If it is
        # not set, the VM will remain on the original network.
        try:
            network = None
            resource_networks = ResourceNetwork.objects.filter(name=ip_network)
            for resource_network in resource_networks:
                rh_name_id_map = {rh.id: rh.name for rh in resource_network.get_resource_handlers()}
                if server.resource_handler_id in rh_name_id_map:
                    network = resource_network
                    break
            if network is None:
                raise Exception(f"Network {ip_network} does not exist in CloudBolt")
        except Exception as e:
            raise Exception(f"An error occurred while processing the network {ip_network}: {str(e)}")
        server.set_value_for_custom_field(f'sc_nic_{nic_suffix}', network)
    if dns_domain:
        server.set_value_for_custom_field(f'dns_domain',
                                          dns_domain)
    if domain_name_server:
        server.set_value_for_custom_field(f'domain_name_server',
                                          domain_name_server)
    set_gateway_and_subnet_mask(ipam_json, network)
    logger.debug(f'all nics: {server.nics.all()}')
    server.OneFuse_Tracking_Id = ipam_json["trackingId"]
    server.save()
    logger.info(f"IP being set to: {ip_address}")


def get_domain_name_server(ipam_json):
    domain_name_server = ""
    if ipam_json.get("primaryDns"):
        domain_name_server = ipam_json.get("primaryDns")
    if ipam_json.get("secondaryDns"):
        if domain_name_server:
            domain_name_server += ','
        domain_name_server += ipam_json.get("secondaryDns")
    return domain_name_server


def set_gateway_and_subnet_mask(ipam_json, network):
    """
    This method will set the gateway and subnet mask on the CloudBolt Network
    if it isn't already set. If the network already has a gateway and subnet
    mask, it will not be overwritten, this will throw an error if the network
    subnet mask and gateway do not match what was passed back from OneFuse.
    This prevents from having to set up a netmask and gateway in CloudBolt for
    each network if netmask and gateway are already defined in the IPAM Policy.
    """
    gateway = ipam_json.get("gateway")
    netmask = ipam_json.get("netmask")
    if gateway:
        if not network.gateway:
            logger.info(f"Setting gateway for network {network.name} to "
                        f"{gateway}")
            network.gateway = gateway
            network.save()
        elif network.gateway != gateway:
            raise Exception(f"Gateway for network {network.name} is already "
                            f"set to {network.gateway}, cannot set to "
                            f"{gateway}")
    if netmask:
        if not network.netmask:
            logger.info(f"Setting subnet mask for network {network.name} to "
                        f"{netmask}")
            network.netmask = netmask
            network.save()
        elif network.netmask != netmask:
            raise Exception(f"Subnet Mask for network {network.name} is "
                            f"already set to {network.netmask}, cannot "
                            f"set to {netmask}")


def provision_additional_ipam(server, additional_policy, properties_stack,
                              utils):
    onefuse_endpoint = additional_policy["endpoint"]
    policy_name = additional_policy["policy"]
    nic_suffix = additional_policy["suffix"]
    try:
        name_key = f'OneFuse_Naming_Additional_{nic_suffix}'
        name_prop = properties_stack[name_key]
        ipam_hostname = name_prop["name"]
    except KeyError:
        ipam_hostname = f'{server.hostname}-{nic_suffix}'
    ipam_json = request_onefuse_ipam(server, onefuse_endpoint, policy_name,
                                     ipam_hostname, properties_stack)
    ipam_json["endpoint"] = onefuse_endpoint
    nic_property = f'OneFuse_Ipam_Additional_{nic_suffix}'
    utils.check_or_create_cf(nic_property)
    server.set_value_for_custom_field(nic_property,
                                      json.dumps(ipam_json))
    server.OneFuse_Tracking_Id = ipam_json["trackingId"]
    server.save()


def request_onefuse_ipam(server, onefuse_endpoint, policy_name, hostname,
                         properties_stack):
    logger.debug(f"Starting OneFuse IPAM Policy: "
                 f"{policy_name}, Endpoint: {onefuse_endpoint}")
    try:
        tracking_id = server.OneFuse_Tracking_Id
    except:
        tracking_id = ""
    ofm = CbOneFuseManager(onefuse_endpoint, VERIFY_CERTS, logger=logger)
    set_progress(f'Calling OneFuse to provision IPAM '
                 f'Managed Object. Policy: {policy_name}')
    return ofm.provision_ipam(policy_name, properties_stack, hostname,
                              tracking_id)


if __name__ == '__main__':
    job_id = sys.argv[1]
    job = Job.objects.get(id=job_id)
    run = run(job)
    if run[0] == 'FAILURE':
        set_progress(run[1])
