"""
Discover Amazon Aurora Database records with some basic identifying attributes.
"""
from common.methods import set_progress
from infrastructure.models import CustomField
from resourcehandlers.aws.models import AWSHandler
from botocore.client import ClientError
from utilities.logger import ThreadLogger

logger = ThreadLogger(__name__)

RESOURCE_IDENTIFIER = ['db_cluster_identifier', 'db_cluster_endpoint']


def get_or_create_custom_fields_as_needed():
    CustomField.objects.get_or_create(
        name='aws_rh_id',
        defaults={
            'label': 'AWS RH ID',
            'type': 'STR',
            'show_as_attribute': True,
            'description': 'Used by the AWS Databases blueprint'
        }
    )

    CustomField.objects.get_or_create(
        name='db_endpoint_address',
        defaults={
            'label': 'Endpoint Address',
            'type': 'STR',
            'description': 'Used by the AWS Databases blueprint',
            'show_on_servers': True,
            'show_as_attribute': True,
        }
    )

    CustomField.objects.get_or_create(
        name='db_cluster_port',
        defaults={
            'label': 'Db Cluster Port',
            'type': 'STR',
            'description': 'Used by the AWS Databases blueprint',
            'show_on_servers': True,
            'show_as_attribute': True,
        }
    )

    CustomField.objects.get_or_create(
        name='db_availability_zone',
        defaults={
            'label': 'Availability Zone',
            'type': 'STR',
            'description': 'Used by the AWS Databases blueprint',
            'show_as_attribute': True,
        }
    )

    CustomField.objects.get_or_create(
        name='db_engine',
        defaults={
            'label': 'Engine',
            'type': 'STR',
            'description': 'Used by the AWS Databases blueprint',
            'show_as_attribute': True,

        }
    )

    CustomField.objects.get_or_create(
        name='db_status',
        defaults={
            'label': 'Status',
            'type': 'STR',
            'description': 'Used by the AWS Databases blueprint',
            'show_on_servers': True,
            'show_as_attribute': True,
        }
    )

    CustomField.objects.get_or_create(
        name='db_subnet_group',
        defaults={
            'label': 'Subnet Group',
            'type': 'STR',
            'description': 'Used by the AWS Databases blueprint'
        }
    )

    CustomField.objects.get_or_create(
        name='db_instances',
        defaults={
            'label': 'Db Instances',
            'type': 'STR',
            'description': 'Used by the AWS Databases blueprint',
            'show_on_servers': True,
            'show_as_attribute': True,
        }
    )

    CustomField.objects.get_or_create(
        name='db_cluster_identifier',
        defaults={
            'label': 'Db Cluster Identifier',
            'type': 'STR',
            'description': 'Used by the AWS Databases blueprint',
            'show_on_servers': True,
            'show_as_attribute': True,
        }
    )

    CustomField.objects.get_or_create(
        name='cluster_reader_endpoint',
        defaults={
            'label': 'Cluster Reader Endpoint',
            'type': 'STR',
            'description': 'Used by the AWS Databases blueprint',
            'show_on_servers': True,
            'show_as_attribute': True,
        }
    )

    CustomField.objects.get_or_create(
        name='aws_region',
        defaults={
            'label': 'AWS Region',
            'type': 'STR',
            'description': 'Used by the AWS Databases blueprint',
            'show_on_servers': True,
            'show_as_attribute': True,
        }
    )

    CustomField.objects.get_or_create(
        name='db_engine_mode',
        defaults={
            'label': 'Db Engine Mode',
            'type': 'STR',
            'description': 'Used by the AWS Databases blueprint',
            'show_as_attribute': True,
            'show_on_servers': True
        }
    )

    CustomField.objects.get_or_create(
        name='db_cluster_arn',
        defaults={
            'label': 'Db Cluster Arn',
            'type': 'STR',
            'description': 'Used by the AWS Databases blueprint',
            'show_as_attribute': True,
            'show_on_servers': True
        }
    )

    CustomField.objects.get_or_create(
        name='db_master_username',
        defaults={
            'label': 'Db Master Username',
            'type': 'STR',
            'description': 'Used by the AWS Databases blueprint',
            'show_as_attribute': True,
            'show_on_servers': True
        }
    )

    CustomField.objects.get_or_create(
        name='db_cluster_endpoint',
        defaults={
            'label': 'Db Cluster Endpoint',
            'type': 'STR',
            'description': 'Used by the AWS Databases blueprint',
            'show_as_attribute': True,
            'show_on_servers': True
        }
    )

    CustomField.objects.get_or_create(
        name='db_engine_version',
        defaults={
            'label': 'Db Engine Version',
            'type': 'STR',
            'description': 'Used by the AWS Databases blueprint',
            'show_as_attribute': True,
            'show_on_servers': True
        }
    )

    CustomField.objects.get_or_create(
        name='db_cluster_min_capacity',
        defaults={
            'label': 'Serverless Min capacity',
            'type': 'STR',
            'description': 'Used by the AWS Databases blueprint',
            'show_as_attribute': True,
            'show_on_servers': True
        }
    )

    CustomField.objects.get_or_create(
        name='db_cluster_max_capacity',
        defaults={
            'label': 'Serverless Max capacity',
            'type': 'STR',
            'description': 'Used by the AWS Databases blueprint',
            'show_as_attribute': True,
            'show_on_servers': True
        }
    )


def boto_cluster_to_dict(boto_cluster, region, handler):
    '''
    Create a pared-down representation of an RDS Cluster from the full boto dictionary.
    '''

    instance = {
        'name': boto_cluster['DBClusterIdentifier'],
        'db_cluster_identifier': boto_cluster.get('DBClusterIdentifier'),
        'db_master_username': boto_cluster['MasterUsername'],
        'aws_region': region,
        'aws_rh_id': handler.id,
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

    if boto_cluster['EngineMode'] == 'serverless':
        scaling_config = boto_cluster.get('ScalingConfigurationInfo')
        if scaling_config:
            instance.update({'db_cluster_min_capacity': str(scaling_config.get('MinCapacity')) + ' ACU',
                             'db_cluster_max_capacity': str(scaling_config.get('MaxCapacity')) + ' ACU'
                             })

    cluster_members = [inst.get('DBInstanceIdentifier') for inst in boto_cluster.get('DBClusterMembers')]
    if cluster_members:
        instance.update({'db_instances': cluster_members})
    instance.update({'cluster_reader_endpoint': boto_cluster.get('ReaderEndpoint')})

    logger.info(f'Discovered {instance} Aurora database on AWS.')

    return instance
    

def discover_resources(**kwargs):
    set_progress(f'Started discovering Aurora database on AWS.')
    logger.info(f'Started discovering Aurora database on AWS.')

    # get or create custom fields
    get_or_create_custom_fields_as_needed()

    discovered_aurora_database = []
    handler: AWSHandler
    for handler in AWSHandler.objects.all():
        for region in handler.current_regions():
            rds = handler.get_boto3_client(region, 'rds')

            try:
                db_clusters = rds.describe_db_clusters(
                    Filters=[
                        {
                            'Name': 'engine',
                            'Values': [ 
                                'aurora-mysql', 'aurora-postgresql'
                            ]
                        },
                    ]
                )['DBClusters']
            except ClientError as e:
                set_progress('AWS ClientError: {}'.format(e))
                continue
            
            for db_cluster in db_clusters:

                if db_cluster['Engine'] not in ['aurora', 'aurora-mysql', 'aurora-postgresql']:
                    continue

                discovered_aurora_database.append(boto_cluster_to_dict(db_cluster, region, handler))

    return discovered_aurora_database