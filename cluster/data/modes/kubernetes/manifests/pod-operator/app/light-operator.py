import kopf
import kubernetes.client
from kubernetes import config
import os
import subprocess
import time

# Load the in-cluster Kubernetes configuration.
config.load_incluster_config()

# Create a Kubernetes API client
v1 = kubernetes.client.CoreV1Api()

SSH_KEY = os.environ.get("SSH_KEY_PATH", "/root/.ssh/id_rsa")
SSH_USER = os.environ.get("NODE_SSH_USER", "pi")
LIGHT_SCRIPT = os.environ.get(
    "LIGHT_SCRIPT_PATH", "/home/pi/Documents/light/serial_control_host.py"
)


def _ssh(ip_address, color):
    return [
        "ssh",
        "-i", SSH_KEY,
        "-o", "StrictHostKeyChecking=no",
        f"{SSH_USER}@{ip_address}",
        f"python3 {LIGHT_SCRIPT} {color}",
    ]


def flash(ip_address, command):
    try:
        # Set the LEDs to the given colour, then clear them again.
        subprocess.run(_ssh(ip_address, command), check=True)
        time.sleep(0.5)
        subprocess.run(_ssh(ip_address, "black"), check=True)

    except subprocess.CalledProcessError as e:
        print(f"An error occurred while running the SSH command: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

@kopf.on.create('pods')
def on_create_pod(body, spec, status, **kwargs):
    """
    This function is triggered whenever a Pod is created in the cluster.
    It fetches and prints the node IP address where the Pod is scheduled.
    """
    pod_name = body['metadata']['name']
    namespace = body['metadata']['namespace']
    node_name = spec.get('nodeName')

    if node_name:
        # Fetch the node details
        node_info = v1.read_node(name=node_name)
        node_ip = None

        # Find the first InternalIP in the node's addresses
        for address in node_info.status.addresses:
            if address.type == 'InternalIP':
                node_ip = address.address
                break
        
        if node_ip:
            print(f"Pod '{pod_name}' in namespace '{namespace}' is scheduled on node '{node_name}' with IP '{node_ip}'.")
            flash(node_ip, "green")
        else:
            print(f"Pod '{pod_name}' in namespace '{namespace}' is scheduled on node '{node_name}', but no InternalIP found.")
    else:
        print(f"Pod '{pod_name}' in namespace '{namespace}' is not yet scheduled on any node.")

@kopf.on.delete('pods')
def on_delete_pod(body, spec, status, **kwargs):
    """
    This function is triggered whenever a Pod is created in the cluster.
    It fetches and prints the node IP address where the Pod is scheduled.
    """
    pod_name = body['metadata']['name']
    namespace = body['metadata']['namespace']
    node_name = spec.get('nodeName')

    if node_name:
        # Fetch the node details
        node_info = v1.read_node(name=node_name)
        node_ip = None

        # Find the first InternalIP in the node's addresses
        for address in node_info.status.addresses:
            if address.type == 'InternalIP':
                node_ip = address.address
                break
        
        if node_ip:
            print(f"Pod '{pod_name}' in namespace '{namespace}' is deleted on node '{node_name}' with IP '{node_ip}'.")
            flash(node_ip, "red")

if __name__ == '__main__':
    # Start the operator
    kopf.run()
