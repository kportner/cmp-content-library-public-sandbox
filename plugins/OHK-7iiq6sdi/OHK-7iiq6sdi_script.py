"""
Build service item action for AWS MariaDB database blueprint.
"""
import time
from accounts.models import Group
from botocore.exceptions import ClientError
from common.methods import set_progress
from infrastructure.models import CustomField, Environment
from resourcehandlers.aws.models import AWSHandler


def generate_options_for_env_id(server=None, **kwargs):
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
    
    aws_envs= [(env.id, env.name) for env in envs if env.resource_handler is not None and env.resource_handler.resource_technology.slug.startswith('aws')]
    
    return aws_envs


def generate_options_for_instance_class(**kwargs):
    return [
        ('db.t2.micro', 'Burst Capable - db.t2.micro'),
        ('db.t2.small', 'Burst Capable - db.t2.small'),
        ('db.t2.medium', 'Burst Capable - db.t2.medium'),
        ('db.t2.large', 'Burst Capable - db.t2.large'),
        ('db.m4.large', 'Standard - db.m4.large'),
        ('db.m4.xlarge', 'Standard - db.m4.xlarge'),
        ('db.m4.2xlarge', 'Standard - db.m4.2xlarge'),
        ('db.m4.4xlarge', 'Standard - db.m4.4xlarge'),
        ('db.m4.10xlarge', 'Standard - db.m4.10xlarge'),
        ('db.r3.large', 'Memory Optimized - db.r3.large'),
        ('db.r3.xlarge', 'Memory Optimized - db.r3.xlarge'),
        ('db.r3.2xlarge', 'Memory Optimized - db.r3.2xlarge'),
        ('db.r3.4xlarge', 'Memory Optimized - db.r3.4xlarge'),
        ('db.r3.8xlarge', 'Memory Optimized - db.r3.8xlarge'),
    ]


def create_custom_fields_as_needed():
    CustomField.objects.get_or_create(
        name='aws_rh_id', defaults={'label': 'AWS MariaDB RH ID', 'type': 'STR',
                                    'description': 'Used by the AWS MariaDB blueprint'}
    )

    CustomField.objects.get_or_create(
        name='db_identifier', defaults={'label': 'AWS database identifier', 'type': 'STR',
                                        'description': 'Used by the AWS MariaDB blueprint'}
    )

    CustomField.objects.get_or_create(
        name='db_address', defaults={'label': 'AWS database address', 'type': 'STR',
                                     'description': 'Used by the AWS MariaDB blueprint'}, show_as_attribute=True
    )

    CustomField.objects.get_or_create(
        name='db_port', defaults={'label': 'AWS database port', 'type': 'STR',
                                  'description': 'Used by the AWS MariaDB blueprint'}, show_as_attribute=True
    )
    
    CustomField.objects.get_or_create(
        name='aws_region', defaults={'label': 'AWS Region', 'type': 'STR',
                                  'description': 'Used by the AWS MariaDB blueprint'}
    )


def run(resource, logger=None, **kwargs):
    env_id = '{{ env_id }}'
    env = Environment.objects.get(id=env_id)
    region = env.aws_region
    rh: AWSHandler = env.resource_handler.cast()
    db_identifier = '{{ db_identifier }}'

    create_custom_fields_as_needed()

    resource.name = 'RDS MariaDB - ' + db_identifier
    resource.db_identifier = db_identifier
    resource.aws_region = region
    resource.aws_rh_id = rh.id
    resource.save()

    set_progress('Connecting to Amazon RDS')
    
    # get aws client object
    rds = rh.get_boto3_client(region, 'rds')

    set_progress('Create RDS MariaDB database "{}"'.format(db_identifier))

    try:
        response = rds.create_db_instance(
            DBInstanceIdentifier=db_identifier,
            MasterUsername='{{ db_master_username }}',
            MasterUserPassword='{{ master_password }}',
            Engine='mariadb',
            DBInstanceClass='{{ instance_class }}',
            AllocatedStorage=5,
        )
    except Exception as err:
        return "FAILURE", "MariaDB Database could not be created", str(err)
    
    waiter = rds.get_waiter('db_instance_available')
    set_progress("...waiting for DB instance to be ready...")
    waiter.wait(DBInstanceIdentifier=db_identifier)
    
    response = rds.describe_db_instances(DBInstanceIdentifier=db_identifier)['DBInstances'][0]
    
    resource.db_address = response['Endpoint']['Address']
    resource.db_port = response['Endpoint']['Port']
    resource.lifecycle = 'ACTIVE'
    resource.save()

    return "SUCCESS", "Created MariaDB successfully", ""