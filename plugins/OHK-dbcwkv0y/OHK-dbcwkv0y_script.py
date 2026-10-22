from common.methods import set_progress
from infrastructure.models import CustomField, Environment
from resourcehandlers.aws.models import AWSHandler

RESOURCE_IDENTIFIER = ['cluster_name', 'aws_region']

def connect_to_elasticache(env):
    """
    Return boto connection to the elasticache in the specified environment's region.
    """
    rh: AWSHandler = env.resource_handler.cast()
    return rh.get_boto3_client(env.aws_region, 'elasticache')

def create_custom_fields_as_needed():
    CustomField.objects.get_or_create(
        name='aws_rh_id', defaults={
            'label': 'AWS RH ID', 'type': 'STR',
            'description': 'Used by the AWS blueprints',
            'show_as_attribute': True
        }
    )
    CustomField.objects.get_or_create(
        name='env_id', defaults={
            'label': 'Environment ID', 'type': 'STR',
            'description': 'Used by the AWS blueprints',
            'show_as_attribute': True
        }
    )
    CustomField.objects.get_or_create(
        name='name', defaults={
            'label': 'AWS ElastiCache', 'type': 'STR',
            'description': 'Used by the AWS blueprints',
            'show_as_attribute': True
        }
    )
    aws_region, _ = CustomField.objects.get_or_create(
        name='aws_region', defaults={
            'label': 'AWS ElastiCache Region', 'type': 'STR',
            'description': 'AWS ElastiCache cluster region',
            'show_as_attribute': True
        }
    )
    if aws_region.show_on_servers == False:
        aws_region.show_on_servers = True
        aws_region.show_as_attribute = True
        aws_region.save()
    CustomField.objects.get_or_create(
        name='cluster_name', defaults={
            'label': 'AWS ElastiCache Cluster Name', 'type': 'STR',
            'show_as_attribute': True
        }
    )
    CustomField.objects.get_or_create(
        name='engine', defaults={
            'label': 'AWS ElastiCache Engine', 'type': 'STR',
            'description': 'The name of the cache engine to be used for this cluster',
            'show_as_attribute': True
        }
    )
    CustomField.objects.get_or_create(
        name='cache_node_type', defaults={
            'label': 'AWS ElastiCache Node Type', 'type': 'STR',
            'description': 'The type of the cache node to be used for this cluster',
            'show_as_attribute': True
        }
    )
    CustomField.objects.get_or_create(
        name='nodes_count', defaults={
            'label': 'AWS ElastiCache Nodes', 'type': 'INT',
            'description': 'The number of the cache nodes within this cluster',
            'show_as_attribute': True
        }
    )



def discover_resources(**kwargs):
    discovered_cache = []
    # cache = []

    envs = Environment.objects.filter(
        resource_handler__resource_technology__name="Amazon Web Services")
    
    create_custom_fields_as_needed()

    regions_covered = []
    for env in envs:
        if not env.aws_region or env.aws_region in regions_covered:
            continue
        else:
            regions_covered.append(env.aws_region)
        client = connect_to_elasticache(env)
        try:
            response = client.describe_cache_clusters()
            for res in response.get('CacheClusters'):
                discovered_cache.append({
                    'name': res.get('CacheClusterId'),
                    'cluster_name': res.get('CacheClusterId'),
                    'engine': f"{res.get('Engine')} {res.get('EngineVersion')}",
                    'aws_rh_id': env.resource_handler_id,
                    'cache_node_type': res.get('CacheNodeType'),
                    'nodes_count': res.get('NumCacheNodes'),
                    'aws_region': env.aws_region,
                })

        except Exception as error:
            set_progress(error)
            continue
        
    return discovered_cache