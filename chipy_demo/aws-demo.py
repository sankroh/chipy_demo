from boto.ec2.connection import EC2Connection
from boto.exception import EC2ResponseError
from config import *
from fabric.api import *
from fabric.contrib.files import exists, upload_template
from fabric.contrib.console import confirm

import posixpath, time, base64, socket

env.user = "ubuntu"
env.key_filename = PUBLIC_KEY_FILE[:-4]
env.paths = {"sites": posixpath.join(ROOT_PATH, "sites"),}
env.python_version = "2.6"

"""
EC2 Fabric SSH workaround. See here: http://www.mail-archive.com/fab-user@nongnu.org/msg01170.html
"""
def _test_ssh(address, port=22, throw=True):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.settimeout(1)
            sock.connect((address, port))
            return True
        except socket.timeout:
            if throw:
                raise
        except socket.error, e:
            if throw or e.errno != 111:
                raise
        finally:
            sock.close()
        return False

def start_instances():
    env.hosts = []
    # TODO: Add check for valid keys
    # Start up AMI
    conn = EC2Connection(AWS_ACCESS_KEY, AWS_SECRET_KEY)

    try:
        f = open(PUBLIC_KEY_FILE,'r')
        public_key_material = base64.b64encode(f.read().strip())
    except NameError as exception:
        print "Please check your config, it doesn't seem like there is a PUBLIC_KEY_FILE setting! \n"
        print "==============================="
        print exception
        print "==============================="
    except IOError as exception:
        print "Please check your config, there seems to be an issue with permissions or the path is incorrect! \n"
        print "==============================="
        print exception
        print "==============================="

    # Import public keys to the EC2 Key Pair
    try:
        conn.import_key_pair(KEY_NAME, public_key_material)
    except NameError as exception:
        print "Please check your config, there does not seem to be a key file mentioned! \n"
        print "==============================="
        print exception
        print "==============================="

    # TODO: Add check for 64-bit or 32-bit and adjust instance type based on that.
    # TODO: Add security groups

    try:
        reservation = conn.run_instances(EC2_AMI, instance_type=INSTANCE_TYPE, key_name=KEY_NAME, max_count=NUM_INSTANCES)
    except EC2ResponseError as exception:
        print "An error occurred please check! \n"
        print "==============================="
        print exception
        print "==============================="

    # Hacky, but only way to accomplish this now.
    while reservation.instances[0].state != u'running':
        res_id = reservation.instances[0].id
        print "Waiting for AWS to start instance(s)..."
        time.sleep(TIMEOUT)
        reservation = conn.get_all_instances([res_id])[0]

    # Tag instances
    for count,inst in enumerate(reservation.instances):
        conn.create_tags([inst.id], {'Name': 'linux-auto-launch-' + str(count)})

    # Assign elastic IP
    ip_list = []
    if PUBLIC_IPS:
        # Create new IP per instance & associate with each instance
        for inst in reservation.instances:
            try:
                new_address = conn.allocate_address()
            except EC2ResponseError as exception:
                print "An error occurred please check! \n"
                print "==============================="
                print exception
                print "==============================="
            ip_list.append(new_address)
            new_address.associate(inst.id)
            # Test SSH connection
            while True:
                print "Testing SSH connectivity"
                if _test_ssh(new_address.public_ip, throw=False):
                    print "SSH connection successful!"
                    break

    print "Instance IP(s): " + str(ip_list)
    print "AWS setup done!"
    env.hosts += [ip.public_ip for ip in ip_list]

def init():
    ubuntu_setup()
    #virtualenv()
    #wsgi_conf()
    #nginx()
    #apache()

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
            if project_name[1] == 'com':
                # Sample case - abc.com
                env.project_name = project_name[0]
            else:
                # Sample case - shop.abc.com
                env.project_name = project_name[1]
        except IndexError:
            env.project_name = env.site_name

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
    #sudo('apt-get -y install ruby ruby-dev rubygems', shell=False)
    # DEBIAN_FRONTEND=noninteractive is to make non-interactive prompts
    sudo('DEBIAN_FRONTEND=noninteractive apt-get -y install postfix', shell=False)
    #sudo('gem install haml', shell=False)
    sudo('pip install virtualenv', shell=False)
    sudo('pip install fabric', shell=False)
    print "Packages installed"
                
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
        sudo("chown -R ubuntu:www-data %s" % env.site_name)
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

