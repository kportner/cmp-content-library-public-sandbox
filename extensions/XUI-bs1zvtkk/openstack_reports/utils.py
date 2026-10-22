from resourcehandlers.openstack.gnocchi_wrapper import (
    TechnologyWrapper as VMDetailsWrapper,
)
import requests
from datetime import datetime

def format_megabytes(size):
    power = 2**10
    n = 0
    power_labels = ['MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']
    while size > power:
        size /= power
        n += 1
    return f"{round(size, 2)} {power_labels[n]}"


def format_bytes(size):
    power = 2**10
    n = 0
    power_labels = ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']
    while size > power:
        size /= power
        n += 1
    return f"{round(size, 2)} {power_labels[n]}"


def format_nanoseconds(nanoseconds):
    # Convert nanoseconds to seconds
    seconds = nanoseconds / 1e9
    
    # Check if it exceeds 60 seconds
    if seconds >= 60:
        # Convert seconds to minutes
        minutes = seconds / 60
        
        # Check if it exceeds 60 minutes
        if minutes >= 60:
            # Convert minutes to hours
            hours = minutes / 60
            return f"{hours:.2f} Hrs"
        else:
            return f"{minutes:.2f} Min"
    else:
        return f"{seconds:.2f} Sec"


def get_base_url(resource_handler, servie):
    port = VMDetailsWrapper._get_service_port(
        resource_handler, resource_handler, servie)
    if not "volume" in servie:
        return f"{resource_handler.protocol}://{resource_handler.ip}:{port}/{resource_handler.project_id}"
    return f"{resource_handler.protocol}://{resource_handler.ip}:{port}"


def get_vm_basic_inventory(resource_handler, server):
    try:
        base_url = get_base_url(resource_handler, "compute")
        url = f"{base_url}/servers/{server.resource_handler_svr_id}/diagnostics"
        headers = {
            "X-auth-token": resource_handler.api_auth_token,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-OpenStack-Nova-API-Version": "2.48"
        }
        if resource_handler._check_token_validation():
            headers["X-auth-token"] = resource_handler.api_auth_token
        else:
            token = resource_handler._generate_token()
            headers["X-auth-token"] = token
        response = requests.get(url, headers=headers,
                                verify=resource_handler.enable_ssl_verification)
        resource_handler = server.resource_handler
        wrapper = VMDetailsWrapper(resource_handler.cast(
        ), resource_handler.ip, server.resource_handler_svr_id, resource_handler.protocol)
        usage_for_vms = []
        metric_ids = wrapper._get_performance_metric_ids()
        usage_for_vms = wrapper.collect_vm_performance(
            "last_month", metric_ids)
        
        # Find peak values of CPU stats
        cpu_utilization_peak = 0
        memory_utilization_peak = 0
        disk_read_utilization_peak = 0
        disk_write_utilization_peak = 0
        network_incoming_utilization_peak = 0
        network_outgoing_utilization_peak = 0
        if usage_for_vms and response.status_code == 200:
            # Peak values for CPU Stats
            if usage_for_vms[0]["cpu_usage_values"]:
                cpu_usage_values = usage_for_vms[0]["cpu_usage_values"]
                cpu_utilization_peak = max(cpu_usage_values)

            # Peak values for Memory Stats
            if usage_for_vms[0]["mem_usage_values"]:
                mem_usage_values = usage_for_vms[0]["mem_usage_values"]
                memory_utilization_peak = max(mem_usage_values)

            # Peak values for Disk Read Stats
            if usage_for_vms[0]["disk_usage_values"]:
                disk_usage_values = usage_for_vms[0]["disk_usage_values"]
                disk_read_utilization_peak = max(disk_usage_values)
            
            # Peak values for Disk Write Stats
            if usage_for_vms[0]["disk_write_usage_values"]:
                disk_write_usage_values = usage_for_vms[0]["disk_write_usage_values"]
                disk_write_utilization_peak = max(disk_write_usage_values)

            # Peak values for Network Incoming Stats
            if usage_for_vms[0]["net_usage_values"]:
                net_usage_values = usage_for_vms[0]["net_usage_values"]
                network_incoming_utilization_peak = max(net_usage_values)
            
            # Peak values for Network Outgoing Stats
            if usage_for_vms[0]["net_outgoing_usage_values"]:
                net_outgoing_usage_values = usage_for_vms[0]["net_outgoing_usage_values"]
                network_outgoing_utilization_peak = max(net_outgoing_usage_values)
            response = response.json()
            server_dict = {
                "id": server.id,
                "name": server.hostname,
                "cpu": server.cpu_cnt,
                "memory": server.mem_size,
                "disk": server.disk_size,
                "nics": server.nics.all().count(),
                "os": response['hypervisor_os'],
                "uptime_in_days": round(response['uptime']/86400, 2),
                "uptime_in_hours": round(response['uptime']/3600, 2),
                "uptime_in_minutes": round(response['uptime']/60, 2),
                "cpu_utilization_peak": format_nanoseconds(cpu_utilization_peak),
                "cpu_utilization_avg": format_nanoseconds(usage_for_vms[0]["cpu_usage_average"]),
                "memory_utilization_peak": format_megabytes(memory_utilization_peak),
                "memory_utilization_avg": format_megabytes(usage_for_vms[0]["mem_usage_average"]),
                "disk_read_utilization_peak": format_bytes(disk_read_utilization_peak),
                "disk_read_utilization_avg": format_bytes(usage_for_vms[0]["disk_usage_latest"]),
                "disk_write_utilization_peak": format_bytes(disk_write_utilization_peak),
                "disk_write_utilization_avg": format_bytes(usage_for_vms[0]["disk_write_usage_latest"]),
                "network_incoming_utilization_peak": format_bytes(network_incoming_utilization_peak),
                "network_incoming_utilization_avg": format_bytes(usage_for_vms[0]["net_usage_average"]),
                "network_outgoing_utilization_peak": format_bytes(network_outgoing_utilization_peak),
                "network_outgoing_utilization_avg": format_bytes(usage_for_vms[0]["net_outgoing_usage_average"]),
            }
            return server_dict, True
        # elif response.status_code == 409:
        #     return {}, False
        else:
            return {}, False
    except Exception as e:
        return {}, False


def get_optimization_report(resource_handler):
    base_url = get_base_url(resource_handler, "volumev3")
    url = f"{base_url}/snapshots/detail"
    headers = {
        "X-auth-token": resource_handler.api_auth_token,
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    if resource_handler._check_token_validation():
        headers["X-auth-token"] = resource_handler.api_auth_token
    else:
        token = resource_handler._generate_token()
        headers["X-auth-token"] = token
    response = requests.get(url, headers=headers,
                            verify=resource_handler.enable_ssl_verification)
    if response.status_code == 200:
        response = response.json()
        snapshot_list = []
        for record in response['snapshots']:
            snapshot_dict = {}
            snapshot_dict["name"] = record['name'].replace("snapshot for ", "")
            snapshot_dict["snapshot_size"] = record['size']
            snapshot_dict["snapshot_age"] = calculate_snapshot_age(record['created_at']) if record['created_at'] else 0
            snapshot_dict["parent_project"] = record['os-extended-snapshot-attributes:project_id']
            snapshot_dict["status"] = record['status']
            snapshot_list.append(snapshot_dict)
        return snapshot_list
    else:
        raise Exception(f"{response.status_code} Something went wrong")


def calculate_snapshot_age(created_at):
    created_at = datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%S.%f")
    datetime_now = datetime.now()
    diff = datetime_now - created_at
    return diff.days


