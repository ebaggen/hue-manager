import phue
import random
import time
import Adafruit_IO
import toml

# Import configuration file
config = toml.load('config.toml')

# Connect to Adafruit IOT services and IFTTT feed
adafruit_io = Adafruit_IO.Client(config['adafruit_io']['username'], config['adafruit_io']['key'])
try:
    ifttt_feed = adafruit_io.feeds('ifttt')
except Adafruit_IO.RequestError:
    feed = Adafruit_IO.Feed(name='ifttt')
    ifttt_feed = adafruit_io.create_feed(feed)

# Connect to Philips Hue bridge and get lights dictionary
bridge = phue.Bridge(config['hue']['ip_address'])
lights = bridge.get_light_objects()

def connected(client):
    print('Connected to Adafruit IO.')
    client.subscribe(config['adafruit_io']['feed_id'], config['adafruit_io']['username'])

def disconnected(client):
    print('Disconnected from Adafruit IO')


def message_received(client, feed_id, payload):
    print('Received new value: {0}'.format(payload))
    if payload == 'wake up':
        for light in lights:
            light.on = True
            light.brightness = 254
            light.xy = [random.random(), random.random()]
      
    elif payload == 'sleep':
        for light in lights:
            light.on = False 
    

print('Starting...')

adafruit_io_client = Adafruit_IO.MQTTClient(config['adafruit_io']['username'], config['adafruit_io']['key'])

# Setup callback functions
adafruit_io_client.on_connect = connected
adafruit_io_client.on_disconnect = disconnected
adafruit_io_client.on_message = message_received

adafruit_io_client.connect()

adafruit_io_client.loop_background()

while True:
  try:
      time.sleep(100)

  except KeyboardInterrupt:
    print('Quitting')
    break
