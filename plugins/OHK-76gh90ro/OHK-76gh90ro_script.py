"""
Build service item action for AWS MySQL database blueprint.
"""
import re
import sys
import time
from common.methods import set_progress
from infrastructure.models import CustomField, Environment
from accounts.models import Group
from utilities.logger import ThreadLogger

logger = ThreadLogger(__name__)


def get_or_create_custom_fields_as_needed():
    CustomField.objects.get_or_create(
        name='aws_region',
        defaults={"label": 'Region', "type": 'STR', "description": 'Used by AWS Databases blueprint'}
    )
    CustomField.objects.get_or_create(
        name='db_identifier',
        defaults={"label": 'AWS database identifier', "type": 'STR', "description": 'Used by AWS Databases blueprint'}
    )
    CustomField.objects.get_or_create(
        name='db_engine',
        defaults={"label": 'Engine', "type": 'STR', "description": 'Used by AWS Databases blueprint'}
    )
    CustomField.objects.get_or_create(
        name='db_username',
        defaults={"label": 'Username', "type": 'STR', "description": 'Used by AWS Databases blueprint', "show_on_servers": True}
    )
    CustomField.objects.get_or_create(
        name='subnet_group_option',
        defaults={"label": 'DB Subnet Group Selection', "type": 'STR', "description": 'Choose whether to use an existing subnet group or create a new one'}
    )
    CustomField.objects.get_or_create(
        name='aws_mysql_subnet_group',
        defaults={"label": 'AWS Existing Subnet Group', "type": 'STR', "description": 'Selected existing DB Subnet Group'}
    )
    CustomField.objects.get_or_create(
        name='aws_mysql_subnets',
        defaults={"label": 'AWS Raw Subnets for New Group', "type": 'STR', "description": 'Subnets selected to construct a new DB Subnet Group'}
    )
    CustomField.objects.get_or_create(
        name='aws_mysql_security_group',
        defaults={"label": 'Security Group', "type": 'STR', "description": 'Target Security Group for AWS Databases blueprint'}
    )

    CustomField.objects.get_or_create(
        name='aws_rh_id',
        defaults={"label": 'AWS RH ID', "type": 'STR', "description": 'Used by AWS Databases blueprint'}
    )
    CustomField.objects.get_or_create(
        name='db_endpoint_address',
        defaults={"label": 'Endpoint Address', "type": 'STR', "description": 'Used by AWS Databases blueprint', "show_on_servers": True}
    )
    CustomField.objects.get_or_create(
        name='db_endpoint_port',
        defaults={"label": 'Endpoint Port', "type": 'STR', "description": 'Used by AWS Databases blueprint', "show_on_servers": True}
    )
    CustomField.objects.get_or_create(
        name='db_availability_zone',
        defaults={"label": 'Availability Zone', "type": 'STR', "description": 'Used by AWS Databases blueprint'}
    )
    CustomField.objects.get_or_create(
        name='db_publicly_accessible',
        defaults={"label": 'Publicly Accessible', "type": 'STR', "description": 'Used by AWS Databases blueprint'}
    )
    CustomField.objects.get_or_create(
        name='db_status',
        defaults={"label": 'Status', "type": 'STR', "description": 'Used by AWS Databases blueprint', "show_on_servers": True}
    )
    CustomField.objects.get_or_create(
        name='db_subnet_group',
        defaults={"label": 'Subnet group', "type": 'STR', "description": 'Used by AWS Databases blueprint'}
    )
    CustomField.objects.get_or_create(
        name='db_subnets',
        defaults={"label": 'Subnets', "type": 'STR', "description": 'Used by AWS Databases blueprint'}
    )


def get_boto3_service_client(env, service_name="rds"):
    """
    Return boto connection to RDS/EC2 in the specified environment's region.
    """
    rh = env.resource_handler.cast()
    return rh.get_boto3_client(env.aws_region, service_name)


def sort_dropdown_options(data, placeholder=None, is_reverse=False):
    """
    Sort dropdown options 
    """
    data = list(set(data))
    sorted_options = sorted(data, key=lambda tup: tup[1].lower(), reverse=is_reverse)
    if placeholder is not None:
        sorted_options.insert(0, placeholder)
    return {'options': sorted_options, 'override': True}


def generate_options_for_aws_region(**kwargs):
    """
    Generate AWS region/environment options
    """
    group_name = kwargs.get("group")
    try:
        group = Group.objects.get(name=group_name)
    except Exception:
        return []

    options = []
    envs = group.get_available_environments()
    aws_envs = [env for env in envs if env.resource_handler is not None and env.resource_handler.resource_technology.slug.startswith('aws')]

    if not aws_envs:
        return options

    client = get_boto3_service_client(aws_envs[0])
    rds_support_regions = [region['RegionName'] for region in client.describe_source_regions()['SourceRegions']]

    for env in aws_envs:
        if env.aws_region not in rds_support_regions:
            continue
        options.append((env.id, env.name))

    return sort_dropdown_options(options, is_reverse=True)


def generate_options_for_subnet_group_option(**kwargs):
    options = [
        ("existing", "Use Existing DB Subnet Group"),
        ("new", "Create New DB Subnet Group (Select 2+ Subnets across different AZs)")
    ]
    return {'options': options, 'override': True}


def generate_options_for_aws_mysql_subnet_group(control_value=None, **kwargs):
    options = []
    if not control_value:
        return options

    try:
        env = Environment.objects.get(id=control_value)
        rds_client = get_boto3_service_client(env, service_name="rds")

        vpc_id = getattr(env, 'vpc_id', None) or getattr(env, 'aws_vpc_id', None)
        subnet_groups = rds_client.describe_db_subnet_groups().get('DBSubnetGroups', [])

        if vpc_id:
            subnet_groups = [sg for sg in subnet_groups if sg.get('VpcId') == vpc_id]

        for sg in subnet_groups:
            sg_name = sg['DBSubnetGroupName']
            desc = sg.get('DBSubnetGroupDescription', '')
            label = f"{sg_name} - {desc}" if desc else sg_name
            options.append((sg_name, label))

        if not options:
            return {
                'options': [("", "----- No DB Subnet Groups found in VPC. Switch to 'Create New'. -----")],
                'override': True
            }

    except Exception as e:
        logger.error(f"Error fetching DB Subnet Groups for Environment {control_value}: {str(e)}")

    return sort_dropdown_options(options, placeholder=("", "----- Select Existing DB Subnet Group -----"))


def generate_options_for_aws_mysql_subnets(control_value=None, **kwargs):
    options = []
    if not control_value:
        return options

    try:
        env = Environment.objects.get(id=control_value)
        ec2_client = get_boto3_service_client(env, service_name="ec2")

        vpc_id = getattr(env, 'vpc_id', None) or getattr(env, 'aws_vpc_id', None)
        filters = [{'Name': 'vpc-id', 'Values': [vpc_id]}] if vpc_id else []
        subnets = ec2_client.describe_subnets(Filters=filters).get('Subnets', [])

        for sn in subnets:
            sn_id = sn['SubnetId']
            az = sn['AvailabilityZone']
            cidr = sn.get('CidrBlock', '')

            name_tag = sn_id
            for tag in sn.get('Tags', []):
                if tag['Key'] == 'Name':
                    name_tag = tag['Value']
                    break

            label = f"{name_tag} ({sn_id}) - {cidr} [{az}]"
            options.append((sn_id, label))

    except Exception as e:
        logger.error(f"Error fetching raw subnets for Environment {control_value}: {str(e)}")

    return sort_dropdown_options(options)


def generate_options_for_aws_mysql_security_group(control_value=None, **kwargs):
    options = []
    if not control_value:
        return options

    try:
        env = Environment.objects.get(id=control_value)
        ec2_client = get_boto3_service_client(env, service_name="ec2")

        vpc_id = getattr(env, 'vpc_id', None) or getattr(env, 'aws_vpc_id', None)
        filters = [{'Name': 'vpc-id', 'Values': [vpc_id]}] if vpc_id else []

        sgs = ec2_client.describe_security_groups(Filters=filters).get('SecurityGroups', [])

        for sg in sgs:
            sg_id = sg['GroupId']
            sg_name = sg['GroupName']
            desc = sg.get('Description', '')
            label = f"{sg_name} ({sg_id}) - {desc}" if desc else f"{sg_name} ({sg_id})"
            options.append((sg_id, label))

        if not options:
            return {
                'options': [("", "----- No Security Groups found in VPC. Create SG in AWS & refresh. -----")],
                'override': True
            }

    except Exception as e:
        logger.error(f"Error fetching Security Groups for Environment {control_value}: {str(e)}")

    return sort_dropdown_options(options, placeholder=("", "----- Select Security Group -----"))


def generate_options_for_db_engine_version(control_value=None, **kwargs):
    """
    Generate MySQL Database Engine version options
    Dependency: aws_region
    """
    options = []
    if not control_value:
        return options

    env = Environment.objects.get(id=control_value)
    client = get_boto3_service_client(env)

    version_rgx = r'^\d(\.\d)*$'
    filters = [{'Name': 'status', 'Values': ['available']}, {'Name': 'engine-mode', 'Values': ['provisioned']}]

    for engine in client.describe_db_engine_versions(Engine='mysql', IncludeAll=False, Filters=filters)['DBEngineVersions']:
        option_label = engine['DBEngineVersionDescription']
        if re.match(version_rgx, engine['EngineVersion']) and engine['EngineVersion'] not in engine['DBEngineVersionDescription']:
            option_label = f"{engine['DBEngineVersionDescription']} : {engine['EngineVersion']}"
        options.append((f"{engine['EngineVersion']}/{env.id}", option_label))

    return sort_dropdown_options(options, is_reverse=True)


def generate_options_for_instance_class(control_value=None, **kwargs):
    """
    Generate MySQL Database Instance Class options
    Dependency: db_engine_version
    """
    options = []
    if not control_value:
        return options

    parts = control_value.split("/")
    env = Environment.objects.get(id=parts[1])
    client = get_boto3_service_client(env)

    ins_cls_dict = {
        'xlarge': {'cpu': 4, 'storage': 32}, '2xlarge': {'cpu': 8, 'storage': 64},
        '4xlarge': {'cpu': 16, 'storage': 128}, '8xlarge': {'cpu': 32, 'storage': 256},
        '16xlarge': {'cpu': 64, 'storage': 512}, 'large': {'cpu': 2, 'storage': 16},
        'small': {'cpu': 2, 'storage': 2}, 'medium': {'cpu': 2, 'storage': 4}
    }

    instance_klasss = client.describe_orderable_db_instance_options(
        Engine='mysql', Vpc=True, EngineVersion=parts[0]
    )['OrderableDBInstanceOptions']

    for instance_klass in instance_klasss:
        st_dict = ins_cls_dict.get(instance_klass['DBInstanceClass'].split(".")[-1], None)
        if "MaxStorageSize" in instance_klass and st_dict is not None:
            if instance_klass['MinStorageSize'] <= st_dict['storage'] <= instance_klass['MaxStorageSize']:
                storage = st_dict['storage']
                cpu = st_dict['cpu']
            else:
                storage = instance_klass['MinStorageSize']
                cpu = int(storage) // 8 if int(storage) // 8 > 1 else 2
        elif st_dict is not None:
            storage = st_dict['storage']
            cpu = st_dict['cpu']
        else:
            continue

        key = f"{instance_klass['DBInstanceClass']}$?{storage}$?{instance_klass['StorageType']}"
        name = f"{instance_klass['DBInstanceClass']} ({storage} GiB RAM, {cpu} vCPUs, {instance_klass['StorageType'].capitalize()} Storage)"
        options.append((key, name))

    return sort_dropdown_options(options, is_reverse=True)


def boto_instance_to_dict(boto_instance, env, client):
    """
    Create a pared-down representation of a MySQL database from the full boto dictionary.
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
    }

    subnet_group = boto_instance.get("DBSubnetGroup", {})
    endpoint = boto_instance.get('Endpoint', {})

    if not endpoint:
        time.sleep(10)
        mysql_response = client.describe_db_instances(
            DBInstanceIdentifier=boto_instance['DBInstanceIdentifier'],
            Filters=[{'Name': 'engine', 'Values': [boto_instance['Engine']]}]
        )['DBInstances']
        if mysql_response:
            endpoint = mysql_response[0].get('Endpoint', {})

    instance.update({
        'db_endpoint_address': endpoint.get('Address'),
        'db_endpoint_port': endpoint.get('Port'),
        'db_subnet_group': subnet_group.get("DBSubnetGroupName"),
        'db_subnets': [xx['SubnetIdentifier'] for xx in subnet_group.get("Subnets", [])]
    })

    logger.info(f'MySQL database {instance} created successfully.')
    return instance


def run(job, logger=None, **kwargs):
    set_progress('Creating AWS MySQL database...')
    logger.info('Creating AWS MySQL database...')

    resource = kwargs.pop('resources').first()
    get_or_create_custom_fields_as_needed()

    env = Environment.objects.get(id="""{{ aws_region }}""")

    db_identifier = """{{ db_identifier }}"""
    db_engine_version = """{{ db_engine_version }}""".split("/")[0]
    instance_class_obj = """{{ instance_class }}""".split("$?")
    instance_class = instance_class_obj[0].strip()
    allocated_storage = int(instance_class_obj[1])
    storage_type = instance_class_obj[2].strip()
    db_username = """{{ db_username }}"""
    db_password = """{{ db_password }}"""
    subnet_group_option = """{{ subnet_group_option }}"""
    existing_subnet_group = """{{ aws_mysql_subnet_group }}"""
    raw_subnets_input = """{{ aws_mysql_subnets }}"""
    selected_sg = """{{ aws_mysql_security_group }}"""

    client = get_boto3_service_client(env)
    ec2_client = get_boto3_service_client(env, service_name="ec2")
    vpc_id = getattr(env, 'vpc_id', None) or getattr(env, 'aws_vpc_id', None)

    if subnet_group_option == "new":
        if isinstance(raw_subnets_input, list):
            subnet_ids = raw_subnets_input
        else:
            cleaned_str = str(raw_subnets_input).translate(str.maketrans('', '', "[]'\""))
            subnet_ids = [s.strip() for s in cleaned_str.split(",") if s.strip()]

        if len(subnet_ids) < 2:
            return "FAILURE", f"AWS RDS requires at least 2 subnets in different Availability Zones to create a DB Subnet Group. Selected subnets: {subnet_ids}", ""

        vpc_identifier = None
        if vpc_id:
            try:
                vpcs = ec2_client.describe_vpcs(VpcIds=[vpc_id]).get('Vpcs', [])
                if vpcs:
                    for tag in vpcs[0].get('Tags', []):
                        if tag['Key'] == 'Name':
                            vpc_identifier = tag['Value']
                            break
            except Exception as e:
                logger.warning(f"Could not fetch VPC tags for {vpc_id}: {str(e)}")

        if not vpc_identifier:
            vpc_identifier = vpc_id if vpc_id else "vpc"

        clean_vpc_prefix = re.sub(r'[^a-zA-Z0-9-]', '-', vpc_identifier)
        clean_db_identifier = re.sub(r'[^a-zA-Z0-9-]', '-', db_identifier)

        new_subnet_group_name = re.sub(r'-+', '-', f"sng-{clean_vpc_prefix}-{clean_db_identifier}").strip('-').lower()

        set_progress(f"Creating new AWS DB Subnet Group '{new_subnet_group_name}' with subnets {subnet_ids}...")

        try:
            client.create_db_subnet_group(
                DBSubnetGroupName=new_subnet_group_name,
                DBSubnetGroupDescription=f"Created subnet group for {db_identifier} in {vpc_identifier}",
                SubnetIds=subnet_ids
            )
            target_subnet_group = new_subnet_group_name
        except Exception as err:
            if 'DBSubnetGroupAlreadyExists' in str(err):
                target_subnet_group = new_subnet_group_name
            else:
                return "FAILURE", f"Failed to create DB Subnet Group: {str(err)}", ""

    elif subnet_group_option == "existing":
        target_subnet_group = existing_subnet_group.strip()
        if not target_subnet_group or target_subnet_group.startswith('{{'):
            return "FAILURE", "Please select an existing DB Subnet Group from the dropdown.", ""

    else:
        return "FAILURE", f"Invalid Subnet Group Option selected: '{subnet_group_option}'", ""

    if not selected_sg or "aws_mysql_security_group" in selected_sg:
        if vpc_id:
            sgs = ec2_client.describe_security_groups(
                Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}, {'Name': 'group-name', 'Values': ['default']}]
            ).get('SecurityGroups', [])
            if sgs:
                selected_sg = sgs[0]['GroupId']

    mysql_payload = dict(
        DBInstanceIdentifier=db_identifier,
        DBInstanceClass=instance_class,
        StorageType=storage_type,
        AutoMinorVersionUpgrade=False,
        CopyTagsToSnapshot=True,
        Engine='mysql',
        EngineVersion=db_engine_version,
        MasterUsername=db_username,
        MasterUserPassword=db_password,
        BackupRetentionPeriod=7,
        StorageEncrypted=True,
        DeletionProtection=False,
        LicenseModel="general-public-license",
        AllocatedStorage=allocated_storage,
        DBName=db_identifier,
        DBSubnetGroupName=target_subnet_group
    )

    if selected_sg and not selected_sg.startswith('{{'):
        mysql_payload['VpcSecurityGroupIds'] = [selected_sg]

    if storage_type == 'io1':
        mysql_payload['Iops'] = 1000

    set_progress(f'Create MySQL database "{db_identifier}" using Subnet Group "{target_subnet_group}"')

    try:
        mysql_response = client.create_db_instance(**mysql_payload)
    except Exception as err:
        if 'DBInstanceAlreadyExists' in str(err):
            return ("FAILURE", "Database already exists", f"DB instance {db_identifier} exists already")
        raise

    waiter = client.get_waiter('db_instance_available')
    waiter.config.max_attempts = 100
    waiter.wait(DBInstanceIdentifier=db_identifier)

    logger.info(f"MySQL instance response {mysql_response}")
    mysql_instance_dict = boto_instance_to_dict(mysql_response['DBInstance'], env, client)

    for key, value in mysql_instance_dict.items():
        setattr(resource, key, value)

    resource.name = db_identifier
    resource.save()

    set_progress(f'MySQL database {db_identifier} created successfully.')
    return 'SUCCESS', f'MySQL database {db_identifier} created successfully.', ''