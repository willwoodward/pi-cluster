# Control Neo Trinkey (https://www.adafruit.com/product/4870)
# Neopixel LEDS over a serial interface.
# Set color and brightness (intensity) of each LED.
# Copy serial_control.py to the Neo Trinkey as code.py
#
# Serial commands are of the form: leds:color:intensity
#   leds - integers 1-4 to select the LEDs to change.
#   color - abbreviation of color to set, see COLOR_MAP
#   intensity - integer 0-10 to set the brightness (0 - 100% in steps of 10%)
#
# Multiple commands can be sent at once, separated by commas.
# color or intensity can be blank and the value won't be changed.
#
# Examples:
#   "1:r,8" - Set LED 1 to red, with intensity at 80%.
#   "24::1" - Set the inensity of LEDs 2 and 4 to 10%, leave color unchanged.
#   "1:r::,2:g::,3:b::,4:blk" - Set LEDs 1, 2, and 3 to red, green, and blue. Turn LED 4 off.
#

import neopixel
import board
import supervisor

NUM_PIXELS = 4
DEFAULT_INTENSITY = 0.5

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
        board.NEOPIXEL, NUM_PIXELS, brightness=0.2, auto_write=False, pixel_order=neopixel.GRB)

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

        pixels[led] = colors[led]


def main():
    while True:
        data = serial_read()
        if data is None:
            continue

        commands = parse_commands(data)

        if not commands:
            continue

        for command in commands:
            leds, clr, intensity = command
            set_pixels(leds, clr, intensity)

        pixels.show()


if __name__ == '__main__':
    main()