# pi-cluster
A project to set up environments to practically learn kubernetes on a Raspberry Pi cluster. This tool aims to provide additional functionality to integrate with your cluster.

#### What does this package include?
This package includes a command line tool, `cluster`, which is responsible for executing ansible scripts for configuration management and setting up the cluster. I have also included this tool in the hopes that other distributed computing environments will be integrated, not just Kubernetes.

## Getting Started
First, flash your raspberry pi SD cards with Raspberry Pi OS (or similar) if you haven't already. Then, install the package  using `pip install pi-cluster`. This will give you access to the command line tool `cluster`.

Once installed, you can begin the setup:
1. Type `cluster init`. This will create a JSON file where you should enter your Raspberry Pi IP hostnames and usernames.
2. Type `cluster apply`.  This will apply the config and check to make sure it can SSH into each node.
3. Type `cluster create kubernetes`. This will manage installation and deploy some pods, including a private registry.

You can now interact with the cluster using `kubectl`. Happy learning!

## Switching Networks
`pi-cluster` also comes with functionality to make it easy to switch networks.

## Setting up for a Workshop
This involves creating namespaces for each user with RBAC.