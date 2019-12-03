import phue
import time
import Adafruit_IO
import toml
import csv
import threading
import queue

# Chromacity Color Conversion Dictionary declaration
cct_lookup = {}

# System configuration dictionary declaration
config = {}

# Queue declarations
event_queue = queue.SimpleQueue()


def connected(client):
    client.subscribe(config['adafruit_io']['feed_id'], config['adafruit_io']['username'])


def wake_up_sequence(interrupt):
    now = time.time()
    sequence_duration = config['wake_up_sequence']['duration'] * 60  # in seconds
    end_time = now + sequence_duration
    remaining_time = sequence_duration
    while (remaining_time > 0) & (not interrupt):
        remaining_time = (end_time - time.time())
        percent_complete = 100 - 100 * (remaining_time / sequence_duration)

        brightness = max(min(int(percent_complete / 100 * 254), 254), 0)
        low_temperature = config['wake_up_sequence']['starting_temperature']
        high_temperature = config['wake_up_sequence']['end_temperature']
        desired_temperature = low_temperature + (high_temperature - low_temperature) * percent_complete / 100
        rounded_temperature = min(cct_lookup, key=lambda x: abs(float(x) - desired_temperature))
        xy = cct_lookup[rounded_temperature]

        for light in lights:
            light.on = True
            light.brightness = brightness
            light.xy = xy
        time.sleep(1)

        '''
        Philips Hue bulbs can be changed from multiple sources (phone app, physical switches, etc.)
        It is reasonable to assume that the bulbs will response in the specified sleep duration.
        If, after time.sleep has expired, the current light state is NOT the commanded state, assume that an external
        source has modified bulb state, in which case this process should be terminated.
        '''
        for light in lights:
            if (not light.on) | (light.brightness != brightness) | (light.xy != xy):
                return


def message_received(client, feed_id, payload):
    event_queue.put(payload)


if __name__ == '__main__':
    print('Starting...')

    # Import configuration file
    config: dict = toml.load('config.toml')

    with open('CCT-lookup-table.txt', mode='r') as file:
        reader = csv.DictReader(file, delimiter='\t')
        x_bias = config['wake_up_sequence']['x_bias']
        y_bias = config['wake_up_sequence']['y_bias']
        for entry in reader:
            cct_lookup[entry['CCT']] = [float(entry['x (black body)']) + x_bias,
                                        float(entry['y (black body)']) + y_bias]

    # Connect to Adafruit IOT services and IFTTT feed
    adafruit_io = Adafruit_IO.Client(config['adafruit_io']['username'], config['adafruit_io']['key'])

    # Connect to Philips Hue bridge and get lights dictionary
    bridge = phue.Bridge(config['hue']['ip_address'])
    lights = bridge.get_light_objects()

    try:
        ifttt_feed = adafruit_io.feeds('ifttt')
    except Adafruit_IO.RequestError:
        feed = Adafruit_IO.Feed(name='ifttt')
        ifttt_feed = adafruit_io.create_feed(feed)

    adafruit_io_client = Adafruit_IO.MQTTClient(config['adafruit_io']['username'], config['adafruit_io']['key'])

    # Setup callback functions
    adafruit_io_client.on_connect = connected
    adafruit_io_client.on_message = message_received

    adafruit_io_client.connect()

    adafruit_io_client.loop_background()

    # Process incoming events and manage threads
    while True:
        event = event_queue.get()
        if event == 'wake up':
            wake_up_sequence_interrupt = False
            wake_up_sequence_thread = threading.Thread(target=wake_up_sequence,
                                                       args=(lambda: wake_up_sequence_interrupt, ))
            wake_up_sequence_thread.start()
        elif event == 'sleep':
            # Stop wakeup sequence if sleep is called
            if wake_up_sequence_thread.isAlive():
                wake_up_sequence_interrupt = True
                wake_up_sequence_thread.join()
            for light in lights:
                light.on = False
