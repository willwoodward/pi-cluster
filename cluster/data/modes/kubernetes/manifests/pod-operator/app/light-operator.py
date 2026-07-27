import kopf
import kubernetes.client
from kubernetes import config
import subprocess
import time

# Load the Kubernetes configuration (usually from ~/.kube/config)
config.load_incluster_config()

# Create a Kubernetes API client
v1 = kubernetes.client.CoreV1Api()

def flash(ip_address, command):
    try:
        # SSH command to set color to white
        ssh_command_white = [
            "ssh",
            "-i", "/root/.ssh/id_rsa",
            "-o", "StrictHostKeyChecking=no",
            f"pi@{ip_address}",
            f"python3 /home/pi/Documents/light/serial_control_host.py {command}"
        ]
        
        # SSH command to set color to black
        ssh_command_black = [
            "ssh",
            "-i", "/root/.ssh/id_rsa",
            "-o", "StrictHostKeyChecking=no",
            f"pi@{ip_address}",
            f"python3 /home/pi/Documents/light/serial_control_host.py black"
        ]
        
        # Set the color to white on the remote host
        subprocess.run(ssh_command_white, check=True)
        
        time.sleep(0.5)
        
        # Set the color to black on the remote host
        subprocess.run(ssh_command_black, check=True)
                
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
