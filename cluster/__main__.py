import sys
import subprocess

def main():
    # cluster
    if len(sys.argv) == 1:
        print("Executed")

    elif sys.argv[1] == "online":
        # Execute the command: ansible-playbook -i inventory.ini check-cluster.yml
        command = ["ansible-playbook", "-i", "inventory.ini", "scripts/check-cluster.yml"]
        subprocess.run(command)

if __name__ == "__main__":
    main()