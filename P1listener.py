#!/usr/bin/env python3
# vim: set autoindent filetype=python tabstop=4 shiftwidth=4 softtabstop=4 number textwidth=175 expandtab:
# vim: set fileencoding=utf-8

import argparse
import datetime
import jinja2
import json
import logging
import os.path
import socket
import re
import sys
import time
import serial
import signal
import yaml

__author__ = "Marcel"
__license__ = "MIT"
__email__ = "marcel@home"
__version__ = "2021-06.03"

def get_arguments():
    """
    get commandline arguments
    """
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="P1 reader interface")

    parser.add_argument("--config-file",
                        default=__file__.replace('.py', '.yml').replace('/bin/', '/etc/'),
                        help="P1 config file, default %(default)s",
                        metavar='FILE'
                        )
    parser.add_argument("--log",
                        help="Set log level (default info)",
                        choices=['debug', 'info', 'warning', 'error', 'critical'],
                        default="info"
                        )
    parser.add_argument("--debug",
                        action='store_true',
                        help="debug mode"
                        )
    parser.add_argument('--version',
                        action='version',
                        version=__version__
                        )

    arguments = parser.parse_args()

    return arguments

P1_ONE_VALUE_RGX  = re.compile(r'(?P<key>\d+\-\d+:\d+\.\d+\.\d+)\((?P<value>[^(]*?)\)$')
P1_TWO_VALUES_RGX = re.compile(r'(?P<key>\d+\-\d+:\d+\.\d+\.\d+)\((?P<value1>[^(]*?)\)\((?P<value2>[^(]*?)\)$')


def do_exit(sig, stack):
    raise SystemExit('Exiting')
    power_meter.close_port(ser)

# ##############################################################################
#===  CLASS  ===================================================================
#         NAME:  SlimmeMeter
#      PURPOSE:  Interface to P1 port of 'Slimme Meter'
#===============================================================================

CONFIG = None

class SlimmeMeter():

    """
      This class contains the logic to communicate with the serial port, fetch data,
      store data and generate reports.
    """
    def __init__(self, ser):
        self.ser     = ser
        ser.bytesize = serial.EIGHTBITS
        ser.parity   = serial.PARITY_NONE
        ser.stopbits = serial.STOPBITS_ONE
        ser.xonxoff  =  0
        ser.rtscts   =  0
        ser.timeout  =  3

    def open_port(self, ser, baudrate=115200, port="/dev/ttyUSB0"):
        """
            Opens the serial port using ttyUSB0 (USB <-> Serial)
        """
        #Set COM port config
        ser.baudrate = baudrate
        ser.port     = port

        #Open COM port
        try:
            ser.open()
        except serial.SerialException:
            sys.exit ("Fout bij het openen van %s. Aaaaarch."  % ser.port)

        logging.info("Poort %s geopend" % ser.port)

    def close_port(self, ser):
        """
           Close the serial connection.
        """
        try:
            ser.close()
        except serial.SerialException:
            sys.exit ("Oops %s. Programma closed. Could not close the serial port." % ser.name )

    def parse_p1_value(self, value):
        logging.debug('Original value: %s', value)
        if '*m3' in value:
            value = int(1000 * float(value.split('*')[0]))
        elif '*kW' in value:
            value = int(1000 * float(value.split('*')[0]))
        elif '*V' in value:
            value = float(value.split('*')[0])
        elif '*A' in value:
            value = int(value.split('*')[0])
        logging.debug('  converted to: %s', value)
        return value


    def read_line(self, ser):
        result = None
        while result is None:
            try:
                # Read a line van de seriele poort
                result = ser.readline()
            except:
                logging.error("Seriele poort %s kan niet gelezen worden. Aaaaaaaaarch." % ser.name )
                time.sleep(10)
                pass
        return result.decode('UTF-8').strip()

    def read_datagram(self, ser, first_line='/ISK5\\2M550T-1013'):

        data = dict()
        data['meta'] = {}
        data['telegram'] = {}
        first_line_read = False

        multicast_address = get_config_value(category='multicast', key='address', config_type=str)
        multicast_port = get_config_value(category='multicast', key='port', config_type=int)
        multicast_TTL = get_config_value(category='multicast', key='TTL', config_type=int)

        logging.info('Multicast address: %s', multicast_address)
        logging.info('Multicast port   : %s', multicast_port)
        logging.info('Multicast TTL    : %s', multicast_TTL)

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, multicast_TTL)

        datagram_counter = 0

        while True:
            line = self.read_line(ser)
            if not first_line_read and line.startswith('/'):
                datagram_counter += 1
                logging.debug('First line found')
                data['telegram']['header'] = line
                data['meta']['frame-start-time'] = time.time()
                data['meta']['frame-number'] = datagram_counter
                first_line_read = True
                continue
            elif not first_line_read:
                logging.warning('Unexpected line: %s', line)
                continue
            elif line.startswith('!') and len(line) == 5:
                logging.debug('End line found')
                data['telegram']['checksum'] = line[1:]
                data['meta']['frame-end-time'] = time.time()
                duration = int(1000 * (data['meta']['frame-end-time'] - data['meta']['frame-start-time']))
                data['meta']['frame-time-duration'] = duration
                message = json.dumps(data, indent=0)
                sock.sendto(message.encode(), (multicast_address, multicast_port))

                first_line_read = False
                data = dict()
                data['meta'] = {}
                data['telegram'] = {}
                continue

            p1_one_value_match = P1_ONE_VALUE_RGX.search(line)
            if p1_one_value_match:
                key = p1_one_value_match.group('key')
                value = self.parse_p1_value(p1_one_value_match.group('value'))
                data['telegram'][key] = value
                logging.debug('Found 1 value match: key=%s  value=%s', key, value)
                continue

            p1_two_values_match = P1_TWO_VALUES_RGX.search(line)
            if p1_two_values_match:
                key = p1_two_values_match.group('key')
                value1 = self.parse_p1_value(p1_two_values_match.group('value1'))
                value2 = self.parse_p1_value(p1_two_values_match.group('value2'))
                data['telegram'][f'{key}.A'] = value1
                data['telegram'][f'{key}.B'] = value2
                logging.debug('Found 2 values match: key=%s  value1=%s   value2=%s', key, value1, value2)
                continue


def get_config_value(category, key, config_type=float, default=None):
    global CONFIG
    logging.debug('config: %s', CONFIG)
    if category not in CONFIG:
        logging.warning('Category %s not in config file, returning default %s', category, default)
        return default

    if key not in CONFIG[category]:
        logging.warning('Key %s not in category %s in config file, returning default %s', key, category, default)
        return default

    logging.debug('Returning value %s/%s=%s', category, key, config_type(CONFIG[category][key]))
    return config_type(CONFIG[category][key])


# ##############################################################################

def main():

    global CONFIG

    # Some initialization
    arguments = get_arguments()

    # Configure the logging
    numeric_level = getattr(logging, arguments.log.upper(), None)

    # create formatter
    formatter = logging.Formatter("%(asctime)s;%(levelname)s;%(message)s", "%Y-%m-%d %H:%M:%S")
    logging.basicConfig(format='%(asctime)s [%(levelname)s] [%(funcName)s]   %(message)s',
                        datefmt="%Y%m%d-%H%M%S", level=numeric_level, stream=sys.stdout)

    logging.info("Running version: %s", __version__)
    logging.info("Arguments: %s", arguments)

    script_name = os.path.basename(__file__)

    if not os.path.exists(arguments.config_file):
        logging.error('ERROR: cannot find config file %s, quitting ....' % arguments.config_file)
        sys.exit('ERROR: cannot find config file %s, quitting ....' % arguments.config_file)

    logging.info("loading config from '%s'", arguments.config_file)

    path_matcher = re.compile(r'.*\$\{([^}^{]+)\}')
    def path_constructor(loader, node):
        ''' Extract the matched value, expand env variable, and replace the match '''
        value = node.value
        matches = re.findall(r'\$\{\w+?\}', value)
        logging.debug('before value=%s', value)
        for match in matches:
            environment_variable = (match[2:])[:-1]
            environment_value = os.environ.get(environment_variable, environment_variable)
            value = value.replace(match, environment_value)
        logging.debug('after value=%s', value)
        return value

    yaml.add_implicit_resolver('!path', path_matcher)
    yaml.add_constructor('!path', path_constructor)

    with open(arguments.config_file) as inf:
        CONFIG = inf.read()
        CONFIG = jinja2.Template(CONFIG).render()
        CONFIG = yaml.load(CONFIG, Loader=yaml.FullLoader)

    logging.info('config:\n%s', CONFIG)

    ser  = serial.Serial()
    power_meter = SlimmeMeter(ser)
    power_meter.open_port(ser)

    signal.signal(signal.SIGINT,  do_exit)
    signal.signal(signal.SIGUSR1, do_exit)

    try:
        datagram = power_meter.read_datagram(ser)

    except KeyboardInterrupt:
        print("Interrupted, quit")
        power_meter.close_port(ser)
        sys.exit(1)

#---------------------------------------------------------------------------
#  Main part here
#---------------------------------------------------------------------------
if __name__ == "__main__":
    main()

else:
    # Test several functions
    pass

