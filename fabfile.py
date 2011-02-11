from fabric.api import *
from fabric.contrib.files import exists, upload_template
from fabric.contrib.console import confirm

import posixpath
import os

env.hosts = ['174.129.244.242:22']
env.user = "ubuntu"
env.key_filename = ["/Users/rohit/.ssh/key2"]

def init():
    ubuntu_setup()

def setup():
    virtualenv()
    wsgi_conf()
    nginx()
    apache()

def ubuntu_setup():
    sudo('apt-get -y update', shell=False)
    sudo('apt-get -y install vim', shell=False)
    sudo('apt-get -y install build-essential', shell=False)
    sudo('apt-get -y install libfreetype6 libfreetype6-dev libjpeg8 libjpeg8-dev libpng12-0 libpng12-dev zlibc zlib1g zlib1g-dev', shell=False)
    sudo('apt-get -y install python-imaging python-openssl', shell=False)
    sudo('apt-get -y install python-setuptools python-dev', shell=False)
    sudo('apt-get -y install libpcre3 libpcre3-dev libpcrecpp0 libssl-dev', shell=False)
    sudo('apt-get -y install postgresql python-psycopg2', shell=False)
    sudo('apt-get -y install python-pip libpq-dev', shell=False)
    sudo('apt-get -y install git-core subversion mercurial', shell=False)
    sudo('apt-get -y install ruby ruby-dev rubygems', shell=False)
    # DEBIAN_FRONTEND=noninteractive is to make non-interactive prompts
    sudo('DEBIAN_FRONTEND=noninteractive apt-get -y install postfix', shell=False)
    sudo('gem install haml', shell=False)
    sudo('pip install virtualenv', shell=False)
    sudo('pip install fabric', shell=False)
    print "Setup completed!"

"""
Base configuration
"""

ROOT_PATH = "/var/www/"
JINJA_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "templates/jinja")

env.paths = {"sites": posixpath.join(ROOT_PATH, "sites"),}
env.python_version = "2.6"

@runs_once
def get_details():
    """
    Request details for the project.
    TODO: Get hosts
    """
    if not hasattr(env, "site_name"):
        env.site_name = prompt("Enter site domain name:")
        env.site_is_secure = confirm("Do you need SSL? (Yes/No)", default=False)
        env.app_server = prompt("Enter app server you wish to use (apache/uwsgi/gunicorn):")
        if env.site_is_secure:
            env.ip_address = prompt("Enter server IP address:")
        else:
            env.ip_address = "0.0.0.0"

        # Find out project name
        project_name = env.site_name.split('.')
        try:
            if project_name[1] == 'manifestdigital':
                # Sample case - abc.manifestdigital.net
                env.project_name = project_name[0]
            elif project_name[1] == 'com':
                # Sample case - abc.com
                env.project_name = project_name[0]
            else:
                # Sample case - shop.abc.com
                env.project_name = project_name[1]
        except IndexError:
            env.project_name = env.site_name

def virtualenv():
    """
    Set up a virtualenv for the project.
    """

    get_details()

    # Set up the virtualenv.
    with cd(env.paths["sites"]):
        run("virtualenv %s" % env.site_name)

    # Create directory structure
    with cd(posixpath.join(env.paths["sites"], env.site_name)):
        run("mkdir logs media src tmp")
        run("mkdir src/src-%s" % env.project_name)
        run("mkdir %s" % env.app_server)

    # Fix permissions TODO: CHANGE THIS!!
    with cd(env.paths["sites"]):
        sudo("chown -R riot:www-data %s" % env.site_name)
        sudo("chmod -R g+w %s" % env.site_name)


def wsgi_conf():
    """
    Create the wsgi file.
    """

    get_details()

    site_dir = posixpath.join(env.paths["sites"], env.site_name)
    if not exists(site_dir):
        run("mkdir -p %s" % site_dir)

    filename = "%s_wsgi.py" % env.project_name

    context = {
            "site_name": env.site_name,
            "project_name": env.project_name,
            "python_version": env.python_version,
            "paths": env.paths,
    }

    # Set up the wsgi dir.
    if env.app_server=='apache':
        wsgi_dir = posixpath.join(site_dir, "apache")
    else:
        wsgi_dir = posixpath.join(site_dir, "src/src-%s" % env.project_name)

    with cd(wsgi_dir):
        if not exists(filename):
            print "Template path: %s" % JINJA_TEMPLATE_PATH
            upload_template("wsgi_conf_%s.txt" % env.app_server,
                            filename,
                            context,
                            use_jinja=True,
                            template_dir=JINJA_TEMPLATE_PATH)
        else:
			#TODO: If it exists, append to it
            print "This file already exists."
            return
        run("chmod 654 %s" % filename)

def nginx():
    """Add a nginx config file for the site"""

    get_details()

    context = {
            "site_name": env.site_name,
            "paths": env.paths,
            "ip_address": env.ip_address,
            "site_is_secure": env.site_is_secure,
            "app_server": env.app_server,
    }

    nginx_path = '/etc/nginx/sites-available'

    if exists(nginx_path):
        with cd(nginx_path):
            if exists(env.site_name):
                print "nginx site configuration already exists!"
                return
            else:
                upload_template("nginx_conf.txt", 
                                 env.site_name,
                                 context,
                                 use_jinja=True,
                                 template_dir=JINJA_TEMPLATE_PATH,
                                 use_sudo=True)
                print "Created nginx site configuration file. Enabling site..."
                sudo('ln -s /etc/nginx/sites-available/%s /etc/nginx/sites-enabled/%s' % (env.site_name, env.site_name))
                #print "Site enabled. Reloading nginx..."
                #sudo('/etc/init.d/nginx reload')
                return
    else:
        print "It doesn't seem like you have nginx installed."
        return

def apache():
    """Add an apache config file for the site """

    get_details()

    context = {
            "site_name": env.site_name,
            "paths": env.paths,
            "project_name": env.project_name,
    }

    apache_path = '/etc/httpd/sites-available/'

    if exists(apache_path):
        with cd(apache_path):
            if exists(env.site_name):
                print "apache site configuration already exists!"
                return
            else:
                upload_template("apache_conf.txt", 
                                 env.site_name,
                                 context,
                                 use_jinja=True,
                                 template_dir=JINJA_TEMPLATE_PATH,
                                 use_sudo=True)
                print "Created apache site configuration file. Don't forget to enable it!"
                return
    else:
        print "It doesn't seem like you have apache installed."
        return

def uwsgi():
    """Setup uwsgi."""

    get_details()

    context = {
            "site_name": env.site_name,
            "paths": env.paths,
            "project_name": env.project_name,
    }

    supervisord_path = '/etc/supervisord.d/'

    if exists(supervisord_path):
        with cd(supervisord_path):
            if exists('%s.conf' % env.project_name):
                print "uwsgi site configuration already exists!"
                return
            else:
                upload_template("supervisord_uwsgi_conf.txt", 
                                 '%s.conf' % env.project_name,
                                 context,
                                 use_jinja=True,
                                 template_dir=JINJA_TEMPLATE_PATH,
                                 use_sudo=True)
                print "Created uwsgi site configuration file."
                sudo('chown root:root %s.conf' % env.project_name)
                sudo('chmod 644 %s.conf' % env.project_name)
                print "Reloading Supervisord..."
                sudo('/etc/init.d/supervisord restart')
                return
    else:
        print "It doesn't seem like you have supervisord installed."
        return
