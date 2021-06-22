#!/usr/bin/env python3
# vim: set autoindent filetype=python tabstop=4 shiftwidth=4 softtabstop=4 number textwidth=175 expandtab:
# vim: set fileencoding=utf-8

"""
This script is collecting information as being provided from the P1 port on an electical usage meter and is
based on code as made available by Ge Janssen, see:
   http://gejanssen.com/howto/Slimme-meter-uitlezen/index.html

"""

import argparse
import configparser
import datetime
import json
import jinja2
import logging
import os.path
import re
import socket
import struct
import sys
import time
import signal
import yaml
from pathlib import Path


__author__ = "Marcel"
__license__ = "MIT"
__email__ = "marcel@home"
__version__ = "2021-06.05"

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
    parser.add_argument("--test",
                        action='store_true',
                        help="test mode"
                        )
    parser.add_argument('--version',
                        action='version',
                        version=__version__
                        )

    arguments = parser.parse_args()

    return arguments

power_meter = None
def do_exit(sig, stack):
    global power_meter
    logging.info('Flushing data before exiting')
    power_meter.flush_data()
    power_meter.print_html()
    power_meter.print_csv()
    raise SystemExit('Exiting')


P1MESSAGE_RGX     = re.compile(r'(?P<key>\S+:\S+)\((?P<value>\S+)\)')
REALVALUE_RGX     = re.compile(r'(?P<value>\d+\.\d+)')
P1_ONE_VALUE_RGX  = re.compile(r'(?P<key>\d+\-\d+:\d+\.\d+\.\d+)\((?P<value>[^(]*?)\)$')
P1_TWO_VALUES_RGX = re.compile(r'(?P<key>\d+\-\d+:\d+\.\d+\.\d+)\((?P<value1>[^(]*?)\)\((?P<value2>[^(]*?)\)$')

P1_KEYS = ['1-3:0.2.8', '0-0:1.0.0', '0-0:96.1.1', '1-0:1.8.1', '1-0:1.8.2', '1-0:2.8.1', '1-0:2.8.2', '0-0:96.14.0', '1-0:1.7.0', '1-0:2.7.0', '0-0:96.7.21', '0-0:96.7.9',
'1-0:99.97.0', '1-0:32.32.0', '1-0:52.32.0', '1-0:72.32.0', '1-0:32.36.0', '1-0:52.36.0', '1-0:72.36.0', '0-0:96.13.0', '1-0:32.7.0', '1-0:52.7.0', '1-0:72.7.0', '1-0:31.7.0',
'1-0:51.7.0', '1-0:71.7.0', '1-0:21.7.0', '1-0:41.7.0', '1-0:61.7.0', '1-0:22.7.0', '1-0:42.7.0', '1-0:62.7.0', '0-1:24.1.0', '0-1:96.1.0', '0-1:24.2.1.A', '0-1:24.2.1.B']

P1_KEYS_TO_FRIENDLY_NAME = {
        '1-3:0.2.8': 'version',
        '0-0:1.0.0': 'timestamp',
        '0-0:96.1.1': 'equipment id',
        '1-0:1.8.1': 'elec. in, t1',
        '1-0:1.8.2': 'elec. in, t2',
        '1-0:2.8.1': 'elec. out, t1',
        '1-0:2.8.2': 'elec. out, t2',
        '0-0:96.14.0': 'tariff',
        '1-0:1.7.0': 'power in',
        '1-0:2.7.0': 'power out',
        '0-0:96.7.21': '# power failures',
        '0-0:96.7.9': '# long power failures',
        '1-0:99.97.0': 'failure timestamp - duration',
        '1-0:32.32.0': 'voltage sags L1',
        '1-0:52.32.0': 'voltage sags L2',
        '1-0:72.32.0': 'voltage sags L3',
        '1-0:32.36.0': 'voltage swells L1',
        '1-0:52.36.0': 'voltage swells L2',
        '1-0:72.36.0': 'voltage swells L3',
        '0-0:96.13.0': 'text message',
        '1-0:32.7.0': 'voltage L1',
        '1-0:52.7.0': 'voltage L2',
        '1-0:72.7.0': 'voltage L3',
        '1-0:31.7.0': 'current L1',
        '1-0:51.7.0': 'current L2',
        '1-0:71.7.0': 'current L3',
        '1-0:21.7.0': 'power in L1',
        '1-0:41.7.0': 'power in L2',
        '1-0:61.7.0': 'power in L3',
        '1-0:22.7.0': 'power out L1',
        '1-0:42.7.0': 'power out L2',
        '1-0:62.7.0': 'power out L3',
        '0-1:24.1.0': 'device type',
        '0-1:96.1.0': 'equipment ID',
        '0-1:24.2.1.A': 'Gas meting tijd',
        '0-1:24.2.1.B': 'Gas meting'
        }

CONFIG = None

# ##############################################################################
#===  CLASS  ===================================================================
#         NAME:  SlimmeMeter
#      PURPOSE:  Interface to P1 port of 'Slimme Meter'
#===============================================================================

class SlimmeMeter():

    """
      This class contains the logic to communicate with the serial port, fetch data,
      store data and generate reports.
    """
    def __init__(self, multicast_address, multicast_port):
        self.measurements = []
        self.lastten = []
        self.csvdata = []
        self.csvverbruik = []
        self.csvlevering = []
        self.csvfm =  0  # first moment
        self.multicast_address = multicast_address
        self.multicast_port = multicast_port
        self.who = None
        self.telegram_framenumber = 0

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((multicast_address, multicast_port))
        mreq = struct.pack('4sl', socket.inet_aton(multicast_address), socket.INADDR_ANY)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    def sorted_rows(self, rows):
        if len(rows) == 0:
            return
        sorted_row = []
        temp_row = []
        first_timestamp = rows[0][0]
        for row in rows:
            if (first_timestamp // 10) == (row[0] // 10):
                temp_row.append(row)
            else:
                sorted_row.append(temp_row)
                temp_row = [row]
                first_timestamp = row[0]
        return sorted_row

    def print_html(self):
        """
           Print out an html page with last period information.
        """
        html_report_filename = get_config_value(category='html_report', key='filename', config_type=str, default='/tmp/p1-lastm.html')
        lastminute_file = open(html_report_filename, 'w')
        lastminute_file.write(''' <html>
      <head>
         <title>Electriciteitsverbruik laatste metingen</title>
         <meta http-equiv="refresh" content="2" />
         <meta http-equiv="pragma" content="no-cache" />
         <meta http-equiv="cache-control" content="no-cache" />
         <meta http-equiv="content-type" content="text/html; charset=iso-8859-1" />
      </head>
      <body>
         <font size="4">
         <big>
      ''')
        header_line = '<tr bgcolor="#AAFFFF"><th bgcolor="#AAFFFF">time</th><th bgcolor="#FFAAAA">verbruik</th><th bgcolor="#AAFFAA">levering</th>'
        header_line = '<tr bgcolor="#AAFFFF"><th bgcolor="#AAFFFF">time</th>\n'
        for i in range(10):
            header_line += f' <th bgcolor="#FFAAAA">verbruik</th><th bgcolor="#AAFFAA">levering</th>\n'
        header_line += '</tr>\n'

        lastminute_file.write("<H1>Vermogensverbruik</H1>now: %s " % time.strftime("%Y%m%d", time.localtime()) )
        lastminute_file.write('<small><a href="lastm.html">refresh</a></small><br><br>\n')
        lastminute_file.write('<table>\n')
        lastminute_file.write(header_line)

        lastten = list(self.lastten)
        batched_lastten = self.sorted_rows(lastten)
        batched_lastten.reverse()
        lastten.reverse()

        first_epoch_time = lastten[0][0]
        html_line = ''
        for i in range(9 - (first_epoch_time % 10)):
            html_line += f' <td bgcolor="#FFAAAA">&nbsp;</td><td bgcolor="#AAFFAA">&nbsp;</td>\n'

        for lastten_batch in batched_lastten:
            first_epoch_time = lastten_batch[0][0]
            time_fmt = time.strftime("%H:%M:%S", time.localtime(first_epoch_time))
            lastminute_file.write(f' <tr>\n <td bgcolor="CCFFFF">{time_fmt}</td>\n')

            for epoch_time, power_watt, power_levering in lastten_batch:
                minute = int(time.strftime("%M", time.localtime(epoch_time)))

                time_fmt = time.strftime("%H:%M:%S", time.localtime(epoch_time))
                power = int(power_watt)
                power_levering = int(power_levering)
                lastminute_file.write(f' <td align="right" bgcolor="#FFAAAA">{power}</td><td align="right" bgcolor="#AAFFAA">{power_levering}</td>\n')

            lastminute_file.write(' </tr>\n')
            if epoch_time % 60 == 0:
                lastminute_file.write(header_line)

        lastminute_file.write('</big></table></font></body></html>')
        lastminute_file.close()

    def print_csv(self):
        """
           Print out an csv file with last period information.
        """

        if len(self.csvdata) < 3:
            logging.warning("Not enough data to write interval report (%s records)", len(self.csvdata))
            return

        csv_filename = get_config_value(category='p1_reader_interval', key='filename', config_type=str, default='/tmp/p1_reader_interval-PERIOD.csv')
        csv_filename = csv_filename.replace('PERIOD', time.strftime("%Y%m%d-%H%M%S", time.localtime()))
        csv_file  = open(csv_filename, 'w')

        csv2_filename = get_config_value(category='p1_reader_day', key='filename', config_type=str, default='/tmp/p1_reader_day-DAY.csv')
        csv2_filename = csv2_filename.replace('DAY', time.strftime("%Y%m%d", time.localtime()))
        csv_file2 = open(csv2_filename, 'a')

        # from self.csvverbruik determine average, min, max and median
        for epoch_time, power_watt, csvverbruiklist, power_watt_levering, csvleveringlist in self.csvdata:
            NI = 0
            minI = 999999
            maxI = 0
            sumI = 0
            NO = 0
            minO = 999999
            maxO = 0
            sumO = 0

            for e in csvverbruiklist:
                if e > maxI:
                    maxI = e
                if e < minI:
                    minI = e
                sumI += e
                NI   += 1
            avgI = sumI / NI

            for e in csvleveringlist:
                if e > maxO:
                    maxO = e
                if e < minO:
                    minO = e
                sumO += e
                NO   += 1
            avgO = sumO / NO

            message = "%s, %s, %4d, %4d, %4d,    %s, %4d, %4d, %4d" % (
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(epoch_time / 300 * 300 )),
                power_watt,          minI, avgI, maxI,
                power_watt_levering, minO, avgO, maxO )
            csv_file.write( "%s\n" % message)
            csv_file2.write("%s\n" % message)

        csv_file.close()
        csv_file2.close()
        self.csvdata     = []


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

    def read_datagram(self):
        """
           Read a datagram from the serial port. This looks like the following:

         datagram ISKRA AM550:
           /ISK5\2M550T-xxxx                                   #  header information

           1-3:0.2.8(50)                                       #  Version information for P1 output
           0-0:1.0.0(210608130046S)                            #  Date-time stamp of the P1 message, format YYMMDDhhmmssX
           0-0:96.1.1(xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx)      #  Equipment identifier
           1-0:1.8.1(000001.651*kWh)                           #  Meter Reading electricity delivered to client (Tariff 1) in 0,001 kWh
           1-0:1.8.2(000001.134*kWh)                           #  Meter Reading electricity delivered to client (Tariff 2) in 0,001 kWh
           1-0:2.8.1(000008.673*kWh)                           #  Meter Reading electricity delivered by client (Tariff 1) in 0,001 kWh
           1-0:2.8.2(000005.385*kWh)                           #  Meter Reading electricity delivered by client (Tariff 2) in 0,001 kWh
           0-0:96.14.0(0002)                                   #  Tariff indicator electricity. The tariff indicator can also be used to switch tariff dependent loads e.g boilers.
                                                               #  This is the responsibility of the P1 user
           1-0:1.7.0(00.000*kW)                                #  Actual electricity power delivered (+P) in 1 Watt resolution
           1-0:2.7.0(00.713*kW)                                #  Actual electricity power received (-P) in 1 Watt resolution
           0-0:96.7.21(00006)                                  #  Number of power failures in any phase
           0-0:96.7.9(00002)                                   #  Number of long power failures in any phase
           1-0:99.97.0()                                       #  Power Failure Event Log (long power failures). Unit: Timestamp (end of failure) – duration in seconds
           1-0:32.32.0(00000)                                  #  Number of voltage sags in phase L1
           1-0:52.32.0(00000)                                  #  Number of voltage sags in phase L2
           1-0:72.32.0(00000)                                  #  Number of voltage sags in phase L3
           1-0:32.36.0(00001)                                  #  Number of voltage swells in phase L1
           1-0:52.36.0(00001)                                  #  Number of voltage swells in phase L2
           1-0:72.36.0(00001)                                  #  Number of voltage swells in phase L3
           0-0:96.13.0()                                       #  Text message max 1024 characters.
           1-0:32.7.0(226.2*V)                                 #  Instantaneous voltage L1 in V resolution
           1-0:52.7.0(222.5*V)                                 #  Instantaneous voltage L2 in V resolution
           1-0:72.7.0(224.7*V)                                 #  Instantaneous voltage L3 in V resolution
           1-0:31.7.0(000*A)                                   #  Instantaneous current L1 in A resolution.
           1-0:51.7.0(001*A)                                   #  Instantaneous current L2 in A resolution.
           1-0:71.7.0(004*A)                                   #  Instantaneous current L3 in A resolution.
           1-0:21.7.0(00.000*kW)                               #  Instantaneous active power L1 (+P) in W resolution
           1-0:41.7.0(00.169*kW)                               #  Instantaneous active power L2 (+P) in W resolution
           1-0:61.7.0(00.000*kW)                               #  Instantaneous active power L3 (+P) in W resolution
           1-0:22.7.0(00.000*kW)                               #  Instantaneous active power L1 (-P) in W resolution
           1-0:42.7.0(00.000*kW)                               #  Instantaneous active power L2 (-P) in W resolution
           1-0:62.7.0(00.877*kW)                               #  Instantaneous active power L3 (-P) in W resolution
           0-1:24.1.0(003)                                     #  Device-Type
           0-1:96.1.0(xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx)      #  Equipment identifier (Gas)
           0-1:24.2.1(210608130002S)(00006.135*m3)             #  Last 5-minute value (temperature converted), gas delivered to client in m3, including decimal values and capture time
           !0281                                               #


           Used notation: OBIS (IEC 62056-61 Object Identification System)

           http://en.wikipedia.org/wiki/IEC_62056

           B : C.D.E * F
           where:
           + B: energy metering channel 1-6.
                Not indicated for a single self-metering channel when no external channels are defined.
           + C: identifies a physical instrumentation quantity, like the type of a source power and
                its direction. 0 identifes general purpose objects.
           + D: identifies a quantity processing algorithm, like time accumulation, maximum and
                cumulative maximum.
           + E: tariff rate 1...8, or 0 for total readings.
           + F: billing period 0-3, 0 (not indicated) for present billing period, 1 for the first previous
                (last) period, 2 for the second previous billing period, 3 for the third previous billing
                period.

        """

        #Initialize
        p1_line = ''
        data = dict()

        (buf, who) = self.sock.recvfrom(10240)
        try:
            data = json.loads(buf)
        except:
            logging.error(f"{now} ERROR decoding json message: {sys.exc_info()[0]}")
            logging.error(f'packet contents:\n{buf}')
            return None

        meta_info = data['meta']
        telegram = data['telegram']

        if self.who != who:
            logging.info('Multicast sender restarted, listening to %s now', who)
            self.who = who
            self.telegram_framenumber = meta_info['frame-number']

        if meta_info['frame-number'] != self.telegram_framenumber:
            delta = self.telegram_framenumber - meta_info['frame-number']
            logging.warning('Missed %s telegrams', delta)
            self.telegram_framenumber = meta_info['frame-number']

        self.telegram_framenumber += 1

        start_time = time.time()
        telegram_time = int(meta_info['frame-start-time'])

        #When it takes more than delta seconds to finish this loop, than please report this:
        if meta_info['frame-time-duration'] > 500:
            logging.warning("Took to much time (%s ms) to collect a datagram.", meta_info['frame-time-duration'])

        logging.debug('telegram %s', telegram)

        if not '1-0:2.7.0' in telegram:
            logging.debug("2.7.0. key NOT found")
            telegram['1-0:2.7.0'] = 0

        weekly_log_measurement_period = get_config_value(category='weekly_log', key='measurement_period', config_type=int, default=30)
        if telegram_time % weekly_log_measurement_period == 0:
            self.measurements.append([telegram_time, telegram['1-0:1.8.1'], telegram['1-0:1.8.2'], telegram['1-0:1.7.0'],
                                                     telegram['1-0:2.8.1'], telegram['1-0:2.8.2'], telegram['1-0:2.7.0']])

        if len(self.lastten) > 120:
            self.lastten = self.lastten[1:] + [[telegram_time, telegram['1-0:1.7.0'], telegram['1-0:2.7.0']]]
        else:
            self.lastten.append([telegram_time, telegram['1-0:1.7.0'], telegram['1-0:2.7.0']])

        self.csvverbruik.append(telegram['1-0:1.7.0'])
        self.csvlevering.append(telegram['1-0:2.7.0'])
        if (((telegram_time % 300) < 3) and (telegram_time - self.csvfm) > 10)  or  ((telegram_time - self.csvfm) > 300):
            totalO = telegram['1-0:1.8.1'] + telegram['1-0:1.8.2']
            totalI = telegram['1-0:2.8.1'] + telegram['1-0:2.8.2']
            self.csvdata.append([telegram_time, totalO, self.csvverbruik, totalI, self.csvlevering])
            self.csvfm       = telegram_time
            self.csvverbruik = []
            self.csvlevering = []

        return telegram

    def flush_data(self):
        """

        Flush data to data file. Later this needs to be done to rrd type file.

        """
        # '%4s-W%02d' %( datetime.datetime.now().strftime("%Y"), datetime.datetime.now().isocalendar()[1])
        data_filename = get_config_value(category='weekly_log', key='filename', config_type=str, default='/tmp/P1reader-YYYY-Www.log')
        data_filename = data_filename.replace('YYYY', datetime.datetime.now().strftime("%Y"))
        data_filename = data_filename.replace('ww', f'{datetime.datetime.now().isocalendar()[1]:02d}')
        data_file = open(data_filename, 'a')
        for measurement in self.measurements:
            data_file.write( "%d:%7.3f:%7.3f:%5.3f : %7.3f:%7.3f:%5.3f\n" % (
                measurement[0],
                measurement[1], measurement[2], measurement[3],
                measurement[4], measurement[5], measurement[6] ) )

        data_file.close()
        self.measurements = []

def write_to_csv_file(datagrams):
    csv_file = get_config_value(category='p1_reader_details', key='filename', config_type=str, default='/tmp/p1_reader_details-DAY.csv')
    csv_file = csv_file.replace('DAY', time.strftime("%Y%m%d"))
    csv_file = Path(csv_file)
    csv_file_exists = csv_file.is_file()
    delimeter = ';'
    with csv_file.open('a') as fp:
        if not csv_file_exists:
            fp.write('datum' + delimeter)
            fp.write(delimeter.join(P1_KEYS) + '\n')
            fp.write('datum' + delimeter)
            for element in P1_KEYS:
                fp.write(P1_KEYS_TO_FRIENDLY_NAME[element] + delimeter)
            fp.write('\n')

        for datagram_time, datagram in datagrams:
            logging.debug('datagram_time: %s', datagram_time)
            logging.debug('datagram     : %s', datagram)
            fp.write(time.strftime("%d-%m-%Y %H:%M:%S", time.localtime(datagram_time)) + delimeter)
            for element in P1_KEYS:
                value = ''
                if element in datagram:
                    value = datagram[element]
                fp.write(str(value) + delimeter)
            fp.write('\n')

def get_config_value(category, key, config_type=float, default=None):
    global CONFIG
    logging.debug('config: %s', CONFIG)
    if category not in CONFIG:
        logging.debug('Category %s not in config file, returning default %s', category, default)
        return default

    if key not in CONFIG[category]:
        logging.debug('Key %s not in category %s in config file, returning default %s', key, category, default)
        return default

    logging.debug('Returning value %s/%s=%s', category, key, config_type(CONFIG[category][key]))
    return config_type(CONFIG[category][key])


# ##############################################################################

def main():
    """
    Program to connect to serial P1 port and process data from this.
      PURPOSE:..main function; initialize data/functions, loop to read P1 data
    """

    global CONFIG
    global power_meter

    # Some initialization
    arguments = get_arguments()

    # Configure the logging
    numeric_level = getattr(logging, arguments.log.upper(), None)

    # create formatter
    formatter = logging.Formatter("%(asctime)s;%(levelname)s;%(message)s", "%Y-%m-%d %H:%M:%S")
    logging.basicConfig(format='%(asctime)s [%(levelname)s] [%(funcName)s]   %(message)s',
                        datefmt="%Y%m%d-%H%M%S", level=numeric_level, stream=sys.stdout)

    logging.info("Running version: %s", __version__)
    logging.debug("Arguments: %s", arguments)

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

    multicast_address = get_config_value(category='multicast', key='address', config_type=str)
    multicast_port = get_config_value(category='multicast', key='port', config_type=int)
    power_meter = SlimmeMeter(multicast_address=multicast_address, multicast_port=multicast_port)

    signal.signal(signal.SIGINT,  do_exit)
    signal.signal(signal.SIGUSR1, do_exit)

    count_datagrams = 0
    datagrams = []

    p1_reader_details_flushtime = time.time()
    p1_reader_details_flushperiod = get_config_value(category='p1_reader_details', key='flush_period', config_type=int, default=300)

    p1_reader_interval_flushtime = time.time()
    p1_reader_interval_flushperiod = get_config_value(category='p1_reader_interval', key='flush_period', config_type=int, default=1800)

    p1_reader_day_flushtime = time.time()
    p1_reader_day_flushperiod = get_config_value(category='p1_reader_day', key='flush_period', config_type=int, default=7200)

    html_report_flushtime = time.time()
    html_report_flushperiod = get_config_value(category='html_report', key='flush_period', config_type=int, default=30)

    weekly_log_flushtime = time.time()
    weekly_log_flushperiod = get_config_value(category='weekly_log', key='flush_period', config_type=int, default=30)

    try:
        while True:
            count_datagrams += 1
            now = int(time.time())

            datagram = power_meter.read_datagram()
            datagrams.append([time.time(), datagram])

            if (now % p1_reader_details_flushperiod) < 5  and  (now - p1_reader_details_flushtime) > 0.25 * p1_reader_details_flushperiod:
                logging.info('writing to p1_reader_details file')
                write_to_csv_file(datagrams)
                datagrams = []
                p1_reader_details_flushtime = now

            if (now % html_report_flushperiod) < 2  and  (now - html_report_flushtime) > 0.25 * html_report_flushperiod:
                power_meter.print_html()
                html_report_flushtime = now

            if (now % weekly_log_flushperiod) < 5  and  (now - weekly_log_flushtime) > 0.25 * weekly_log_flushperiod:
                logging.info('writing to weekly_log file')
                power_meter.flush_data()
                weekly_log_flushtime = now

            if (now % p1_reader_interval_flushperiod) < 5  and  (now - p1_reader_interval_flushtime) > 0.25 * p1_reader_interval_flushperiod:
                logging.info('writing to p1_reader_interval file')
                power_meter.print_csv()
                p1_reader_interval_flushtime = now

            if arguments.test  and  count_datagrams > 5:
                logging.info('End of test')
                sys.exit(0)

    except KeyboardInterrupt:
        logging.info("Interrupted, saving remaining data and than quit")
        power_meter.flush_data()
        power_meter.print_html()
        power_meter.print_csv()

        sys.exit(1)

#---------------------------------------------------------------------------
#  Main part here
#---------------------------------------------------------------------------
if __name__ == "__main__":
    main()

else:
    # Test several functions
    pass

