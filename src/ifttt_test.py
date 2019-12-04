import phue
import time
import Adafruit_IO
import toml
import csv
import threading
import queue
from enum import Enum
import logging

# Chromacity Color Conversion Dictionary declaration
cct_lookup = {}

# System configuration dictionary declaration
config = {}

# Queue declarations
event_queue = queue.SimpleQueue()


class WakeUpSequenceActions(Enum):
    START = 1
    STOP = 2
    TERMINATE = 3


class WakeUpSequence(object):
    def __init__(self):
        self._action_queue = queue.SimpleQueue()

        self._thread = threading.Thread(target=self.__sequence, args=())
        self._thread.daemon = True
        self._thread.start()

    def start(self):
        self._action_queue.put(WakeUpSequenceActions.START)

    def stop(self):
        self._action_queue.put(WakeUpSequenceActions.STOP)

    def terminate(self):
        self._action_queue.put(WakeUpSequenceActions.TERMINATE)
        self._thread.join()

    def __sequence(self):
        # Initialize as inactive
        sequence_active = False

        # Non-blocking Wake Up Sequence Thread Loop
        while True:

            # Dequeue any incoming actions
            if not self._action_queue.empty():
                action = self._action_queue.get_nowait()

                # Handle any action. If action is none, then continue
                if action == WakeUpSequenceActions.START:
                    sequence_active = True
                    now = time.time()
                    sequence_duration = config['wake_up_sequence']['duration'] * 60  # in seconds
                    end_time = now + sequence_duration
                elif action == WakeUpSequenceActions.STOP:
                    sequence_active = False
                elif action == WakeUpSequenceActions.TERMINATE:
                    return

            # Sequence logic. While in the running state, complete the sequence
            if sequence_active:
                remaining_time = (end_time - time.time())
                percent_complete = 100 * (1 - (remaining_time / sequence_duration))

                brightness = max(min(int(percent_complete / 100 * 254), 254), 1)
                low_temperature = config['wake_up_sequence']['starting_temperature']
                high_temperature = config['wake_up_sequence']['end_temperature']
                desired_temperature = low_temperature + (high_temperature - low_temperature) * percent_complete / 100
                rounded_temperature = min(cct_lookup, key=lambda x: abs(float(x) - desired_temperature))
                xy = [round(element, 2) for element in cct_lookup[rounded_temperature]]

                for light in lights:
                    light.on = True
                    light.brightness = brightness
                    light.xy = xy
                time.sleep(3)

                '''
                Philips Hue bulbs can be changed from multiple sources (phone app, physical switches, etc.)
                It is reasonable to assume that the bulbs will response in the specified sleep duration.
                If, after time.sleep has expired, the current light state is NOT the commanded state, assume that an external
                source has modified bulb state, in which case this process should be terminated.
                '''
                xy_min = [e - config['hue']['xy_noise_detection_sensitivity'] for e in xy]
                xy_max = [e + config['hue']['xy_noise_detection_sensitivity'] for e in xy]
                state_changed = not all([light.on for light in lights])
                brightness_changed = not all([light.brightness == brightness for light in lights])
                xy_changed = not all([(xy_min < light.xy < xy_max) for light in lights])
                external_override = state_changed | brightness_changed | xy_changed
                if external_override:
                    logging.info('External control of lights detected. Stopping sequence.')

                # End conditions
                if (remaining_time <= 0) | external_override:
                    sequence_active = False
            else:
                time.sleep(1)


def connected(client):
    logging.info('Connected to Adafruit IO')
    client.subscribe(config['adafruit_io']['feed_id'], config['adafruit_io']['username'])


def message_received(client, feed_id, payload):
    logging.info('Received from Adafruit IO: {0}'.format(payload))
    event_queue.put(payload)


if __name__ == '__main__':
    # Setup logging
    logging.basicConfig(filename='hue-manager.log',
                        format='%(asctime)s %(levelname)s %(message)s',
                        datefmt='%m/%d/%Y %I:%M:%S',
                        level=logging.INFO)

    logging.info('Application starting.')

    # Import configuration file
    config: dict = toml.load('config.toml')
    logging.info('Configuration file loaded.')

    # Load chromacity file
    with open('CCT-lookup-table.txt', mode='r') as file:
        reader = csv.DictReader(file, delimiter='\t')
        x_bias = config['wake_up_sequence']['x_bias']
        y_bias = config['wake_up_sequence']['y_bias']
        for entry in reader:
            cct_lookup[entry['CCT']] = [float(entry['x (black body)']) + x_bias,
                                        float(entry['y (black body)']) + y_bias]

    logging.info('Chromacity conversion file loaded.')
    # Connect to Adafruit IOT services and IFTTT feed
    adafruit_io = Adafruit_IO.Client(config['adafruit_io']['username'], config['adafruit_io']['key'])

    # Connect to Philips Hue bridge and get lights dictionary
    bridge = phue.Bridge(config['hue']['ip_address'])
    lights = bridge.get_light_objects()
    logging.info('Connected to Philips Hue.')

    try:
        ifttt_feed = adafruit_io.feeds(config['adafruit_io']['feed_id'])
    except Adafruit_IO.RequestError:
        feed = Adafruit_IO.Feed(name=config['adafruit_io']['feed_id'])
        ifttt_feed = adafruit_io.create_feed(feed)

    adafruit_io_client = Adafruit_IO.MQTTClient(config['adafruit_io']['username'], config['adafruit_io']['key'])

    # Setup callback functions
    adafruit_io_client.on_connect = connected
    adafruit_io_client.on_message = message_received

    adafruit_io_client.connect()

    adafruit_io_client.loop_background()

    wake_up_sequence = WakeUpSequence()

    # Process incoming events and manage threads
    while True:
        try:
            event = event_queue.get()
            if event == 'wake up':
                wake_up_sequence.start()
            elif event == 'sleep':
                # Stop wakeup sequence if sleep is called
                wake_up_sequence.stop()
                for light in lights:
                    light.on = False
        except KeyboardInterrupt:
            logging.info('Application closing.')
            wake_up_sequence.terminate()
            exit()
