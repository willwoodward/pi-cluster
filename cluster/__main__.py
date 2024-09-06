import sys
import subprocess
import json

def main():
    # cluster
    if len(sys.argv) == 1:
        print("Executed")

    # cluster init
    elif sys.argv[1] == "init": init()

    # cluster online
    elif sys.argv[1] == "online":
        # Check to see if the nodes in the cluster are online
        command = ["ansible-playbook", "-i", "inventory.ini", "scripts/check-cluster.yml"]
        subprocess.run(command)
    
    # cluster shutdown
    elif sys.argv[1] == "shutdown":
        # Shutdown the cluster
        command = ["ansible-playbook", "-i", "inventory.ini", "scripts/shutdown-cluster.yml"]
        subprocess.run(command)

def init():
    # Data to be written
    nodes = {
        "master": {
            "username": "",
            "hostname": ""
        },
        "workers": [
            {
                "username": "",
                "hostname": ""
            },
        ]
    }
    
    # Serializing json
    json_object = json.dumps(nodes, indent=4)
    
    with open("cluster-config.json", "w") as outfile:
        outfile.write(json_object)

if __name__ == "__main__":
    main()