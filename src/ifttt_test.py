import phue
import random
import time
import Adafruit_IO
import toml
import asyncio
import numpy
import csv
import math

# Import configuration file
config = toml.load('config.toml')

# Connect to Adafruit IOT services and IFTTT feed
adafruit_io = Adafruit_IO.Client(config['adafruit_io']['username'], config['adafruit_io']['key'])

cct_lookup = {}

try:
    ifttt_feed = adafruit_io.feeds('ifttt')
except Adafruit_IO.RequestError:
    feed = Adafruit_IO.Feed(name='ifttt')
    ifttt_feed = adafruit_io.create_feed(feed)

# Connect to Philips Hue bridge and get lights dictionary
bridge = phue.Bridge(config['hue']['ip_address'])
lights = bridge.get_light_objects()

def connected(client):
    client.subscribe(config['adafruit_io']['feed_id'], config['adafruit_io']['username'])

def wake_up_sequence():
    now = time.time()
    sequence_duration = config['wake_up_sequence']['duration'] * 60 # in seconds
    end_time = now + sequence_duration
    remaining_time = sequence_duration
    while remaining_time > 0:
        remaining_time = (end_time - time.time())
        percent_complete = 100 - 100*(remaining_time / sequence_duration)
        for light in lights:
            light.on = True
            light.brightness = max(min(int(percent_complete / 100 * 254), 254), 0)
            low_temperature = config['wake_up_sequence']['starting_temperature']
            high_temperature = config['wake_up_sequence']['end_temperature']
            desired_temperature = low_temperature + (high_temperature - low_temperature) * percent_complete/100
            rounded_temperature = min(cct_lookup, key=lambda x:abs(float(x) - desired_temperature))
            light.xy = cct_lookup[rounded_temperature]
        time.sleep(1)

def message_received(client, feed_id, payload):
    print('Received new value: {0}'.format(payload))
    if payload == 'wake up':
        wake_up_sequence()
    elif payload == 'sleep':
        for light in lights:
            light.on = False 

if __name__ == '__main__':    
    print('Starting...')
    
    with open ('CCT-lookup-table.txt', mode='r') as file:
        reader = csv.DictReader(file, delimiter='\t')
        x_bias = config['wake_up_sequence']['x_bias']
        y_bias = config['wake_up_sequence']['y_bias']
        for entry in reader:
            cct_lookup[entry['CCT']] = [float(entry['x (black body)']) + x_bias,
                                        float(entry['y (black body)']) + y_bias]

    adafruit_io_client = Adafruit_IO.MQTTClient(config['adafruit_io']['username'], config['adafruit_io']['key'])

    # Setup callback functions
    adafruit_io_client.on_connect = connected
    adafruit_io_client.on_message = message_received

    adafruit_io_client.connect()

    adafruit_io_client.loop_background()
    
    while True:
        time.sleep(100)
