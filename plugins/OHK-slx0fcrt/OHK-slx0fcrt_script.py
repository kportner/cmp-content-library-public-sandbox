"""
Build service item action for AWS RDS Aurora (provisioned & serverless) blueprint.
"""
import re
import time
from botocore.exceptions import ClientError
from infrastructure.models import CustomField, Environment
from common.methods import set_progress
from accounts.models import Group
from resourcehandlers.aws.models import AWSHandler
from utilities.logger import ThreadLogger

logger = ThreadLogger(__name__)


def get_or_create_custom_fields_as_needed():
    CustomField.objects.get_or_create(
        name='aws_rh_id',
        defaults={
            "label": 'AWS RH ID',
            "type": 'STR',
            'show_as_attribute': True,
            "description": 'Used by the AWS Databases blueprint'
        }
    )

    CustomField.objects.get_or_create(
        name='db_endpoint_address',
        defaults={
            "label": 'Endpoint Address',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            "show_on_servers": True,
            'show_as_attribute': True,
        }
    )

    CustomField.objects.get_or_create(
        name='db_cluster_port',
        defaults={
            "label": 'Db Cluster Port',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            "show_on_servers": True,
            'show_as_attribute': True,
        }
    )

    CustomField.objects.get_or_create(
        name='db_availability_zone',
        defaults={
            "label": 'Availability Zone',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            'show_as_attribute': True,
        }
    )

    CustomField.objects.get_or_create(
        name='db_engine',
        defaults={
            "label": 'Engine',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            'show_as_attribute': True,

        }
    )

    CustomField.objects.get_or_create(
        name='db_status',
        defaults={
            "label": 'Status',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            "show_on_servers": True,
            'show_as_attribute': True,
        }
    )

    CustomField.objects.get_or_create(
        name='db_subnet_group',
        defaults={
            "label": 'Subnet Group',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint'
        }
    )

    CustomField.objects.get_or_create(
        name="db_instances",
        defaults={
            "label": 'Db Instances ',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            "show_on_servers": True,
            'show_as_attribute': True,
        }
    )

    CustomField.objects.get_or_create(
        name="db_cluster_identifier",
        defaults={
            "label": 'Db Cluster Identifier',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            "show_on_servers": True,
            'show_as_attribute': True,
        }
    )

    CustomField.objects.get_or_create(
        name="cluster_reader_endpoint",
        defaults={
            "label": 'Db Cluster Reader Endpoint',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            "show_on_servers": True,
            'show_as_attribute': True,
        }
    )

    CustomField.objects.get_or_create(
        name="aws_region",
        defaults={
            "label": 'AWS Region',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            "show_on_servers": True,
            'show_as_attribute': True,
        }
    )

    CustomField.objects.get_or_create(
        name='db_engine_mode',
        defaults={
            "label": 'Db Engine Mode',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            'show_as_attribute': True,
            "show_on_servers": True
        }
    )

    CustomField.objects.get_or_create(
        name='db_cluster_arn',
        defaults={
            "label": 'Db Cluster Arn',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            'show_as_attribute': True,
            "show_on_servers": True
        }
    )

    CustomField.objects.get_or_create(
        name='db_master_username',
        defaults={
            "label": 'Db Master Username',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            'show_as_attribute': True,
            "show_on_servers": True
        }
    )

    CustomField.objects.get_or_create(
        name='db_cluster_endpoint',
        defaults={
            "label": 'Db Cluster Endpoint',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            'show_as_attribute': True,
            "show_on_servers": True
        }
    )

    CustomField.objects.get_or_create(
        name='db_engine_version',
        defaults={
            "label": 'Db Engine Version',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            'show_as_attribute': True,
            "show_on_servers": True
        }
    )

    CustomField.objects.get_or_create(
        name='db_cluster_min_capacity',
        defaults={
            "label": 'Serverless Min capacity',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            'show_as_attribute': True,
            "show_on_servers": True
        }
    )

    CustomField.objects.get_or_create(
        name='db_cluster_max_capacity',
        defaults={
            "label": 'Serverless Max capacity',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            'show_as_attribute': True,
            "show_on_servers": True
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
        return []

    # fetch all group environment
    envs = group.get_available_environments()

    aws_envs = [env for env in envs if env.resource_handler is not None and env.resource_handler.resource_technology.slug.startswith('aws')]
    if not aws_envs:
        return []

    # get boto3 client
    client = get_boto3_service_client(aws_envs[0])

    # fetch all postgres supported regions
    rds_support_regions = [region['RegionName'] for region in client.describe_source_regions()['SourceRegions']]
    
    options = []

    for env in aws_envs:
        if env.aws_region not in rds_support_regions:
            continue

        options.append((env.id, env.name))

    return sort_dropdown_options(options)


def generate_options_for_engine(control_value=None, **kwargs):
    """
    Generate options for engine 
    Dependency: aws region
    """
    options = []

    if control_value is None or control_value == "":
        return options

    if control_value:
        options.extend([
            ("{0}/{1}".format(control_value, "aurora-mysql"), "Aurora-Mysql"),
            ("{0}/{1}".format(control_value, "aurora-postgresql"), "Aurora-Postgresql")
        ])

    return options

def generate_options_for_db_engine_version(control_value=None, **kwargs):
    """
    Generate RDS Database Engine version options
    Dependency: Engine - aurora , aurora-mysql, aurora-postgresql
    """
    
    options = []

    if control_value is None or control_value == "":
        return options
        
    control_value = control_value.split("/")
    
    if control_value[0]:
    
        env = Environment.objects.get(id=control_value[0])
    
        # get rds boto3 client
        client = get_boto3_service_client(env)
    
        version_rgx = '^\d(\.\d)*$'
    
        filters = [{'Name': 'status', 'Values': ['available']},
                   {'Name': 'engine-mode', 'Values': ['provisioned', 'serverless']}]
    
        for engine in client.describe_db_engine_versions(Engine=control_value[1], IncludeAll=False, Filters=filters)[
            'DBEngineVersions']:
    
            option_label = engine['DBEngineVersionDescription']
    
            if re.match(version_rgx, engine['EngineVersion']) and engine['EngineVersion'] not in engine[
                'DBEngineVersionDescription']:
                option_label = "{0} : {1}".format(engine['DBEngineVersionDescription'], engine['EngineVersion'])
    
            options.append(("{0}/{1}/{2}".format(engine['EngineVersion'], env.id, control_value[1]), option_label))
    
        return sort_dropdown_options(options)


def control_as_per_engine(type, *args):
    """
    Helper method for serverless types
    """
    # serverless v2 supports particular engine versions only 
    if args[0] in ["8.0.mysql_aurora.3.02.0",'13.6', '13.7', '14.3']:
        opst = ("{0}/{1}/{2}/{3}".format(type, *args), "Serverlessv2")

    else:
        opst = ("{0}/{1}/{2}/{3}".format(type, *args), "Serverlessv1")
    
    return opst
    

def generate_options_for_instance_class_type(control_value=None, **kwargs):
    """
    Generate instance type class options
    Dependency: Db Engine Version, Serverless Mode will only available for supported engine version 
    For Engine Aurora, Supported Engine version for Serverless V1 - 5.6.10a, 2.07.1
    For Engine Aurora Mysql, Supported Engine version for Serverless V2 3.02.0
    For Engine Aurora Postgresql, Supported Engine version for Serverless V1 10.12, 10.14, 10.18
    For Engine Aurora Postgresql, Supported Engine version for Serverless V2 13.6, 13.7, 14.3
    """

    options = []

    if control_value is None or control_value == "":
        return options

    control_value = control_value.split("/")
    
    args =(control_value[0], control_value[1], control_value[2])
    
    opts = {
        '5.6.10a': control_as_per_engine('v1', *args),
        "5.7.mysql_aurora.2.07.1": control_as_per_engine('v1', *args),
        "8.0.mysql_aurora.3.02.0": control_as_per_engine('v2', *args),
        '10.12': control_as_per_engine('postgressv1', *args),
        '10.14': control_as_per_engine('postgressv1', *args),
        '10.18': control_as_per_engine('postgressv1', *args),
        '13.6': control_as_per_engine('v2', *args),
        '13.7': control_as_per_engine('v2', *args),
        '14.3': control_as_per_engine('v2', *args),
    }

    if control_value[0] in opts:
        options.append(opts[control_value[0]])
        
    options.extend([
    ("{0}/{1}/{2}/{3}".format('r', *args), "Memory optimized classes (includes r classes)"),
    ("{0}/{1}/{2}/{3}".format('t', *args), "Burstable classes (includes t classes)")
    ])

    return options


def generate_options_for_instance_class(control_value=None, **kwargs):
    """
    Generate instance class options
    Dependency: Instance Class Type
    
    For Serverless
    For Serverless V1 - instance class type: v1 and instance class:serverlessv1
    For Serverless V2 - instance class type: v2 and instance class:Serverlessv2
    For Postgresql Serverless V1 - instance class type: postgressv1 and instance class:postgressv1
    
    Here Instance class for serverless mode only represent further max and min capacity for serverless database cluster
    
    For Provision 
    Instance class based or instance class type or 'r' or 't' type 
    """

    options = []

    if control_value is None or control_value == "":
        return options

    control_value = control_value.split("/")

    if control_value[0] == 'v1':
        options.append(("serverlessv1", "Serverless V1"))
         
    elif control_value[0] =='postgressv1':
        options.append(("postgressv1", "Serverless V1"))
        
    elif control_value[0] =='v2':
        options.append(("Serverlessv2", "Serverless V2"))

    else:
        env = Environment.objects.get(id=control_value[2])

        # get rds boto3 client
        client = get_boto3_service_client(env)

        ins_cls_dict = {'xlarge': {'cpu': 4, 'storage': 32}, '2xlarge': {'cpu': 8, 'storage': 64},
                        '4xlarge': {'cpu': 16, 'storage': 128},
                        '8xlarge': {'cpu': 32, 'storage': 256}, '16xlarge': {'cpu': 64, 'storage': 512},
                        'large': {'cpu': 2, 'storage': 16},
                        'small': {'cpu': 2, 'storage': 2}, 'medium': {'cpu': 2, 'storage': 4}
                        }

        # fetch all db engine version instance classes
        instance_klasss = client.describe_orderable_db_instance_options(Engine=control_value[3], Vpc=True,
                                                                        EngineVersion=control_value[1])['OrderableDBInstanceOptions']

        for instance_klass in instance_klasss:

            instance_type = instance_klass['DBInstanceClass'].split(".")[1]

            if instance_type.startswith(control_value[0]):

                storage = None
                cpu = None
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

                if cpu is None:
                    continue

                key = "{0}".format(instance_klass['DBInstanceClass'])
                name = "{0} ({1} GiB RAM,   {2} vCPUs, {3} Storage)".format(instance_klass['DBInstanceClass'], storage, cpu,
                                                                            instance_klass['StorageType'].capitalize())

                options.append((key, name))

    return sort_dropdown_options(options)


def generate_options_for_engine_mode(control_value=None, **kwargs):
    """
    Generate options for engine mode
    Dependency: instance class
    Showing applicable engine mode based on selected engine version and instance class 
    """
    options = []

    if control_value is None or control_value == "":
        return options

    control_value = control_value.split(".")

    if control_value[0] == "db":
        options.append(("provisioned", "Provisioned"))

    else:
        options.append(("serverless", "Serverless"))

    return options


def generate_options_for_number_of_instances(control_value=None, **kwargs):
    """
    Provide options for number of instances
    Dependency: Engine Mode show when provisioned
    Providing feature to add multiple instance inside provisioned database cluster 
    this only applicable when engine mode is provisioned 
    
    """
    return []


def generate_options_for_serverless_min_capacity(control_value=None, **kwargs):
    """
    Generate options for min capacity for serverless
    Dependency: instance class show when serverlessv1
    This only applicable for serverless engine mode when engine - 'aurora' and 'aurora-mysql'
    on supported engine version - 5.6.10a, 2.07.1
    """
    options = [
        ('1', "1 ACU  2 GiB RAM"),
        ('2', "2 ACU  4 GiB RAM"),
        ('4', "4 ACU  8 GiB RAM"),
        ('8', "8 ACU  16 GiB RAM"),
        ('16', "16 ACU  32 GiB RAM"),
        ('32', "32 ACU  64 GiB RAM"),
        ('64', "64 ACU  122 GiB RAM"),
        ('128', "128 ACU  244 GiB RAM"),
        ('256', "256 ACU  488 GiB RAM")
    ]

    return options


def generate_options_for_serverless_max_capacity(control_value=None, **kwargs):
    """
    Generate options for max capacity for serverless
    Dependency: instance class show when serverlessv1
    This only applicable for serverless engine mode when engine - 'aurora' and 'aurora-mysql'
    on supported engine version - 5.6.10a, 2.07.1
    """

    options = [
        ('1', "1 ACU  2 GiB RAM"),
        ('2', "2 ACU  4 GiB RAM"),
        ('4', "4 ACU  8 GiB RAM"),
        ('8', "8 ACU  16 GiB RAM"),
        ('16', "16 ACU  32 GiB RAM"),
        ('32', "32 ACU  64 GiB RAM"),
        ('64', "64 ACU  122 GiB RAM"),
        ('128', "128 ACU  244 GiB RAM"),
        ('256', "256 ACU  488 GiB RAM")
    ]

    return options

def generate_options_for_min_capacity_for_postgress_serverless_v1(control_value=None, **kwargs):
    """
    Generate options for min capacity for serverless
    Dependency: instance class show when postgressv1
    This only applicable for serverless engine mode when engine - 'aurora-postgresql'
    on supported engine version - 10.12, 10.14, 10.18
    """
    options = [
        ('2', "2 ACU  4 GiB RAM"),
        ('4', "4 ACU  8 GiB RAM"),
        ('8', "8 ACU  16 GiB RAM"),
        ('16', "16 ACU  32 GiB RAM"),
        ('32', "32 ACU  64 GiB RAM"),
        ('64', "64 ACU  122 GiB RAM"),
        ('192', "192 ACU  384 GiB RAM"),
        ('384', "384 ACU  768 GiB RAM")
    ]

    return options


def generate_options_for_max_capacity_for_postgress_serverless_v1(control_value=None, **kwargs):
    """
    Generate options for max capacity for serverless
    Dependency: instance class show when postgressv1
    This only applicable for serverless engine mode when engine - 'aurora-postgresql'
    on supported engine version - 10.12, 10.14, 10.18
    """
    options = [
        ('2', "2 ACU  4 GiB RAM"),
        ('4', "4 ACU  8 GiB RAM"),
        ('8', "8 ACU  16 GiB RAM"),
        ('16', "16 ACU  32 GiB RAM"),
        ('32', "32 ACU  64 GiB RAM"),
        ('64', "64 ACU  122 GiB RAM"),
        ('192', "192 ACU  384 GiB RAM"),
        ('384', "384 ACU  768 GiB RAM")
    ]

    return options


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
                DBSubnetGroupDescription='Created subnet group for RDS  Aurora DB Cluster',
                SubnetIds= [xx['SubnetId'] for xx in subnets if xx['VpcId'] == vpc_id]
            )
        except Exception as err:
            raise RuntimeError(err)
        else:
            subnet_group = sub_resp['DBSubnetGroup']['DBSubnetGroupName']
            time.sleep(10)

    return subnet_group


def boto_cluster_to_dict(boto_cluster, env):
    """
    Create a pared-down representation of an RDS instance from the full boto dictionary.
    """

    instance = {
        'db_cluster_identifier': boto_cluster.get("DBClusterIdentifier", ''),
        'db_master_username': boto_cluster['MasterUsername'],
        'aws_region': env.aws_region,
        'aws_rh_id': env.resource_handler.cast().id,
        'db_cluster_endpoint': boto_cluster['Endpoint'],
        'db_status': boto_cluster['Status'],
        'db_availability_zone': boto_cluster.get('AvailabilityZones', ''),
        'db_cluster_arn': boto_cluster['DBClusterArn'],
        'db_engine': boto_cluster['Engine'],
        'db_engine_version': boto_cluster['EngineVersion'],
        'db_engine_mode': boto_cluster['EngineMode'],
        'db_subnet_group': boto_cluster['DBSubnetGroup'],
        'db_cluster_port': boto_cluster['Port'],
    }

    return instance


def run(job, logger=None, **kwargs):
    set_progress('Creating AWS Aurora database...')
    logger.info('Creating AWS Aurora database...')

    resource = kwargs.pop('resources').first()

    # cluster identifier:
    db_identifier = '{{ db_identifier }}'

    # aws region for database cluster
    aws_region = '{{aws_region}}'
    
    engine = '{{engine}}'.split("/")[1]

    # engine version for aws database
    db_engine_version = '{{ db_engine_version }}'.split("/")[0]

    # engine mode for database cluster
    engine_mode = '{{engine_mode}}'

    # instance class type as per provisioned or serverless
    instance_class_type = '{{ instance_class_type }}'

    # instance class as per engine mode
    instance_class = '{{ instance_class }}' 

    # get or create custom field as required
    get_or_create_custom_fields_as_needed()

    # environment object
    env = Environment.objects.get(id=aws_region)

    # aws region
    region = env.aws_region

    # aws resource handler
    rh = env.resource_handler.cast()

    set_progress('Connecting to Amazon RDS Aurora')

    # get boto3 client
    rds = get_boto3_service_client(env)

    set_progress('Create RDS Aurora database cluster "{}"'.format(db_identifier))
    
    # get or create subnet group
    subnet_group = find_or_create_rds_subnet_group(rds, env) 
    
    # start deployment when engine mode is serverless
    if engine_mode == "serverless":
        
        # here serverless v2 provide feature to give desired min or max capacity with increment of 0.50 upto 128 ACU
        if instance_class == "Serverlessv2":
            min_capacity = int('{{min_capacity_for_serverless_v2}}')
            max_capacity = int('{{max_capacity_for_serverless_v2}}')
            
        elif instance_class == "postgressv1":
            
            min_capacity = int('{{min_capacity_for_postgress_serverless_v1}}')
            max_capacity = int('{{max_capacity_for_postgress_serverless_v1}}')
            
        else:
            min_capacity = int('{{serverless_min_capacity}}')
            max_capacity = int('{{serverless_max_capacity}}')
            
        try:
            response_cluster = rds.create_db_cluster(
                DBClusterIdentifier=db_identifier,
                DBSubnetGroupName=subnet_group,
                Engine=engine,
                EngineVersion=db_engine_version,
                EngineMode=engine_mode,
                MasterUsername='{{ db_master_username }}',
                MasterUserPassword='{{ master_password }}',
                ScalingConfiguration={
                    'MinCapacity': min_capacity,
                    'MaxCapacity': max_capacity,
                    'AutoPause': False,
                },
            )

        except ClientError as e:
            set_progress('AWS ClientError: {}'.format(e))
            return "FAILURE", "", e
        except Exception as err:
            return "FAILURE", "Amazon Aurora Database Cluster could not be created", str(err)

        cluster = response_cluster['DBCluster']

        while cluster['Status'] == 'creating':
            set_progress('Aurora Database Cluster "{}" is being created'.format(
                db_identifier), increment_tasks=1)

            time.sleep(60)

            cluster_dict = rds.describe_db_clusters(DBClusterIdentifier=db_identifier)

            cluster = cluster_dict['DBClusters'][0]

        scaling_config = cluster.get("ScalingConfigurationInfo")

        if scaling_config:
            resource.db_cluster_min_capacity = str(scaling_config["MinCapacity"]) + " ACU"
            resource.db_cluster_max_capacity = str(scaling_config["MaxCapacity"]) + " ACU"

    # start deployment when engine mode is provisioned
    else:
        try:
            response_cluster = rds.create_db_cluster(
                DBClusterIdentifier=db_identifier,
                DBSubnetGroupName=subnet_group,
                Engine=engine,
                EngineMode=engine_mode,
                EngineVersion=db_engine_version,
                MasterUsername='{{ db_master_username }}',
                MasterUserPassword='{{ master_password }}',
            )
        except ClientError as e:
            set_progress('AWS ClientError: {}'.format(e))
            return "FAILURE", "", e
        except Exception as err:
            return "FAILURE", "Amazon Aurora Database Cluster could not be created", str(err)

        set_progress("Writer Endpoint : %s" % response_cluster['DBCluster']['Endpoint'])
        set_progress("Reader Endpoint : %s" % response_cluster['DBCluster']['ReaderEndpoint'])
        set_progress("Creating database instance(s)...")

        # collected instances which are in creation state
        waiting_for_instances = []

        # number of instances inside cluster specified by user
        num_instances = int('{{ number_of_instances }}')

        # creating db instances
        for i in range(num_instances):

            instance_id = f'{db_identifier}-{i + 1}'

            set_progress("Creating instance %d named '%s'" % (i + 1, instance_id))

            try:
                response_instance = rds.create_db_instance(
                    DBInstanceIdentifier=instance_id,
                    DBInstanceClass=instance_class,
                    Engine=engine,
                    PubliclyAccessible=False,
                    DBClusterIdentifier=db_identifier,
                )

            except ClientError as e:
                set_progress('AWS ClientError: {}'.format(e))
                return "FAILURE", "", e

            except Exception as err:
                if 'DBInstanceAlreadyExists' in str(err):
                    return ("FAILURE", "Database already exists", "DB instance %s exists already" % db_identifier)
                else:
                    return ("FAILURE", "Instance Creation Failed", str(err))
            else:
                waiting_for_instances.append(instance_id)

        # wait until all specified instances get available
        while waiting_for_instances:
            time.sleep(20)
            for instance_id in waiting_for_instances[:]:
                # It takes awhile for the DB to be created and backed up.
                waiter = rds.get_waiter('db_instance_available')
                waiter.config.max_attempts = 100  # default is 40 but oracle takes more time.
                waiter.wait(DBInstanceIdentifier=instance_id)

                set_progress(f'Status of instance {instance_id} is: Available')

                waiting_for_instances.remove(instance_id)

        # check cluster is available after creation of all instances and fetched its details
        try:
            cluster = rds.describe_db_clusters(DBClusterIdentifier=db_identifier)['DBClusters'][0]
        except ClientError as e:
            set_progress('AWS ClientError: {}'.format(e))
            return "FAILURE", "", e
        except Exception as err:
            return "FAILURE", "Failed to fetch cluster status", str(err)

        # wait until cluster is creating
        while cluster['Status'] == 'creating':
            set_progress('Aurora Database Cluster "{}" is being created'.format(db_identifier), increment_tasks=1)
            time.sleep(60)
            cluster_dict = rds.describe_db_clusters(DBClusterIdentifier=db_identifier)
            cluster = cluster_dict['DBClusters'][0]

        # cluster reader endpoint will only available for provisioned engine mode
        resource.cluster_reader_endpoint = cluster['ReaderEndpoint']

        # collecting all instances created in cluster
        resource.db_instances = [inst['DBInstanceIdentifier'] for inst in cluster['DBClusterMembers']]

    # saving attribute for database cluster
    rds_cluster = boto_cluster_to_dict(cluster, env)

    for key, value in rds_cluster.items():
        setattr(resource, key, value)  # set custom field value
        
    resource.name=db_identifier

    resource.save()
    
    set_progress(f'Aurora database {db_identifier} created successfully.')

    return 'SUCCESS', f'Aurora database {db_identifier} created successfully.', ''