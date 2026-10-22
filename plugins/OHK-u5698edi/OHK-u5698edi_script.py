"""
Action creates a new RDS instance and stores its data as an attribute on the
new deployed service.
"""
import re
import time

from infrastructure.models import CustomField, Environment
from resourcehandlers.aws.models import AWSHandler
from common.methods import set_progress
from utilities.logger import ThreadLogger
from accounts.models import Group

logger = ThreadLogger(__name__)


def get_or_create_custom_fields_as_needed():
    CustomField.objects.get_or_create(
        name='aws_rh_id',
        defaults={
            "label": 'AWS RH ID',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint'
        }
    )
    CustomField.objects.get_or_create(
        name='db_identifier',
        defaults={
            "label": 'AWS database identifier',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint'
        }
    )

    CustomField.objects.get_or_create(
        name='db_endpoint_address',
        defaults={
            "label": 'Endpoint Address',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            "show_on_servers": True
        }
    )
    CustomField.objects.get_or_create(
        name='db_endpoint_port',
        defaults={
            "label": 'Endpoint Port',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            "show_on_servers": True
        }
    )
    CustomField.objects.get_or_create(
        name='db_availability_zone',
        defaults={
            "label": 'Availability Zone',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint'
        }
    )
    CustomField.objects.get_or_create(
        name='db_subnet_group',
        defaults={
            "label": 'Subnet group',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint'
        }
    )
    CustomField.objects.get_or_create(
        name='db_subnets',
        defaults={
            "label": 'Subnets',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint'
        }
    )
    CustomField.objects.get_or_create(
        name='db_publicly_accessible',
        defaults={
            "label": 'Publicly Accessible',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint'
        }
    )

    CustomField.objects.get_or_create(
        name='db_engine',
        defaults={
            "label": 'Engine',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint'
        }
    )

    CustomField.objects.get_or_create(
        name='db_status',
        defaults={
            "label": 'Status',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            "show_on_servers": True
        }
    )

    CustomField.objects.get_or_create(
        name='db_username',
        defaults={
            "label": 'Username',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            "show_on_servers": True
        }
    )

    CustomField.objects.get_or_create(
        name='db_cluster_identifier',
        defaults={
            "label": 'DBClusterIdentifier',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint'
        }
    )

    CustomField.objects.get_or_create(
        name='aws_region',
        defaults={
            "label": 'Region',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint'
        }
    )


def get_boto3_service_client(env, service_name="rds"):
    """
    Return boto connection to the RDS in the specified environment's region.
    """
    # get aws resource handler object
    rh: AWSHandler = env.resource_handler.cast()
    # get aws client object
    client = rh.get_boto3_client(env.aws_region, service_name)

    return client


def boto_instance_to_dict(boto_instance, env, rds_client):
    """
    Create a pared-down representation of an RDS instance from the full boto dictionary.
    """
    instance = {
        'name': boto_instance['DBInstanceIdentifier'],
        'aws_region': env.aws_region,
        'aws_rh_id': env.resource_handler.cast().id,
        'db_identifier': boto_instance['DBInstanceIdentifier'],
        'db_engine': boto_instance['Engine'],
        'db_status': boto_instance['DBInstanceStatus'],
        'db_username': boto_instance['MasterUsername'],
        'db_publicly_accessible': boto_instance['PubliclyAccessible'],
        'db_availability_zone': boto_instance.get("AvailabilityZone", ""),
        'db_cluster_identifier': boto_instance.get("DBClusterIdentifier", "")
    }

    # get subnet object
    subnet_group = boto_instance.get("DBSubnetGroup", {})
    # Endpoint may not be returned if networking is not set up yet
    endpoint = boto_instance.get('Endpoint', {})

    if not endpoint:
        time.sleep(10)

        # fetch RDS DB instance
        rds_rsp = rds_client.describe_db_instances(DBInstanceIdentifier=boto_instance['DBInstanceIdentifier'],
                                    Filters=[{'Name':'engine','Values':[boto_instance['Engine']]}])['DBInstances']
        if rds_rsp:
            endpoint = rds_rsp[0].get('Endpoint', {})
    instance.update({'db_endpoint_address': endpoint.get('Address'),
        'db_endpoint_port': endpoint.get('Port'),
        'db_subnet_group': subnet_group.get("DBSubnetGroupName"),
        'db_subnets': [xx['SubnetIdentifier'] for xx in subnet_group.get("Subnets", [])]})

    logger.info(f'RDS instance {instance} created successfully.')
    return instance


def sort_dropdown_options(data, placeholder=None, is_reverse=False):
    """
    Sort dropdown options
    """
    # remove duplicate option from list
    data = list(set(data))
    # sort options
    sorted_options = sorted(data, key=lambda tup: tup[1].lower(), reverse=is_reverse)

    if placeholder is not None:
        sorted_options.insert(0, placeholder)

    return {'options': sorted_options, 'override': True}


def generate_options_for_aws_region(**kwargs):
    """
    Generate AWS region options
    """
    group_name = kwargs["group"]
    try:
        group = Group.objects.get(name=group_name)
    except Exception as err:
        return [("", "-----No Group Found-----")]

    # fetch all group environment
    envs = group.get_available_environments()

    aws_envs = [env for env in envs if env.resource_handler is not None and env.resource_handler.resource_technology.slug.startswith('aws')]

    if not aws_envs:
        return [("", "-----Select Environment-----")]

    client = get_boto3_service_client(aws_envs[0])

    # fetch all rds supported regions
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/rds.html#RDS.Client.describe_source_regions
    rds_support_regions = [region['RegionName'] for region in client.describe_source_regions()['SourceRegions']]
    options = []

    for env in aws_envs:
        if env.aws_region not in rds_support_regions:
            continue

        # change int to str because aws_region field type is STR
        options.append((str(env.id), env.name))

    # boto3 describe_source_regions api response does not return region which is used to create the boto3 client.
    if aws_envs[0].aws_region not in rds_support_regions:
        # change int to str because aws_region field type is STR
        options.append((str(aws_envs[0].id), aws_envs[0].name))

    if not options:
        return [("", "-----Select Environment-----")]

    return sort_dropdown_options(options)


def generate_options_for_db_engine(control_value=None, **kwargs):
    """
    Generate RDS Database Engine options
    Dependency: RDS Region
    """
    if control_value is None or control_value == "":
        return [("", "-----First, Select AWS Region-----")]
    env = Environment.objects.get(id=control_value)
    client = get_boto3_service_client(env)
    paginator = client.get_paginator("describe_db_engine_versions")
    engines = set()
    for page in paginator.paginate():
        for item in page["DBEngineVersions"]:
            engines.add(item["Engine"])
    options = [
        (f"{engine}/{env.id}", engine.replace("-", " ").title())
        for engine in sorted(engines)
    ]
    if not options:
        return [("", "-----No Database Engines Found-----")]
    return sort_dropdown_options(options)


def generate_options_for_db_engine_version(control_value=None, **kwargs):
    """
    Generate RDS Database Engine version options
    Dependency: RDS Database Engine
    """
    if control_value is None or control_value == "":
        return [("", "-----First, Select Database Engine-----")]
    engine, env_id = control_value.split("/")
    env = Environment.objects.get(id=env_id)
    client = get_boto3_service_client(env)
    paginator = client.get_paginator("describe_db_engine_versions")
    filters = [
        {"Name": "status", "Values": ["available"]},
        {"Name": "engine-mode", "Values": ["provisioned"]},
    ]
    version_rgx = r'^\d+(\.\d+)*$'
    seen = set()
    options = []
    for page in paginator.paginate(
        Engine=engine,
        IncludeAll=False,
        Filters=filters,
    ):
        for version in page["DBEngineVersions"]:
            version_no = version["EngineVersion"]
            if version_no in seen:
                continue
            seen.add(version_no)
            label = version["DBEngineVersionDescription"]
            if "Limitless" in label:
                continue
            if (
                re.match(version_rgx, version_no)
                and version_no not in label
            ):
                label = f"{label} : {version_no}"
            options.append(
                (
                    f"{version_no}/{env.id}/{engine}",
                    label,
                )
            )
    if not options:
        return [("", "-----No Engine Versions Found-----")]
    return sort_dropdown_options(options, None, True)


def generate_options_for_instance_class(control_value=None, **kwargs):
    """
    Generate RDS Database Engine Version instance class options
    Dependency: RDS Database Engine Version
    """
    if control_value is None or control_value == "":
        return [("", "-----First, Select Database Engine Version-----")]
    engine_version, env_id, engine = control_value.split("/")
    env = Environment.objects.get(id=env_id)
    client = get_boto3_service_client(env)
    paginator = client.get_paginator("describe_orderable_db_instance_options")
    options = []
    seen = set()
    for page in paginator.paginate(
        Engine=engine,
        EngineVersion=engine_version,
        Vpc=True,
    ):
        for option in page["OrderableDBInstanceOptions"]:
            instance_class = option["DBInstanceClass"]
            storage_type = option.get("StorageType", "")
            license_model = option.get("LicenseModel", "")
            # Avoid duplicate entries
            unique_key = (
                instance_class,
                storage_type,
                license_model,
            )

            if unique_key in seen:
                continue

            seen.add(unique_key)
            min_storage = option.get("MinStorageSize", 20)
            key = "$?".join([
                instance_class,
                str(min_storage),
                license_model,
                storage_type,
            ])
            label = instance_class
            if storage_type:
                label += f" ({storage_type})"
            options.append((key, label))
    if not options:
        return [("", "-----No Instance Classes Found-----")]
    return sort_dropdown_options(options)


def find_or_create_rds_subnet_group(rds_client, env):
    """
    Find or create rds subnet group
    """
    subnet_group = None

    for sb_gp in rds_client.describe_db_subnet_groups()['DBSubnetGroups']:
        subnet_group = sb_gp['DBSubnetGroupName']
        break

    if subnet_group is None:
        # get ec2 boto3 client object
        ec2_client = get_boto3_service_client(env, 'ec2')
        # fetch all ec2 region subnets
        subnets = ec2_client.describe_subnets()['Subnets']
        if not subnets:
            raise RuntimeError(f"Subnet does not exists for EC2 region({env.aws_region})")
        vpc_id = subnets[0]['VpcId']
        try:
            # create subnet group
            sub_resp = rds_client.create_db_subnet_group(
                DBSubnetGroupName=f'default-{vpc_id}',
                DBSubnetGroupDescription='Created subnet group for RDS DB instance',
                SubnetIds= [xx['SubnetId'] for xx in subnets if xx['VpcId'] == vpc_id]
            )
        except Exception as err:
            raise RuntimeError(err)
        else:
            subnet_group = sub_resp['DBSubnetGroup']['DBSubnetGroupName']
            time.sleep(10)
    return subnet_group


def generate_options_for_security_group(control_value=None, **kwargs):
    """
    Generate Security Group options for the VPC used by the RDS subnet group.
    Dependency: AWS Region
    """
    if control_value is None or control_value == "":
        return [("", "-----First, Select AWS Region-----")]
    env = Environment.objects.get(id=control_value)
    rds_client = get_boto3_service_client(env)
    ec2_client = get_boto3_service_client(env, "ec2")
    # Reuse the existing subnet group logic
    subnet_group = find_or_create_rds_subnet_group(rds_client, env)
    # Get subnet group details
    subnet_group_rsp = rds_client.describe_db_subnet_groups(
        DBSubnetGroupName=subnet_group
    )["DBSubnetGroups"][0]
    # Use the first subnet to determine the VPC
    subnet_id = subnet_group_rsp["Subnets"][0]["SubnetIdentifier"]
    subnet_rsp = ec2_client.describe_subnets(
        SubnetIds=[subnet_id]
    )["Subnets"][0]
    vpc_id = subnet_rsp["VpcId"]
    options = []
    paginator = ec2_client.get_paginator("describe_security_groups")
    for page in paginator.paginate(
        Filters=[
            {
                "Name": "vpc-id",
                "Values": [vpc_id],
            }
        ]
    ):
        for sg in page["SecurityGroups"]:
            options.append(
                (
                    sg["GroupId"],
                    f"{sg['GroupName']} ({sg['GroupId']})",
                )
            )
    if not options:
        return [("", "-----No Security Groups Found-----")]
    return sort_dropdown_options(options)


def create_rds_db_cluster(client, cluster_identifier, **cluster_kwargs):
    """
    Create RDS DB instance cluster
    """
    cluster_kwargs['DBClusterIdentifier'] = cluster_identifier

    set_progress(f'Started provision of rds cluster: {cluster_identifier}')
    logger.info('Started provision of rds cluster'.format(cluster_kwargs))

    try:
        # create database cluster
        cluster_rsp = client.create_db_cluster(**cluster_kwargs)['DBCluster']
    except Exception as err:
        if 'DBClusterAlreadyExistsFault' not in str(err):
            raise RuntimeError(err)

    while cluster_rsp['Status'] != "available":
        time.sleep(20)

        # fetch rds db cluster
        cluster_rsp = client.describe_db_clusters(DBClusterIdentifier=cluster_identifier,
                                        Filters=[{'Name':'engine','Values':[cluster_kwargs['Engine']]}])['DBClusters'][0]
    return cluster_identifier


def run(resource, logger=None, **kwargs):
    set_progress('Creating AWS RDS instance...')
    logger.info('Creating AWS RDS instance...')

    # get or create custom fields
    get_or_create_custom_fields_as_needed()

    # AWS requires DB Name to have a certain format (only alphanumeric). To
    # have CB properly validate user input on this parameter, an admin should go
    # to the action's detail page, edit the 'DB Name' Action Input and set a
    # "Regex constraint" value of "^[a-zA-Z]\w+$".
    db_name = '{{ db_name }}'
    db_username = '{{ db_username }}'
    db_password = '{{ db_password }}'
    security_group_id = '{{ security_group }}'
    db_identifier = '{{ db_identifier }}'
    instance_class_obj = '{{ instance_class }}'.split("$?")
    engine = '{{ db_engine }}'.split("/")[0]
    db_engine_version = '{{ db_engine_version }}'.split("/")[0]
    license_model = instance_class_obj[2]
    instance_class = instance_class_obj[0]
    allocated_storage = int(instance_class_obj[1])
    env = Environment.objects.get(id='{{ aws_region }}')

    set_progress('Connecting to AWS RDS in region {0}.'.format(env.aws_region))
    logger.info('Connecting to AWS RDS in region {0}.'.format(env.aws_region))

    # get boto client object
    client = get_boto3_service_client(env)

    rds_payload = {
        "DBInstanceIdentifier": db_identifier,
        "DBInstanceClass": instance_class,
        "AutoMinorVersionUpgrade": False,
        "CopyTagsToSnapshot": True,
    }

    if license_model:
        rds_payload["LicenseModel"] = license_model

    # get or create subnet group
    subnet_group = find_or_create_rds_subnet_group(client, env)
    common_kwargs = dict(
        Engine=engine,
        EngineVersion=db_engine_version,
        MasterUserPassword=db_password,
        BackupRetentionPeriod=7,
        StorageEncrypted=True,
        MasterUsername=db_username,
        DeletionProtection=False,
        DBSubnetGroupName=subnet_group,
        VpcSecurityGroupIds=[security_group_id],
    )
    if engine.startswith("aurora"):
        cluster_id = create_rds_db_cluster(
            client,
            f"{db_identifier}-c",
            **common_kwargs
        )

        rds_payload.update({
            "Engine": engine,
            "EngineVersion": db_engine_version,
            "DBClusterIdentifier": cluster_id,
        })

    else:
        storage_type = instance_class_obj[3]

        rds_payload["AllocatedStorage"] = allocated_storage
        rds_payload["StorageType"] = storage_type

        if not engine.startswith("sqlserver"):
            rds_payload["DBName"] = db_name

        if storage_type == "io1":
            rds_payload["Iops"] = 1000

        if engine == "sqlserver-ex":
            common_kwargs.pop("StorageEncrypted", None)

        rds_payload.update(common_kwargs)

    set_progress(f'Started provision of rds instance: {db_identifier}')
    logger.info('Started provision of rds instance:\n{0}'.format(rds_payload))

    supported = client.describe_orderable_db_instance_options(
        Engine=engine,
        EngineVersion=db_engine_version,
        DBInstanceClass=instance_class,
        Vpc=True,
    )["OrderableDBInstanceOptions"]

    if not supported:
        raise RuntimeError(
            f"{instance_class} is not supported for "
            f"{engine} {db_engine_version}"
        )
    try:
        # create rds db instance
        rds_response = client.create_db_instance(**rds_payload)
    except Exception as err:
        if 'DBInstanceAlreadyExists' in str(err):
            return "FAILURE", "Database already exists", "DB instance {} exists already".format(db_identifier)
        raise

    # It takes awhile for the DB to be created and backed up.
    waiter = client.get_waiter('db_instance_available')
    waiter.config.max_attempts = 100  # default is 40 but oracle takes more time.
    waiter.wait(DBInstanceIdentifier=db_identifier)

    logger.info(f"RDS instance response {rds_response}")

    # convert boto model into cb rds dict
    rds_instance = boto_instance_to_dict(rds_response['DBInstance'], env, client)
    for key, value in rds_instance.items():
        setattr(resource, key, value)  # set custom field value
    resource.name = db_identifier
    resource.save()
    set_progress(f'RDS instance {db_identifier} created successfully.')

    return 'SUCCESS', f'RDS instance {db_identifier} created successfully.', ''