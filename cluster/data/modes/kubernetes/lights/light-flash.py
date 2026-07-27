import argparse
import subprocess
import time

def ssh_flash_white(ip_address, username, key_path, remote_script_path):
    try:
        # SSH command to set color to white
        ssh_command_white = [
            "ssh",
            "-i", key_path,
            f"{username}@{ip_address}",
            f"python3 {remote_script_path} white"
        ]
        
        # SSH command to set color to black
        ssh_command_black = [
            "ssh",
            "-i", key_path,
            f"{username}@{ip_address}",
            f"python3 {remote_script_path} black"
        ]
        
        # Set the color to white on the remote host
        subprocess.run(ssh_command_white, check=True)
        
        time.sleep(1)
        
        # Set the color to black on the remote host
        subprocess.run(ssh_command_black, check=True)
        
        print("Flashed white for 1 seconds on the remote host.")
        
    except subprocess.CalledProcessError as e:
        print(f"An error occurred while running the SSH command: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Flash a node's LED white for one second over SSH.")
    parser.add_argument("ip_address", help="node IP address or .local hostname")
    parser.add_argument("--username", default="pi", help="SSH username")
    parser.add_argument("--key-path", default="~/.ssh/pi-cluster", help="SSH private key path")
    parser.add_argument(
        "--remote-script-path",
        default="/home/pi/Documents/light/serial_control_host.py",
        help="path to serial_control_host.py on the node",
    )
    args = parser.parse_args()

    ssh_flash_white(args.ip_address, args.username, args.key_path, args.remote_script_path)
