from infrastructure.models import Environment
from common.methods import set_progress
from resourcehandlers.aws.models import AWSHandler

def create_client(env_id):
    env = Environment.objects.get(id=env_id)
    rh: AWSHandler = env.resource_handler.cast()
    client = rh.get_boto3_client(env.aws_region, 'elasticache')
    return client

def run(job, *args, **kwargs):
    nodes_to_add = int("{{ nodes_to_add }}")

    resource = kwargs.get('resource')
    if resource.env_id:
        client = create_client(resource.env_id)
    else:
        env = Environment.objects.filter(aws_region = resource.aws_region)[0]
        client = create_client(env.id)
    if resource.engine.split()[0] == 'redis':
        if nodes_to_add > 1:
            return "FAILURE", "Can add only 1 node at a time in Redis Engine", "Can add only 1 node at a time in Redis Engine, kindly change the number of nodes to add"
    elif resource.engine.split()[0] == 'memcached':
        if nodes_to_add > 20:
            return "FAILURE", "Can add maximum 20 nodes at a time in Memcached Engine", "Can add maximum 20 nodes at a time in Memcached Engine, kindly change the number of nodes to add"
    try:
        client.modify_cache_cluster(
            CacheClusterId=resource.cluster_name,
            NumCacheNodes=resource.nodes_count+nodes_to_add,
            ApplyImmediately=True,
            CacheNodeType=resource.cache_node_type
        )
        waiter = client.get_waiter('cache_cluster_available')
        waiter.wait(
            CacheClusterId=resource.cluster_name
        )
        
        response = client.describe_cache_clusters(
            CacheClusterId=resource.cluster_name)
    
        resource.nodes_count = response['CacheClusters'][0]['NumCacheNodes']
        resource.save()

        return "SUCCESS", "Added nodes successfully", f"Added nodes successfully to {resource.cluster_name}"
    except Exception as e:
        return "FAILURE", "Exception", f"{e}"