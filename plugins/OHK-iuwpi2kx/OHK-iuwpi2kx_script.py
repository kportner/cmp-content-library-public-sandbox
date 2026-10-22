import socket
import time
import paramiko
from django.conf import settings
from common.methods import set_progress
from infrastructure.models import Server
from resources.models import Resource


def copy_file_to_or_from_remote_server(server, key_file_path, from_path, To_path, action, max_retries=10, delay=10):
    """
    Safely connects via Paramiko with retry limits using ec2-user.
    """
    host_name = server.ip
    if not host_name:
        raise ValueError(f"Server '{server.hostname}' has no IP address assigned.")

    # Dynamically resolve username, defaulting to ec2-user
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


def run(job, *args, **kwargs):
    proserv_path = getattr(settings, "PROSERV_DIR", "/var/opt/cloudbolt/proserv/")
    if not proserv_path.endswith("/"):
        proserv_path += "/"

    resource = kwargs.get('resource')
    if not resource:
        raise ValueError("Resource parameter is required for mount_shared_file_system plugin.")

    key_file_path = f"{proserv_path}{resource.ec2_key_name}.pem"
    filesystem_id = resource.efs_id
    region = resource.aws_region_ha
    efs_dns_name = f"{filesystem_id}.efs.{region}.amazonaws.com"
    first_instance = True

    for server_id in resource.server_ids.split(","):
        server = Server.objects.get(id=int(server_id))

        # Explicitly ensure server username in CloudBolt DB is set to ec2-user
        server.username = 'ec2-user'
        if getattr(server, 'credentials', None):
            server.credentials.username = 'ec2-user'
            server.credentials.save()
        server.save()

        set_progress(f"Installing NFS Client on '{server.hostname}'")
        server.execute_script(script_contents="sudo runuser -l root -c 'yum -y install nfs-utils'", timeout=360)

        set_progress(f"Creating /mnt/efs directory on '{server.hostname}'")
        server.execute_script(script_contents="sudo runuser -l root -c 'mkdir -p /mnt/efs'", timeout=120)

        set_progress(f"Mounting EFS file system on '{server.hostname}'")
        mount_efs_cmd = f"sudo runuser -l root -c 'mount -t nfs4 -o nfsvers=4.1,rsize=1048576,wsize=1048576,hard,timeo=600,retrans=2,noresvport {efs_dns_name}:/ /mnt/efs'"
        server.execute_script(script_contents=mount_efs_cmd, timeout=240)

        if first_instance:
            set_progress(f"Stopping web and job engine services before data migration on '{server.hostname}'")
            server.execute_script(script_contents="sudo runuser -l root -c 'systemctl stop httpd supervisord || true'", timeout=180)

            set_progress(f"Migrating /var/opt/cloudbolt to EFS on '{server.hostname}'...")
            move_cloudbolt_cmd = (
                "sudo runuser -l root -c '"
                "if [ -d \"/var/opt/cloudbolt\" ]; then "
                "  mv /var/opt/cloudbolt /mnt/efs/cloudbolt; "
                "else "
                "  mkdir -p /mnt/efs/cloudbolt; "
                "fi'"
            )
            server.execute_script(script_contents=move_cloudbolt_cmd, timeout=900)

            set_progress(f"Migrating /var/log/cloudbolt/jobs to EFS on '{server.hostname}'...")
            move_jobs_cmd = (
                "sudo runuser -l root -c '"
                "if [ -d \"/var/log/cloudbolt/jobs\" ]; then "
                "  mv /var/log/cloudbolt/jobs /mnt/efs/jobs; "
                "else "
                "  mkdir -p /mnt/efs/jobs; "
                "fi'"
            )
            server.execute_script(script_contents=move_jobs_cmd, timeout=900)

            set_progress(f"Migrating static assets to EFS on '{server.hostname}'...")
            move_static_cmd = (
                "sudo runuser -l root -c '"
                "if [ -d \"/var/www/html/cloudbolt/static\" ]; then "
                "  mv /var/www/html/cloudbolt/static /mnt/efs/static; "
                "else "
                "  mkdir -p /mnt/efs/static; "
                "fi'"
            )
            server.execute_script(script_contents=move_static_cmd, timeout=900)
            first_instance = False
        else:
            set_progress(f"Cleaning local directories on secondary node '{server.hostname}'")
            server.execute_script(script_contents="sudo runuser -l root -c 'rm -rf /var/opt/cloudbolt'", timeout=240)
            server.execute_script(script_contents="sudo runuser -l root -c 'rm -rf /var/log/cloudbolt/jobs'", timeout=240)
            server.execute_script(script_contents="sudo runuser -l root -c 'rm -rf /var/www/html/cloudbolt/static'", timeout=240)

        set_progress(f"Creating required target mount directories on '{server.hostname}'")
        server.execute_script(script_contents="sudo runuser -l root -c 'mkdir -p /var/opt/cloudbolt'", timeout=120)
        server.execute_script(script_contents="sudo runuser -l root -c 'mkdir -p /var/log/cloudbolt/jobs'", timeout=120)
        server.execute_script(script_contents="sudo runuser -l root -c 'mkdir -p /var/www/html/cloudbolt/static'", timeout=120)

        set_progress(f"Mapping required directories with EFS on '{server.hostname}'")
        server.execute_script(script_contents=f"sudo runuser -l root -c 'mount -t nfs4 -o nfsvers=4.1,rsize=1048576,wsize=1048576,hard,timeo=600,retrans=2,noresvport {efs_dns_name}:/cloudbolt /var/opt/cloudbolt'", timeout=240)
        server.execute_script(script_contents=f"sudo runuser -l root -c 'mount -t nfs4 -o nfsvers=4.1,rsize=1048576,wsize=1048576,hard,timeo=600,retrans=2,noresvport {efs_dns_name}:/jobs /var/log/cloudbolt/jobs'", timeout=240)
        server.execute_script(script_contents=f"sudo runuser -l root -c 'mount -t nfs4 -o nfsvers=4.1,rsize=1048576,wsize=1048576,hard,timeo=600,retrans=2,noresvport {efs_dns_name}:/static /var/www/html/cloudbolt/static'", timeout=240)

        set_progress(f"Updating fstab file on '{server.hostname}'")
        local_file_path = f"{proserv_path}fstab_setting.txt"
        remote_file_path = "/tmp/fstab_setting.txt"
        lines = [
            f"{efs_dns_name}:/cloudbolt /var/opt/cloudbolt nfs rw,hard,intr,rsize=8192,wsize=8192,timeo=14 0 0\n",
            f"{efs_dns_name}:/jobs /var/log/cloudbolt/jobs nfs rw,hard,intr,rsize=8192,wsize=8192,timeo=14 0 0\n",
            f"{efs_dns_name}:/static /var/www/html/cloudbolt/static nfs rw,hard,intr,rsize=8192,wsize=8192,timeo=14 0 0\n"
        ]
        with open(local_file_path, "w") as f:
            f.writelines(lines)

        copy_file_to_or_from_remote_server(server, key_file_path, local_file_path, remote_file_path, "upload")
        server.execute_script(script_contents=f"sudo runuser -l root -c 'cat {remote_file_path} >> /etc/fstab'", timeout=120)