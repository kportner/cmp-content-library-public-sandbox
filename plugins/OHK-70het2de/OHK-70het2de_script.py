from common.methods import set_progress
from infrastructure.models import Environment
from resourcehandlers.aws.models import AWSHandler

def create_client(env_id):
    env = Environment.objects.get(id=env_id)
    rh: AWSHandler = env.resource_handler.cast()
    client = rh.get_boto3_client(env.aws_region, 'elasticache')
    return client

def generate_options_for_nodes(server=None, **kwargs):
    options = []
    resource = kwargs.get('resource')
    if resource:
        if resource.env_id:
            client = create_client(resource.env_id)
        else:
            env = Environment.objects.filter(aws_region = resource.aws_region)[0]
            client = create_client(env.id)
        response = client.describe_cache_clusters(
                CacheClusterId=resource.cluster_name, ShowCacheNodeInfo=True)
        for cache_cluster in response['CacheClusters']:
            for node in cache_cluster['CacheNodes']:
                options.append(node["CacheNodeId"])
    return options
    

def run(job, *args, **kwargs):
    nodes = "{{ nodes }}"
    
    trans_table = nodes.maketrans(" ", ",", "[]',")
    nodes = nodes.translate(trans_table).split(',')

    resource = kwargs.get('resource')
    if resource.env_id:
        client = create_client(resource.env_id)
    else:
        env = Environment.objects.filter(aws_region = resource.aws_region)[0]
        client = create_client(env.id)

    try:
        client.reboot_cache_cluster(
            CacheClusterId=resource.cluster_name,
            CacheNodeIdsToReboot=nodes
        )
        waiter = client.get_waiter('cache_cluster_available')
        waiter.wait(
            CacheClusterId=resource.cluster_name
        )
        
        response = client.describe_cache_clusters(
            CacheClusterId=resource.cluster_name)

        return "SUCCESS", "Rebooted nodes successfully", f"Rebooted nodes successfully of {resource.cluster_name}"
    except Exception as e:
        return "FAILURE", "Exception", f"{e}"