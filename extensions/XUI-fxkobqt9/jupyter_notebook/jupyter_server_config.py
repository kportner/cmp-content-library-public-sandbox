# Delivered by xui/jupyter_notebook — configures CloudBolt's jupyterd
# JupyterLab server (manage.py shell_plus --lab) with no customer_settings.py
# edits. Install once:
#   cp /var/opt/cloudbolt/proserv/xui/jupyter_notebook/jupyter_server_config.py /usr/local/etc/jupyter/
c = get_config()  # noqa

c.ServerApp.ip = "127.0.0.1"
c.ServerApp.base_url = "/shell"
c.ServerApp.allow_origin = "*"
c.ServerApp.allow_remote_access = True
# Allow the CMP page to embed the notebook in an iframe.
c.ServerApp.tornado_settings = {
    "headers": {"Content-Security-Policy": "frame-ancestors https://* 'self' "}
}
c.ServerApp.root_dir = "/home/cloudbolt"

# JupyterLab's built assets live under the pip prefix, not the default
# <sys.prefix>/share/jupyter/lab this build computes.
c.LabApp.app_dir = "/usr/local/lib/python3.12/site-packages/share/jupyter/lab"

# Only expose the Django Shell-Plus kernel: the plain "Python 3 (ipykernel)"
# kernel has no CMP models and only produces NameError confusion.
c.KernelSpecManager.allowed_kernelspecs = {"django_extensions"}
c.MappingKernelManager.default_kernel_name = "django_extensions"

try:
    # Inside jupyterd, CMP's Django settings module is already imported —
    # reuse its token/port so the XUI iframe URLs keep matching.
    import settings

    c.ServerApp.port = int(settings.NOTEBOOK_PORT)
    c.IdentityProvider.token = settings.NOTEBOOK_TOKEN
except ImportError:
    pass
