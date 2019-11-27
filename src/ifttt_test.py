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

def acknowledge_adafruit_event():
    # Acknowledge event by resetting it
    adafruit_io.send(ifttt_feed.key, 0)

print('Starting...')
while True:
  try:
    data = adafruit_io.receive(ifttt_feed.key)
    if data.value == 'wakeup':
      acknowledge_adafruit_event()
      for light in lights:
        light.on = True
        light.brightness = 254
        light.xy = [random.random(), random.random()]
      
    elif data.value == 'sleep':
        acknowledge_adafruit_event()
        for light in lights:
            light.on = False 
    
    # Sleep to reduce overload on Adafruit IO service
    time.sleep(0.5)

  except KeyboardInterrupt:
    print('Quitting')
    break
