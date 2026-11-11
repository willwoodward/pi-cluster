# Neo Trinkey firmware (https://www.adafruit.com/product/4870) for pi-cluster.
# Copy this onto the Trinkey's CIRCUITPY drive as code.py; `cluster-led` on the
# node then drives the four NeoPixels over USB serial.
#
# Each serial line holds one or more commands separated by commas:
#   leds:colour:intensity
#     leds       - LED numbers 1-4, e.g. "13" for LEDs 1 and 3
#     colour     - a name from COLOR_MAP, or blank to leave it unchanged
#     intensity  - 0-10 (0-100% in steps of 10%), or blank to leave it unchanged
#
# Examples:
#   "1:red:8"                        LED 1 red at 80%
#   "24::1"                          LEDs 2 and 4 at 10%, colour unchanged
#   "1:red:,2:green:,3:blue:,4:black:"  LEDs 1-3 red/green/blue, LED 4 off

import neopixel
import board
import supervisor

NUM_PIXELS = 4
DEFAULT_INTENSITY = 0.3

COLOR_MAP = {
    'red':     'ff0000',
    'yellow':  'ffff00',
    'orange':  'ffaa00',
    'green':   '00ff00',
    'teal':    'afeeee',
    'cyan':    '00a6d6',
    'blue':    '0000ff',
    'purple':  '5a005a',
    'magenta': 'ff00ff',
    'white':   'ffffff',
    'black':   '000000',
    'off':     '000000',
    'gold':    'e7bd42',
    'pink':    'ffb6c1',
    'aqua':    '00ffff',
    'jade':    'ffd8ab',
    'amber':   'ffd8ab',
    'oldlace': 'fdf5e6',
}

def rgb(colour):
    colour = COLOR_MAP[colour]
    return int(colour[0:2], 16), int(colour[2:4], 16), int(colour[4:6], 16)


pixels = neopixel.NeoPixel(
        board.NEOPIXEL, NUM_PIXELS, brightness=1.0, auto_write=False, pixel_order=neopixel.GRB)

pixels.fill(rgb('black'))
pixels.show()

colors = [rgb('black')] * NUM_PIXELS
intensities = [DEFAULT_INTENSITY] * NUM_PIXELS

def serial_read():
    if supervisor.runtime.serial_bytes_available:
        return input()

    return None


def parse_commands(data):
    commands = []
    raw_commands = data.split(',')
    for raw_command in raw_commands:
        commands.append(parse_command(raw_command))

    return commands


def parse_command(command):
    try:
        leds, clr, intensity = command.split(':')
        leds = [int(x) - 1 for x in leds]
        for led in leds:
            if led >= NUM_PIXELS:
                return None

        if clr == '':
            clr = None
        elif clr not in COLOR_MAP.keys():
            return None
        else:
            clr = rgb(clr)

        if intensity == '':
            intensity = None
        else:
            intensity = int(intensity)
            if intensity < 0 or intensity > 10:
                return None

            intensity /= 10

    except ValueError:
        return None

    return (leds, clr, intensity)


def set_pixels(leds, clr, intensity):
    for led in leds:

        if clr is not None:
            colors[led] = clr

        if intensity is not None:
            intensities[led] = intensity

        pixels[led] = tuple(int(c * intensities[led]) for c in colors[led])


def main():
    while True:
        data = serial_read()
        if data is None:
            continue

        commands = parse_commands(data)

        if not commands:
            continue

        for command in commands:
            if command is None:
                continue
            leds, clr, intensity = command
            set_pixels(leds, clr, intensity)

        pixels.show()


if __name__ == '__main__':
    main()