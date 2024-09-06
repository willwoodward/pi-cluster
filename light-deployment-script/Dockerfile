# Use an appropriate base image
FROM python:3.9-slim

# Copy the Python script into the container
COPY print-ip.py /usr/local/bin/print-ip.py

# Make the script executable
RUN chmod +x /usr/local/bin/print-ip.py

# Set the entrypoint to the script
ENTRYPOINT ["/usr/local/bin/print-ip.py"]
