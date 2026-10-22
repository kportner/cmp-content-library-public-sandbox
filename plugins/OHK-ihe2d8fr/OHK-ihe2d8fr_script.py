from infrastructure.models import CustomField, Environment
from resourcehandlers.aws.models import AWSHandler
from common.methods import set_progress
import time
import re


def connect_to_elasticache(env):
    """
    Return boto connection to the elasticache in the specified environment's region.
    """
    rh: AWSHandler = env.resource_handler.cast()
    return (rh.id, rh.get_boto3_client(env.aws_region, 'elasticache'))


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
        name='name', defaults={
            'label': 'AWS ElastiCache', 'type': 'STR',
            'description': 'Used by the AWS blueprints',
            'show_as_attribute': True
        }
    )
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


def generate_options_for_aws_environment(profile=None, **kwargs):
    group = kwargs["group"]

    # fetch all group environment
    envs = group.get_available_environments()
    options = [(env.id, env.name) for env in envs if env.resource_handler is not None and env.resource_handler.resource_technology.slug.startswith('aws')]
    return options

def generate_options_for_engine(control_value=None, **kwargs):
    options = []
    if control_value:
        env = Environment.objects.get(id=control_value)
        rh_id, client = connect_to_elasticache(env)
        engines = client.describe_cache_engine_versions()
        return list(set(map(lambda d: (d['Engine']+'-'+str(control_value), d['Engine']), engines['CacheEngineVersions'])))
    return sorted(options)

def generate_options_for_engine_version(control_value=None, **kwargs):
    options = []
    if control_value:
        engine, env_id = control_value.split('-')
        env = Environment.objects.get(id=int(env_id))
        rh_id, client = connect_to_elasticache(env)
        engines = client.describe_cache_engine_versions(Engine=engine)
        versions = [(y['EngineVersion']+'-'+y['CacheParameterGroupFamily']+'-'+env_id, y['EngineVersion']) for y in engines['CacheEngineVersions'] if engine==y['Engine']]
        return versions
    return options
    
def generate_options_for_cache_parameter_group_name(control_value=None, **kwargs):
    options = []
    if control_value:
        version, family, env_id = control_value.split('-')
        env = Environment.objects.get(id=int(env_id))
        rh_id, client = connect_to_elasticache(env)
        response = client.describe_cache_parameter_groups()
        cache_parameter_group_names = [(x['CacheParameterGroupName']+'-'+env_id, x['CacheParameterGroupName']) for x in response['CacheParameterGroups'] if x['CacheParameterGroupFamily']==family]
        return cache_parameter_group_names
    return options
    
def generate_options_for_cache_node_type(control_value=None, **kwargs):
    options = []
    node_type_dict = {}
    if control_value:
        group_name, env_id = control_value.split('-')
        env = Environment.objects.get(id=int(env_id))
        rh_id, client = connect_to_elasticache(env)
        response = client.describe_cache_parameters(CacheParameterGroupName=group_name)
        for i in response['CacheNodeTypeSpecificParameters']:
            key = ' '.join(re.split('-|_', i['ParameterName']))
            description = i['Description']
            for j in i['CacheNodeTypeSpecificValues']:
                if not node_type_dict.get(j['CacheNodeType']):
                    node_type_dict[j['CacheNodeType']] = j['CacheNodeType']
                node_type_dict[j['CacheNodeType']] += f" - {key} ({description}) : {j['Value']}"
            for key, value in node_type_dict.items():
                _, generation, _ = key.split('.')
                options.append((key, generation.upper()+' node - '+value))
        return options
    return options

def find_or_create_cache_subnet_group(env, client):
    # find cache subnet group
    csg = client.describe_cache_subnet_groups()
    subnet_groups = list(map(lambda d: d['CacheSubnetGroupName'], csg['CacheSubnetGroups']))
    if subnet_groups:
        return subnet_groups[0]
    
    # create subnet group
    # get ec2 boto3 client object
    rh: AWSHandler = env.resource_handler.cast()
    ec2_client = rh.get_boto3_client(env.aws_region, 'ec2')
    # fetch all ec2 region subnets
    subnets = ec2_client.describe_subnets()['Subnets']
    if not subnets:
        raise RuntimeError(f"Subnet does not exists for EC2 region({env.aws_region})")

    response = client.create_cache_subnet_group(
        CacheSubnetGroupName = f"default-{env.vpc_id}",
        CacheSubnetGroupDescription = '',
        SubnetIds=[xx['SubnetId'] for xx in subnets if xx['VpcId'] == env.vpc_id]
    )
    return response['CacheSubnetGroup']['CacheSubnetGroupName']

def run(resource, *args, **kwargs):
    create_custom_fields_as_needed()

    cluster_name = "{{ cluster_name }}"
    engine = "{{ engine }}"
    engine, env_id = engine.split('-')
    engine_version = "{{ engine_version }}"
    CacheNodeType = "{{ cache_node_type }}"
    env = Environment.objects.get(id='{{ aws_environment }}')
    NumCacheNodes = "{{ num_cache_nodes }}"
    CacheParameterGroupName = "{{ cache_parameter_group_name }}"
    
    if engine == 'redis':
        NumCacheNodes = 1

    rh_id, client = connect_to_elasticache(env)
    CacheSubnetGroupName = find_or_create_cache_subnet_group(env, client)

    try:
        client.create_cache_cluster(
            CacheClusterId=cluster_name,
            Engine=engine,
            CacheNodeType=CacheNodeType,
            NumCacheNodes=int(NumCacheNodes),
            CacheSubnetGroupName=CacheSubnetGroupName
        )
        waiter = client.get_waiter('cache_cluster_available')
        waiter.wait(
            CacheClusterId=cluster_name
        )

    except Exception as error:
        return "FAILURE", "", f"{error}"

    response = client.describe_cache_clusters(
        CacheClusterId=cluster_name)

    cache_instances = response['CacheClusters']
    if len(cache_instances) != 1:
        raise RuntimeError(
            "Multiple caches with this name {0} identified. ".format(cluster_name))

    cache_instance = cache_instances[0]

    status = cache_instance['CacheClusterStatus']
    set_progress('Status of the cluster is: %s' % status)

    if status == 'available':
        set_progress('Cluster is now available on host')

    resource.name = cluster_name
    resource.cluster_name = cluster_name
    resource.engine = f"{engine} {engine_version}"
    resource.aws_rh_id = rh_id
    resource.env_id = env.id
    resource.aws_region = env.aws_region
    resource.cache_node_type = CacheNodeType
    resource.nodes_count = NumCacheNodes
    resource.save()

    return "SUCCESS", "", ""