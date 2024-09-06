import sys
import subprocess

def main():
    # cluster
    if len(sys.argv) == 1:
        print("Executed")

    # cluster init
    elif sys.argv[1] == "init":
        pass

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

if __name__ == "__main__":
    main()