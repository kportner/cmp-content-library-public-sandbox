from common.methods import set_progress
from resourcehandlers.aws.models import AWSHandler

RESOURCE_IDENTIFIER = 'cluster_name'



def discover_resources(**kwargs):
    redshift_clusters = []
    handler: AWSHandler
    for handler in AWSHandler.objects.all():
        for region in handler.current_regions():
            # get aws client object
            client = handler.get_boto3_client(region, 'redshift')
            try:
                clusters = client.describe_clusters().get('Clusters')
            except Exception as error:
                set_progress(error)
                continue

            if not clusters:
                continue

            for cluster in clusters:
                if cluster.get('NumberOfNodes') == 1:
                    cluster_type = 'single-node'
                else:
                    cluster_type = 'multi-node'
                
                data = {
                    'name': cluster.get('ClusterIdentifier'),
                    'cluster_name': cluster.get('ClusterIdentifier'),
                    'node_type': cluster.get('NodeType'),
                    'cluster_type': cluster_type,
                    'master_username': cluster.get('MasterUsername'),
                    'aws_rh_id': handler.id, 
                    'aws_region': region 
                }
                
                if data not in redshift_clusters:
                    redshift_clusters.append(data)

    return redshift_clusters