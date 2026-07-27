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
    # Example usage
    ip_address = "192.168.2.209"         # Remote host IP address
    username = "pi"           # Your SSH username
    key_path = "~/.ssh/id_rsa"  # Path to your SSH private key
    remote_script_path = "/home/pi/Documents/light/serial_control_host.py"  # Path to the script on the remote host

    ssh_flash_white(ip_address, username, key_path, remote_script_path)
