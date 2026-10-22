from common.methods import set_progress
from infrastructure.models import CustomField
from infrastructure.models import Environment
from resourcehandlers.aws.models import AWSHandler
from accounts.models import Group
import time

def get_boto3_service_client(rh: AWSHandler, aws_region, service_name="fsx"):
    """
    Return boto connection to the FSX in the specified environment's region.
    """
    client = rh.get_boto3_client(aws_region, service_name)
    return client


def create_custom_fields_as_needed():
    CustomField.objects.get_or_create(
        name='aws_rh_id', defaults={
            'label': 'AWS RH ID', 'type': 'STR',
            'description': 'Used by the AWS blueprints'
        }
    )
    CustomField.objects.get_or_create(
        name='aws_region', defaults={
            'label': 'AWS Region', 'type': 'STR',
            'description': 'Used by the AWS blueprints'
        }
    )
    CustomField.objects.get_or_create(
        name='file_system_type', defaults={
            'label': 'FileSystemType', 'type': 'STR',
            'description': 'The type of file system (WINDOWS, LUSTRE, ONTAP, OPENZFS).'
        }
    )
    CustomField.objects.get_or_create(
        name='file_system_id', defaults={
            'label': 'FileSystemId', 'type': 'STR',
            'description': 'The ID of the file system created.'
        }
    )
    CustomField.objects.get_or_create(
        name='storage_capacity', defaults={
            'label': 'StorageCapacity', 'type': 'INT',
            'description': " The storage capacity of the file system."
                           "For Windows file systems, the storage capacity has a minimum of 300 GiB,"
                           "and a maximum of 65,536 GiB. For Lustre file systems, the storage capacity has a minimum "
                           "of 3,600 GiB. Storage capacity is provisioned in increments of 3,600 GiB. "
                           "For ONTAP, minimum is 1,024 GiB and maximum is 196,608 GiB. "
                           "For OpenZFS, minimum is 64 GiB and maximum is 524,288 GiB."
        }
    )
    CustomField.objects.get_or_create(
        name='subnet_ids', defaults={
            'label': 'SubnetIds', 'type': 'STR',
            'description': "A list of IDs for the subnets that the file system will be accessible from. File systems "
                           "support only one subnet. The file server is also launched in that subnet's Availability "
                           "Zone. "
        }
    )
    CustomField.objects.get_or_create(
        name='security_group_ids', defaults={
            'label': 'SecurityGroupIds', 'type': 'STR',
            'description': 'The ID of the security group.'
        }
    )
    CustomField.objects.get_or_create(
        name='deployment_type', defaults={
            'label': 'DeploymentType', 'type': 'STR',
            'description': 'Deployment type for the file system. Required for ONTAP and OPENZFS '
                           '(e.g. MULTI_AZ_1, MULTI_AZ_2, SINGLE_AZ_1, SINGLE_AZ_2).'
        }
    )
    CustomField.objects.get_or_create(
        name='route_table_ids', defaults={
            'label': 'RouteTableIds', 'type': 'STR',
            'description': 'Multi-AZ only. VPC route table IDs FSx should update to route traffic to the '
                           'file system. If left blank, AWS uses the VPC default route table.'
        }
    )
    CustomField.objects.get_or_create(
        name='endpoint_ip_address_range', defaults={
            'label': 'EndpointIpAddressRange', 'type': 'STR',
            'description': 'Multi-AZ only. IPv4 range for the file system endpoints (e.g. 192.168.0.0/24). '
                           'If left blank, AWS auto-selects a range.'
        }
    )


def generate_options_for_env_id(server=None, **kwargs):
    group_name = kwargs["group"]

    try:
        group = Group.objects.get(name=group_name)
    except Exception:
        return []

    # fetch all group environment
    envs = group.get_available_environments()
    aws_envs = [(str(env.id), env.name) for env in envs if env.resource_handler is not None and env.resource_handler.resource_technology.slug.startswith('aws')]
    return aws_envs


def generate_options_for_file_system_type(control_value=None, **kwargs):
    if not control_value:
        return []

    try:
        env = Environment.objects.get(id=control_value)
    except Environment.DoesNotExist:
        return []

    rh = env.resource_handler.cast()
    fsx = get_boto3_service_client(rh, env.aws_region)

    blank_option = [("", "-- Select a file system type --")]

    try:
        enum_values = fsx.meta.service_model.shape_for("FileSystemType").enum
        return blank_option + [(v, v) for v in enum_values]
    except Exception:
        return blank_option + [(v, v) for v in ("WINDOWS", "LUSTRE", "ONTAP", "OPENZFS")]


def _fallback_deployment_types(file_system_type):
    """
    Static safety net used only if we can't reach the FSx client (e.g. no
    env selected yet, or AWS shape lookup fails). Mirrors the same fallback
    pattern used in generate_options_for_file_system_type.
    """
    fallback = {
        "ONTAP": ["MULTI_AZ_1", "MULTI_AZ_2", "SINGLE_AZ_1", "SINGLE_AZ_2"],
        "OPENZFS": ["SINGLE_AZ_1", "SINGLE_AZ_2", "MULTI_AZ_1"],
    }

    options = [("", "-- Please Select a Deployment Type --")]

    options.extend(
        (v, v.replace("_", " ").title())
        for v in fallback.get(file_system_type, [])
    )

    return options


def generate_options_for_deployment_type(control_value=None, **kwargs):
    """
    This field depends on TWO other fields: file_system_type and env_id.
    CloudBolt calls this generator whenever EITHER dependency changes, and
    `control_value` is the value of whichever field triggered the call -
    it could be file_system_type OR env_id depending on what the user just
    touched. So `control_value` itself is unreliable here; always read both
    dependent values out of `control_value_dict` instead.
    """
    control_value_dict = kwargs.get("control_value_dict", {}) or {}

    file_system_type = control_value_dict.get("file_system_type", "")
    env_id = control_value_dict.get("env_id", "")

    if file_system_type not in ("ONTAP", "OPENZFS"):
        return []

    if not env_id:
        return _fallback_deployment_types(file_system_type)

    try:
        env = Environment.objects.get(id=env_id)
    except Environment.DoesNotExist:
        return _fallback_deployment_types(file_system_type)

    try:
        rh = env.resource_handler.cast()
        fsx = get_boto3_service_client(rh, env.aws_region)

        shape_name = (
            "OntapDeploymentType"
            if file_system_type == "ONTAP"
            else "OpenZFSDeploymentType"
        )

        enum_values = fsx.meta.service_model.shape_for(shape_name).enum

        options = [("", "-- Please Select a Deployment Type --")]

        options.extend(
            (v, v.replace("_", " ").title())
            for v in enum_values
        )

        return options

    except Exception:
        return _fallback_deployment_types(file_system_type)

        
def generate_options_for_subnet_ids(control_value=None, **kwargs):
    if not control_value:
        return []

    try:
        env = Environment.objects.get(id=control_value)
    except Environment.DoesNotExist:
        return []

    rh = env.resource_handler.cast()
    ec2 = get_boto3_service_client(rh, env.aws_region, "ec2")

    result = []

    try:
        paginator = ec2.get_paginator("describe_subnets")

        for page in paginator.paginate():
            for subnet in page.get("Subnets", []):
                subnet_id = subnet["SubnetId"]
                az = subnet.get("AvailabilityZone", "Unknown")

                result.append(
                    (
                        f"{subnet_id},{control_value}",
                        f"{subnet_id} ({az})",
                    )
                )

    except Exception:
        return []

    return sorted(result, key=lambda x: x[1])


def generate_options_for_preferred_subnet_id(control_value=None, **kwargs):
    """
    control_value is the value from the subnet_ids field, encoded as
    "subnet_id,env_id". Only used for Multi-AZ ONTAP/OpenZFS deployments,
    which need a second subnet (ideally in a different AZ) as standby.
    """
    if not control_value:
        return []

    try:
        env = Environment.objects.get(id=control_value)
    except Environment.DoesNotExist:
        return []

    rh = env.resource_handler.cast()
    ec2 = get_boto3_service_client(rh, env.aws_region, "ec2")

    result = []

    try:
        paginator = ec2.get_paginator("describe_subnets")

        for page in paginator.paginate():
            for subnet in page.get("Subnets", []):
                subnet_id = subnet["SubnetId"]
                az = subnet.get("AvailabilityZone", "Unknown")

                result.append(
                    (
                        subnet_id,
                        f"{subnet_id} ({az})",
                    )
                )

    except Exception:
        return []

    return sorted(result, key=lambda x: x[1])


def generate_options_for_active_directory_id(control_value=None, **kwargs):
    if not control_value:
        return []
    
    control_value_dict = kwargs.get("control_value_dict", {}) or {}

    file_system_type = control_value_dict.get("file_system_type", "")

    if file_system_type not in "WINDOWS":
        return []

    try:
        subnet_id, env_id = control_value.split(",", 1)
    except ValueError:
        return []

    try:
        env = Environment.objects.get(id=env_id)
    except Environment.DoesNotExist:
        return []

    rh = env.resource_handler.cast()
    client = get_boto3_service_client(rh, env.aws_region, "ds")

    result = []

    try:
        paginator = client.get_paginator("describe_directories")

        for page in paginator.paginate():
            for directory in page.get("DirectoryDescriptions", []):

                # FSx Windows supports only AWS Managed Microsoft AD
                if directory.get("Type") not in ("MicrosoftAD","SharedMicrosoftAD",):
                    continue

                # Only Active directories
                if directory.get("Stage") != "Active":
                    continue

                vpc_settings = directory.get("VpcSettings", {})
                subnet_ids = vpc_settings.get("SubnetIds", [])

                if subnet_id not in subnet_ids:
                    continue

                directory_id = directory["DirectoryId"]
                directory_name = directory.get("Name", "Unknown")

                result.append(
                    (
                        directory_id,
                        f"{directory_name} ({directory_id})",
                    )
                )

    except Exception:
        return []

    return sorted(result, key=lambda x: x[1])


def generate_options_for_security_group_ids(control_value=None, **kwargs):
    if not control_value:
        return []

    try:
        subnet_id, env_id = control_value.split(",", 1)
    except ValueError:
        return []

    try:
        env = Environment.objects.get(id=env_id)
    except Environment.DoesNotExist:
        return []

    rh = env.resource_handler.cast()
    ec2 = get_boto3_service_client(rh, env.aws_region, "ec2")

    try:
        response = ec2.describe_subnets(SubnetIds=[subnet_id])
        subnets = response.get("Subnets", [])

        if not subnets:
            return []

        vpc_id = subnets[0]["VpcId"]

        result = []

        paginator = ec2.get_paginator("describe_security_groups")

        for page in paginator.paginate(
            Filters=[
                {
                    "Name": "vpc-id",
                    "Values": [vpc_id],
                }
            ]
        ):
            for sg in page.get("SecurityGroups", []):
                result.append(
                    (
                        sg["GroupId"],
                        f"{sg['GroupName']} ({sg['GroupId']})",
                    )
                )

        return sorted(result, key=lambda x: x[1])

    except Exception:
        return []


# Validation + per-type configuration builders

def validate_storage_capacity(file_system_type, storage_capacity):
    if file_system_type == "LUSTRE":
        if storage_capacity % 3600 != 0:
            return "Lustre storage must be a multiple of 3600 GiB."

    elif file_system_type == "WINDOWS":
        if storage_capacity < 300:
            return "Windows requires at least 300 GiB."

    elif file_system_type == "ONTAP":
        if storage_capacity < 1024 or storage_capacity > 196608:
            return "ONTAP storage capacity must be between 1,024 and 196,608 GiB."

    elif file_system_type == "OPENZFS":
        if storage_capacity < 64 or storage_capacity > 524288:
            return "OpenZFS storage capacity must be between 64 and 524,288 GiB."

    return None


def validate_throughput_capacity(file_system_type, throughput_capacity):
    """
    AWS requires ThroughputCapacity for ONTAP and OPENZFS file systems.
    It's optional for WINDOWS (AWS can derive a default) and not applicable
    to LUSTRE (Lustre uses PerUnitStorageThroughput instead, not implemented
    in this plugin).
    """
    if file_system_type in ("ONTAP", "OPENZFS") and not throughput_capacity:
        return f"ThroughputCapacity is required for {file_system_type} file systems."

    return None


def build_windows_configuration(active_directory_id, throughput_capacity,
                                 daily_backup_start_time, backup_retention_days):
    configuration = {}

    if active_directory_id:
        configuration["ActiveDirectoryId"] = active_directory_id
    if throughput_capacity:
        configuration["ThroughputCapacity"] = int(throughput_capacity)
    if daily_backup_start_time:
        configuration["DailyAutomaticBackupStartTime"] = daily_backup_start_time
    if backup_retention_days:
        configuration["AutomaticBackupRetentionDays"] = int(backup_retention_days)

    return configuration


def build_ontap_configuration(deployment_type, throughput_capacity, fsx_admin_password,
                               preferred_subnet_id, route_table_ids, endpoint_ip_address_range,
                               daily_backup_start_time, backup_retention_days):
    configuration = {
        "DeploymentType": deployment_type,
    }

    if throughput_capacity:
        configuration["ThroughputCapacity"] = int(throughput_capacity)
    if fsx_admin_password:
        configuration["FsxAdminPassword"] = fsx_admin_password
    if daily_backup_start_time:
        configuration["DailyAutomaticBackupStartTime"] = daily_backup_start_time
    if backup_retention_days:
        configuration["AutomaticBackupRetentionDays"] = int(backup_retention_days)

    # Multi-AZ-only settings
    is_multi_az = deployment_type and deployment_type.startswith("MULTI_AZ")

    if is_multi_az and preferred_subnet_id:
        configuration["PreferredSubnetId"] = preferred_subnet_id

    if is_multi_az and route_table_ids:
        configuration["RouteTableIds"] = [
            rt.strip() for rt in route_table_ids.split(",") if rt.strip()
        ]

    if is_multi_az and endpoint_ip_address_range:
        configuration["EndpointIpAddressRange"] = endpoint_ip_address_range

    return configuration


def build_openzfs_configuration(deployment_type, throughput_capacity, preferred_subnet_id,
                                 route_table_ids, endpoint_ip_address_range,
                                 daily_backup_start_time, backup_retention_days):
    configuration = {
        "DeploymentType": deployment_type,
    }

    if throughput_capacity:
        configuration["ThroughputCapacity"] = int(throughput_capacity)
    if daily_backup_start_time:
        configuration["DailyAutomaticBackupStartTime"] = daily_backup_start_time
    if backup_retention_days:
        configuration["AutomaticBackupRetentionDays"] = int(backup_retention_days)

    # Multi-AZ-only settings (OpenZFS Multi-AZ needs the same fields as ONTAP Multi-AZ)
    is_multi_az = deployment_type and deployment_type.startswith("MULTI_AZ")

    if is_multi_az and preferred_subnet_id:
        configuration["PreferredSubnetId"] = preferred_subnet_id

    if is_multi_az and route_table_ids:
        configuration["RouteTableIds"] = [
            rt.strip() for rt in route_table_ids.split(",") if rt.strip()
        ]

    if is_multi_az and endpoint_ip_address_range:
        configuration["EndpointIpAddressRange"] = endpoint_ip_address_range

    return configuration


# Main entry point

def run(resource, logger=None, **kwargs):
    env_id = '{{ env_id }}'
    env = Environment.objects.get(id=env_id)
    rh = env.resource_handler.cast()

    fsx_file_name = "{{ fsx_file_name }}"
    file_system_type = "{{ file_system_type }}"
    storage_capacity = "{{ storage_capacity }}"
    subnet_ids = "{{ subnet_ids }}"
    security_group_ids = "{{ security_group_ids }}"

    subnet_ids = subnet_ids.split(',')
    if not subnet_ids or not subnet_ids[0]:
        return "FAILURE", "", "No subnet selected."

    try:
        storage_capacity_int = int(storage_capacity)
    except (TypeError, ValueError):
        return "FAILURE", "", "Storage capacity must be a whole number."

    error = validate_storage_capacity(file_system_type, storage_capacity_int)
    if error:
        return "FAILURE", "", error

    # Configuration for Microsoft Windows file system.
    ActiveDirectoryId = "{{ active_directory_id }}"  # Optional
    ThroughputCapacity = "{{ ThroughputCapacity }}"
    DailyAutomaticBackupStartTime = "{{ DailyAutomaticBackupStartTime }}"  # Optional
    AutomaticBackupRetentionDays = "{{ AutomaticBackupRetentionDays }}"  # Optional

    # Configuration for ONTAP / OpenZFS file systems.
    deployment_type = "{{ deployment_type }}"  # Required for ONTAP/OPENZFS
    fsx_admin_password = "{{ fsx_admin_password }}"  # Required for ONTAP
    preferred_subnet_id = "{{ preferred_subnet_id }}"  # Required for Multi-AZ ONTAP/OPENZFS
    route_table_ids = "{{ route_table_ids }}"  # Optional, Multi-AZ only
    endpoint_ip_address_range = "{{ endpoint_ip_address_range }}"  # Optional, Multi-AZ only
        
    throughput_error = validate_throughput_capacity(file_system_type, ThroughputCapacity)
    if throughput_error:
        return "FAILURE", "", throughput_error

    if file_system_type in ("ONTAP", "OPENZFS") and not deployment_type:
        return "FAILURE", "", f"A deployment type is required for {file_system_type} file systems."

    if file_system_type == "ONTAP" and not fsx_admin_password:
        return "FAILURE", "", "An FSx admin password is required for ONTAP file systems."

    if deployment_type and deployment_type.startswith("MULTI_AZ") and not preferred_subnet_id:
        return "FAILURE", "", "A preferred subnet is required for Multi-AZ deployments."

    # Convert the selected security groups into a Python list
    security_groups = []

    if security_group_ids:
        security_groups = [sg.strip() for sg in security_group_ids.split(",") if sg.strip()]

    set_progress(f"Types AD: {ActiveDirectoryId}, ThroughputCapacity {ThroughputCapacity},"
                 f" DailyAutomaticBackupStartTime {DailyAutomaticBackupStartTime}, AutomaticBackupRetentionDays"
                 f" {AutomaticBackupRetentionDays}")

    set_progress(f"Region is {env.aws_region}")

    fsx = get_boto3_service_client(rh, env.aws_region)

    set_progress(f"Creating file system...")
    set_progress(f"Selected subnet: {subnet_ids[0]}")
    set_progress(f"Selected security groups: {security_groups}")
    # Primary subnet
    selected_subnets = [subnet_ids[0]]
    
    # Multi-AZ requires two subnet IDs
    if (
        file_system_type in ("ONTAP", "OPENZFS")
        and deployment_type.startswith("MULTI_AZ")
    ):
        selected_subnets.append(preferred_subnet_id)

    try:
        # Common parameters for all FSx file systems
        params = {
            "FileSystemType": file_system_type,
            "StorageCapacity": storage_capacity_int,
            "SubnetIds": selected_subnets,
            "SecurityGroupIds": security_groups,
            "Tags": [
                {
                    "Key": "Name",
                    "Value": fsx_file_name,
                }
            ],
        }

        if file_system_type == "WINDOWS":
            set_progress(f"File system type is {file_system_type}")
            params["WindowsConfiguration"] = build_windows_configuration(
                ActiveDirectoryId, ThroughputCapacity,
                DailyAutomaticBackupStartTime, AutomaticBackupRetentionDays
            )

        elif file_system_type == "ONTAP":
            set_progress(f"File system type is {file_system_type}, DeploymentType {deployment_type}")
            params["OntapConfiguration"] = build_ontap_configuration(
                deployment_type, ThroughputCapacity, fsx_admin_password,
                preferred_subnet_id, route_table_ids, endpoint_ip_address_range,
                DailyAutomaticBackupStartTime, AutomaticBackupRetentionDays
            )

        elif file_system_type == "OPENZFS":
            set_progress(f"File system type is {file_system_type}, DeploymentType {deployment_type}")
            params["OpenZFSConfiguration"] = build_openzfs_configuration(
                deployment_type, ThroughputCapacity, preferred_subnet_id,
                route_table_ids, endpoint_ip_address_range,
                DailyAutomaticBackupStartTime, AutomaticBackupRetentionDays
            )

        set_progress(f"Creating {file_system_type} file system...")

        res = fsx.create_file_system(**params)

    except Exception as error:
        if logger:
            logger.exception(error)

        return "FAILURE", "", str(error)

    file_system_id = res.get('FileSystem', {}).get('FileSystemId')
    if not file_system_id:
        return "FAILURE", "", "AWS did not return a FileSystemId."

    # Wait for the file system to be created
    def get_lifecycle():
        _res = fsx.describe_file_systems(FileSystemIds=[file_system_id])
        filesystems = _res.get("FileSystems", [])
        if not filesystems:
            raise Exception("No filesystem returned by AWS.")

        return filesystems[0]["Lifecycle"]

    timeout = 3600
    elapsed = 0

    lifecycle = get_lifecycle()

    while lifecycle == "CREATING":
        set_progress(f"File System Status: {lifecycle}")

        if elapsed >= timeout:
            return ("FAILURE", "", "Timed out waiting for FSx to become AVAILABLE.")

        time.sleep(60)
        elapsed += 60
        lifecycle = get_lifecycle()

    # At this point, the lifecycle is either AVAILABLE or FAILED
    if lifecycle == "AVAILABLE":
        create_custom_fields_as_needed()
        resource.name = fsx_file_name
        resource.file_system_id = file_system_id
        resource.aws_rh_id = rh.id
        resource.aws_region = env.aws_region
        resource.subnet_ids = selected_subnets
        resource.security_group_ids = security_groups
        resource.storage_capacity = storage_capacity_int
        resource.file_system_type = file_system_type
        resource.deployment_type = deployment_type

        resource.save()

    else:
        return ("FAILURE", "", f"File system entered lifecycle '{lifecycle}'.")

    return "SUCCESS", "", ""