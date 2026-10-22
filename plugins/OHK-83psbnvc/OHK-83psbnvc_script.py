"""
This CloudBolt plug-in restores scaling policies, applies the product license file,
creates the initial CloudBolt superuser, disables quick setup, and configures
supervisord and Apache services on the newly created HA cluster instances.
"""
import base64
import os
import socket
import time
import paramiko

from django.conf import settings
from common.methods import set_progress
from infrastructure.models import Server
from resourcehandlers.aws.models import AWSHandler


def copy_file_to_or_from_remote_server(server, key_file_path, from_path, To_path, action, max_retries=10, delay=10):
    """
    Safely connects via Paramiko with retry limits using ec2-user.
    """
    host_name = server.ip
    if not host_name:
        raise ValueError(f"Server '{server.hostname}' has no IP address assigned.")

    username = 'ec2-user'
    if getattr(server, 'credentials', None) and server.credentials.username:
        username = server.credentials.username

    for attempt in range(1, max_retries + 1):
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            set_progress(f"Connecting to {server.hostname} ({host_name}) as '{username}' via SSH (Attempt {attempt}/{max_retries})...")
            ssh_client.connect(
                hostname=host_name,
                username=username,
                key_filename=key_file_path,
                timeout=30,
                banner_timeout=30
            )
            
            sftp = ssh_client.open_sftp()
            if action == "upload":
                set_progress(f"Copying file from '{from_path}' to server '{server.hostname}:{To_path}'")
                sftp.put(from_path, To_path)
            elif action == "download":
                set_progress(f"Copying file from server '{server.hostname}:{from_path}' to local '{To_path}'")
                sftp.get(from_path, To_path)
            sftp.close()
            set_progress(f"File transfer successfully completed for server '{server.hostname}'")
            return

        except (paramiko.SSHException, TimeoutError, socket.timeout, OSError) as err:
            set_progress(f"SSH Connection error on server '{server.hostname}' ({err}). Retrying in {delay}s...")
            if attempt == max_retries:
                raise RuntimeError(
                    f"Failed to connect to '{server.hostname}' ({host_name}) after {max_retries} attempts."
                ) from err
        finally:
            ssh_client.close()
            time.sleep(delay)


def get_boto3_client(rh, service_name, region=None):
    """
    Retrieves Boto3 client safely through CloudBolt AWS resource handler wrapper.
    """
    wrapper = rh.get_api_wrapper()
    return wrapper.get_boto3_client(service_name, rh.serviceaccount, rh.servicepasswd, region)


def run(job, *args, **kwargs):
    resource = kwargs.get('resource')
    if not resource:
        raise ValueError("Resource parameter is required for configure_product_license_and_user plugin.")

    base_name = resource.base_name
    aws_ha_region = resource.aws_region_ha
    rh = AWSHandler.objects.get(id=resource.aws_rh_id)
    auto_scaling_client = get_boto3_client(rh, 'autoscaling', region=aws_ha_region)

    upload_dir = getattr(settings, "MEDIA_ROOT", "/var/www/html/cloudbolt/static/uploads/")
    if not upload_dir.endswith("/"):
        upload_dir += "/"

    proserv_path = getattr(settings, "PROSERV_DIR", "/var/opt/cloudbolt/proserv/")
    if not proserv_path.endswith("/"):
        proserv_path += "/"

    username = '{{username}}'
    email_id = '{{email_id}}'
    password = '{{password}}'
    product_license_file = "{{product_license_file}}"

    key_file_path = f"{proserv_path}{resource.ec2_key_name}.pem"
    from_path = f"{upload_dir}{product_license_file}"
    fname = product_license_file.split("/")[-1]
    to_path = f"/tmp/{fname}"

    from_path_userdetails = f"{proserv_path}SuperUserDetails.txt"
    to_path_userdetails = "/tmp/SuperUserDetails.txt"
    
    # Generate superuser creation payload using dict constructor to avoid escaping issues
    userdetails = (
        f'from django.contrib.auth.models import User; '
        f'u, created = User.objects.get_or_create(username="{username}", defaults=dict(email="{email_id}")); '
        f'u.email = "{email_id}"; u.set_password("{password}"); u.is_superuser = True; u.is_staff = True; u.save()'
    )
    user_b64_string = base64.b64encode(userdetails.encode("ascii")).decode("ascii")
    
    with open(from_path_userdetails, "w") as f:
        f.write(user_b64_string)

    # 1. Restore original scaling policy threshold
    load_balancer_arn = resource.ha_load_balancer_arn
    target_group_arn = resource.target_group_arn
    if resource.asg_metric_type in ["ALBRequestCountPerTarget"]:
        resource_label = f'''{"/".join(load_balancer_arn.split("/")[1:])}/targetgroup/{"/".join(target_group_arn.split("/")[1:])}'''
        predefined_metric_specification = {'PredefinedMetricType': resource.asg_metric_type, 'ResourceLabel': resource_label}
    else:
        predefined_metric_specification = {'PredefinedMetricType': resource.asg_metric_type}
        try:
            auto_scaling_client.attach_load_balancer_target_groups(
                AutoScalingGroupName=resource.auto_scaling_group_name,
                TargetGroupARNs=[resource.target_group_arn]
            )
        except Exception as e:
            set_progress(f"Target group attachment notice: {e}")

    try:
        auto_scaling_client.put_scaling_policy(
            AutoScalingGroupName=resource.auto_scaling_group_name,
            PolicyName=f"SP-{base_name}",
            PolicyType='TargetTrackingScaling',
            AdjustmentType='ChangeInCapacity',
            TargetTrackingConfiguration={
                'PredefinedMetricSpecification': predefined_metric_specification,
                'TargetValue': int(resource.asg_policy_targetvalue)
            },
        )
        set_progress(f"Scaling threshold value restored to {resource.asg_policy_targetvalue} successfully.")
    except Exception as err:
        set_progress(f"Updating threshold value to {resource.asg_policy_targetvalue} failed: {err}")

    replace_autostart = """sudo runuser root -c 'sed -i "/autostart=false/c\\autostart=true" /etc/supervisord.d/jobengine.conf'"""
    replace_autorestart = """sudo runuser root -c 'sed -i "/autorestart=false/c\\autorestart=true" /etc/supervisord.d/jobengine.conf'"""

    # Ensure /usr/local/bin is first in PATH so Python 3.12 is invoked
    env_prefix = "export PATH=/usr/local/bin:$PATH"

    first_instance = True
    if fname.split(".")[-1].lower() == 'bin':
        for server_id in resource.server_ids.split(","):
            server = Server.objects.get(id=int(server_id))

            server.username = 'ec2-user'
            if getattr(server, 'credentials', None):
                server.credentials.username = 'ec2-user'
                server.credentials.save()
            server.save()

            if first_instance:
                set_progress(f"Establishing connection with server '{server.hostname}'")
                copy_file_to_or_from_remote_server(server, key_file_path, from_path, to_path, "upload")
                
                # 1. Apply Product License
                command_to_exec = (
                    f"sudo runuser root -c '"
                    f"{env_prefix}; "
                    f"test -f /usr/bin/python || ln -sf /usr/local/bin/python3 /usr/bin/python; "
                    f"/usr/local/bin/python3 /opt/cloudbolt/manage.py load_license -f /tmp/{fname}'"
                )
                set_progress(f"Applying Product license to server '{server.hostname}'")
                server.execute_script(script_contents=command_to_exec, timeout=300)

                # 2. Create Superuser
                copy_file_to_or_from_remote_server(server, key_file_path, from_path_userdetails, to_path_userdetails, "upload")
                set_progress(f"Creating superuser on '{server.hostname}'...")
                
                create_user_cmd = (
                    f"sudo runuser root -c '"
                    f"{env_prefix}; "
                    f"cat /tmp/SuperUserDetails.txt | base64 --decode | /usr/local/bin/python3 /opt/cloudbolt/manage.py shell'"
                )
                server.execute_script(script_contents=create_user_cmd, timeout=300)
                
                # 3. Disable Quick Setup Wizard
                quick_setup_cmd = (
                    f"sudo runuser root -c '"
                    f"{env_prefix}; "
                    f"/usr/local/bin/python3 /opt/cloudbolt/manage.py quick_setup_off'"
                )
                server.execute_script(script_contents=quick_setup_cmd, timeout=300)
                first_instance = False

            # Configure Supervisord
            set_progress(f"Enabling autostart and autorestart in supervisord on '{server.hostname}'")
            server.execute_script(script_contents=replace_autostart, timeout=240)
            server.execute_script(script_contents=replace_autorestart, timeout=240)
            
            set_progress(f"Reloading supervisor service on '{server.hostname}'")
            server.execute_script(
                script_contents=f"sudo runuser root -c '{env_prefix}; supervisorctl reload || systemctl restart supervisord || true'", 
                timeout=240
            )

            # Restart Apache
            set_progress(f"Restarting httpd service on server '{server.hostname}'")
            server.execute_script(script_contents="sudo runuser root -c 'systemctl restart httpd'", timeout=180)

        return "SUCCESS", "Product License and user configuration applied on all servers successfully", ""
    else:
        return "FAILURE", "Product License must have a '.bin' file extension", ""