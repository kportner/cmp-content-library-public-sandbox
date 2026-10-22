import base64
from django.conf import settings
from common.methods import set_progress
from resourcehandlers.aws.models import AWSHandler


def run(job, *args, **kwargs):
    proserv_path = getattr(settings, "PROSERV_DIR", "/var/opt/cloudbolt/proserv/")
    if not proserv_path.endswith("/"):
        proserv_path += "/"

    resource = kwargs.get('resource')
    if not resource:
        raise ValueError("Resource parameter is required for update_auto_scaling_group_template plugin.")

    filesystem_id = resource.efs_id
    region = resource.aws_region_ha
    launch_template_id = resource.launch_template_id
    
    rh = AWSHandler.objects.get(id=resource.aws_rh_id)
    wrapper = rh.get_api_wrapper()
    ec2_client = wrapper.get_boto3_client('ec2', rh.serviceaccount, rh.servicepasswd, region)
    
    efs_dns_name = f"{filesystem_id}.efs.{region}.amazonaws.com"

    # Fixed shebang, added mkdir -p, and cleaned up nested sudo commands
    user_data = """#!/bin/bash
sudo runuser -l root -c 'yum install -y nfs-utils'
sudo runuser -l root -c 'sed -i "/autostart=true/c\\autostart=false" /etc/supervisord.d/jobengine.conf'
sudo runuser -l root -c 'sed -i "/autorestart=true/c\\autorestart=false" /etc/supervisord.d/jobengine.conf'
sudo runuser -l root -c 'supervisorctl reload'
sudo runuser -l root -c 'mkdir -p /mnt/efs'
sudo runuser -l root -c 'rm -rf /var/opt/cloudbolt'
sudo runuser -l root -c 'rm -rf /var/log/cloudbolt/jobs'
sudo runuser -l root -c 'rm -rf /var/www/html/cloudbolt/static'
sudo runuser -l root -c 'mkdir -p /var/opt/cloudbolt'
sudo runuser -l root -c 'mkdir -p /var/log/cloudbolt/jobs'
sudo runuser -l root -c 'mkdir -p /var/www/html/cloudbolt/static'
sudo runuser -l root -c 'mount -t nfs4 -o nfsvers=4.1,rsize=1048576,wsize=1048576,hard,timeo=600,retrans=2,noresvport {0}:/ /mnt/efs'
sudo runuser -l root -c 'mount -t nfs4 -o nfsvers=4.1,rsize=1048576,wsize=1048576,hard,timeo=600,retrans=2,noresvport {0}:/cloudbolt /var/opt/cloudbolt'
sudo runuser -l root -c 'mount -t nfs4 -o nfsvers=4.1,rsize=1048576,wsize=1048576,hard,timeo=600,retrans=2,noresvport {0}:/jobs /var/log/cloudbolt/jobs'
sudo runuser -l root -c 'mount -t nfs4 -o nfsvers=4.1,rsize=1048576,wsize=1048576,hard,timeo=600,retrans=2,noresvport {0}:/static /var/www/html/cloudbolt/static'
sudo runuser -l root -c 'echo "{0}:/cloudbolt /var/opt/cloudbolt nfs rw,hard,intr,rsize=8192,wsize=8192,timeo=14 0 0" >> /etc/fstab'
sudo runuser -l root -c 'echo "{0}:/jobs /var/log/cloudbolt/jobs nfs rw,hard,intr,rsize=8192,wsize=8192,timeo=14 0 0" >> /etc/fstab'
sudo runuser -l root -c 'echo "{0}:/static /var/www/html/cloudbolt/static nfs rw,hard,intr,rsize=8192,wsize=8192,timeo=14 0 0" >> /etc/fstab'
sudo runuser -l root -c 'sed -i "/autostart=false/c\\autostart=true" /etc/supervisord.d/jobengine.conf'
sudo runuser -l root -c 'sed -i "/autorestart=false/c\\autorestart=true" /etc/supervisord.d/jobengine.conf'
sudo runuser -l root -c 'supervisorctl reload'
sudo runuser -l root -c 'systemctl restart httpd'
""".format(efs_dns_name)

    user_data_bytes = user_data.encode("ascii")
    user_data_base64_string = base64.b64encode(user_data_bytes).decode("ascii")

    set_progress(f"Retrieving Launch Template '{launch_template_id}' details...")
    response = ec2_client.describe_launch_templates(LaunchTemplateIds=[launch_template_id])
    source_version = response['LaunchTemplates'][0]['LatestVersionNumber']

    set_progress(f"Creating new Launch Template version with EFS user data...")
    lt_response = ec2_client.create_launch_template_version(
        LaunchTemplateId=launch_template_id,
        SourceVersion=str(source_version),
        VersionDescription="Updated version with auto-mount EFS and Oracle Linux 8 fixes",
        LaunchTemplateData={
            'UserData': user_data_base64_string,
        }
    )
    
    new_version = lt_response['LaunchTemplateVersion']['VersionNumber']
    
    set_progress(f"Setting Launch Template default version to {new_version}...")
    ec2_client.modify_launch_template(
        LaunchTemplateId=launch_template_id,
        DefaultVersion=str(new_version)
    )

    return "SUCCESS", f"Auto scaling group '{resource.auto_scaling_group_name}' launch template updated successfully.", ""