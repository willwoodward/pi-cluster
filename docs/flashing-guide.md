# Flashing your Raspberry Pi SD cards / SSDs

`pi-cluster` discovers your Pis automatically, but only if each one is flashed
with a consistent hostname, a known username, and the SSH public key that
`cluster init` generates for you. This guide walks through that with
[Raspberry Pi Imager](https://www.raspberrypi.com/software/).

Do this once per Pi (and once for the SSD, if you boot from it).

## 1. Generate the SSH key first

Run this before flashing so you have a public key to paste into Imager:

```bash
cluster init
```

It creates `~/.ssh/pi-cluster` / `~/.ssh/pi-cluster.pub` and prints the public
key. Copy that public key — you'll paste it into Imager in step 3.

If you only want the key and the settings (no discovery yet), you can stop after
this and come back to `cluster init` once the Pis are flashed and booted.

## 2. Choose the OS

In Raspberry Pi Imager:

- **Device:** your Pi model.
- **Operating System:** Raspberry Pi OS Lite (64-bit) is plenty — no desktop needed.
- **Storage:** the SD card or SSD for this node.

## 3. Apply the custom settings (the important part)

Click the gear / **Edit Settings** before writing. For **each** node, set:

| Setting | Value |
| --- | --- |
| Hostname | `pi-node-01` on the first Pi, `pi-node-02` on the second, and so on (zero-padded, incrementing) |
| Username | `pi` (or whatever you pass to `cluster init --username`) |
| Enable SSH | **Allow public-key authentication only**, and paste the public key from step 1 |
| Wireless LAN | optional — only if a node uses Wi-Fi instead of the PoE switch |

Notes:

- The hostname prefix (`pi-node`) and username must match what you give
  `cluster init`. The defaults are `pi-node` and `pi`.
- Number the Pis in the order you want them. `pi-node-01` becomes the
  **control-plane** node; the rest become workers.
- Attach the **1 TB SSD to `pi-node-01`** (the control-plane), which is the
  default storage node exported over NFS for the registry. To use a different
  node, edit `cluster-config.json` after `init`.

## 4. Write, boot, and wire up

1. Write each card/SSD and insert it into the matching Pi.
2. Connect every Pi to the PoE switch and power the switch on.
3. Give them a minute to boot and appear on the network.

## 5. Discover

Back on your machine:

```bash
cluster init      # discovers the Pis, writes cluster-config.json + inventory.ini
cluster apply     # verifies SSH into every node and runs base setup
```

If discovery finds nothing, see the troubleshooting notes in the main
[README](../README.md#troubleshooting).
