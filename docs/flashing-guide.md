# Flashing your Raspberry Pis

`pi-cluster` finds your Pis automatically, as long as each one is flashed with
a consistent hostname, a known username, and the SSH public key that `cluster`
generates for you. This guide does that with
[Raspberry Pi Imager](https://www.raspberrypi.com/software/).

## 1. Get the public key

```bash
cluster init
```

On the first run this creates `~/.ssh/pi-cluster` (a key used only for the
cluster), prints the settings to flash with, and then looks for Pis — it won't
find any yet, which is fine. `cluster pubkey` prints the key again at any time.

## 2. Choose the OS

In Raspberry Pi Imager:

- **Device:** your Pi model.
- **Operating system:** Raspberry Pi OS Lite (64-bit). No desktop needed.
- **Storage:** the SD card (or SSD, if this Pi boots from one).

## 3. Apply the custom settings

Open **Edit settings** before writing. For **each** Pi:

| Setting | Value |
| --- | --- |
| Hostname | `pi-node-01` on the first Pi, `pi-node-02` on the second, … (two digits) |
| Username | `pi` (or whatever you pass to `cluster init --username`) |
| SSH | **Allow public-key authentication only**, and paste the key from step 1 |
| Wireless LAN | Only if this Pi uses Wi-Fi instead of the switch |

- The hostname prefix and username must match `cluster init` (defaults:
  `pi-node` and `pi`).
- `pi-node-01` becomes the **control-plane**; the rest become workers.
- If you have a data SSD, attach it to `pi-node-01` — that's the default
  storage node. It needs an ext4 partition at `/dev/sda1` (change either with
  `--storage-device` or in the config). No SSD? Use `cluster init --no-storage`.
- If a Pi **boots** from its SSD, `/dev/sda1` is its boot partition: point
  `storage.device` at a separate data partition, or use `--no-storage`.

## 4. Boot

1. Write each card and put it in the matching Pi.
2. Connect every Pi to the switch and power up.
3. Give them a minute or two.

## 5. Discover

```bash
cluster init            # again: finds the Pis and writes ~/.config/pi-cluster/config.json
cluster apply           # checks SSH to every node and runs base setup
```

Base setup enables memory cgroups, which needs one reboot — `cluster apply`
waits for the nodes to come back.

If discovery finds nothing, see
[Troubleshooting](../README.md#troubleshooting).
