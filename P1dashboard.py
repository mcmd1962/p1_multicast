"""
Demonstrates a Rich "application" using the Layout and Live classes.

"""

import datetime

from rich import box
from rich.align import Align
from rich.console import Console, RenderGroup
from rich.layout import Layout
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.live import Live
import json
import time
import socket
import struct

console = Console()

def make_layout() -> Layout:
    """Define the layout."""
    layout = Layout(name="root")

    layout.split(
        Layout(name="header", size=3),
        Layout(name="meta_information", size=11),
        Layout(name="electriciteit", size=21),
        Layout(name="quality information"),
    )
    layout["meta_information"].split_row(
        Layout(name="telegram"),
        Layout(name="meta"),
    )
    layout["electriciteit"].split_row(
        Layout(name="electriciteit links"),
        Layout(name="electriciteit rechts"),
    )
    layout["electriciteit links"].split(Layout(name="power information"), Layout(name="cummulative information"))
    layout["electriciteit rechts"].split(Layout(name="phase information"), Layout(name="gas"))
    return layout


def make_meta_message(meta_info) -> Panel:
    frame_start_time = datetime.datetime.fromtimestamp(meta_info['frame-start-time']).strftime('%H:%M:%S.%f')[:-3]
    frame_end_time = datetime.datetime.fromtimestamp(meta_info['frame-end-time']).strftime('%H:%M:%S.%f')[:-3]
    frame_duration = meta_info['frame-time-duration']
    frame_number = meta_info['frame-number']
    meta_message = Table(box=box.SIMPLE, show_header=False, title="meta information", show_edge=False)
    meta_message.add_column(style="dark_blue", justify="left")
    meta_message.add_column(style="bold", justify="right")
    meta_message.add_row('Frame start tijd: ', frame_start_time)
    meta_message.add_row('Frame eind tijd: ', frame_end_time)
    meta_message.add_row('Frame tijd: ', f'{frame_duration}ms')
    meta_message.add_row('Frame nummer: ', f'{frame_number}')

    #    Align.center( meta_message),
    message_panel = Panel( meta_message, box=box.ROUNDED, padding=(1, 0), style="blue on light_yellow3", border_style="dark_blue")
    return message_panel

def make_metatelegram_message(telegram_info) -> Panel:
    header = telegram_info['header']
    checksum = telegram_info['checksum']
    version = telegram_info['1-3:0.2.8']
    equipment_id = telegram_info['0-0:96.1.1']
    timestamp = datetime.datetime.strptime(telegram_info['0-0:1.0.0'][:-1], '%y%m%d%H%M%S').strftime('%Y-%m-%d %H:%M:%S') + telegram_info['0-0:1.0.0'][-1:]
    tariff_indicator = telegram_info['0-0:96.14.0']

    meta_message = Table(box=box.SIMPLE, show_header=False, title="telegram information", show_edge=False)
    meta_message.add_column(style="dark_blue", justify="left")
    meta_message.add_column(style="bold", justify="right")
    meta_message.add_row('Header: ', header)
    meta_message.add_row('Version: ', version)
    meta_message.add_row('Equipment_id: ', equipment_id)
    meta_message.add_row('Timestamp: ', timestamp)
    meta_message.add_row('Checksum ', checksum)
    meta_message.add_row('Tariff indicator: ', tariff_indicator)

    #    Align.center( meta_message),
    message_panel = Panel( meta_message, box=box.ROUNDED, padding=(1, 0), style="blue on light_yellow3", border_style="dark_blue")
    return message_panel

def make_power_message(telegram) -> Panel:
    power_in = f'{telegram["1-0:1.7.0"]}W'
    power_out = f'{telegram["1-0:2.7.0"]}W'
    power_total = f'{telegram["1-0:1.7.0"] - telegram["1-0:2.7.0"]}W'

    power_in_L1 = f'{telegram["1-0:21.7.0"]}W'
    power_in_L2 = f'{telegram["1-0:41.7.0"]}W'
    power_in_L3 = f'{telegram["1-0:61.7.0"]}W'

    power_out_L1 = f'{telegram["1-0:22.7.0"]}W'
    power_out_L2 = f'{telegram["1-0:42.7.0"]}W'
    power_out_L3 = f'{telegram["1-0:62.7.0"]}W'

    power_total_L1 = f'{telegram["1-0:21.7.0"] - telegram["1-0:22.7.0"]}W'
    power_total_L2 = f'{telegram["1-0:41.7.0"] - telegram["1-0:42.7.0"]}W'
    power_total_L3 = f'{telegram["1-0:61.7.0"] - telegram["1-0:62.7.0"]}W'

    power_message = Table(title="Power usage", header_style="bold", show_edge=False)
    power_message.add_column("", style="bold", justify="left", min_width=8)
    power_message.add_column("Total", justify="right", min_width=8)
    power_message.add_column("L1", justify="right", min_width=8)
    power_message.add_column("L2", justify="right", min_width=8)
    power_message.add_column("L3", justify="right", min_width=8)
    power_message.add_row('In: ', power_in, power_in_L1, power_in_L2, power_in_L3)
    power_message.add_row('Out: ', power_out, power_out_L1, power_out_L2, power_out_L3)
    power_message.add_row('TOTAL: ', power_total, power_total_L1, power_total_L2, power_total_L3, style='bold')

    #    Align.center( power_message),
    message_panel = Panel( power_message, box=box.ROUNDED, padding=(1, 2), style="white on black", border_style="dark_green")
    return message_panel

def make_counter_message(telegram) -> Panel:
    electricity_in_t1 = f'{telegram["1-0:1.8.1"] / 1000.0:0.3f}kWh'
    electricity_in_t2 = f'{telegram["1-0:1.8.2"] / 1000.0:0.3f}kWh'
    electricity_in_total = f'{(telegram["1-0:1.8.1"] + telegram["1-0:1.8.2"]) / 1000.0:0.3f}kWh'

    electricity_out_t1 = f'{telegram["1-0:2.8.1"] / 1000.0:0.3f}kWh'
    electricity_out_t2 = f'{telegram["1-0:2.8.2"] / 1000.0:0.3f}kWh'
    electricity_out_total = f'{(telegram["1-0:2.8.1"] + telegram["1-0:2.8.2"]) / 1000.0:0.3f}kWh'

    counter_message = Table(title="Counter readings", header_style="bold", show_edge=False)
    counter_message.add_column("", style="bold", justify="left", min_width=8)
    counter_message.add_column("in", justify="right", min_width=8)
    counter_message.add_column("out", justify="right", min_width=8)
    counter_message.add_row('Tariff 1: ', electricity_in_t1, electricity_out_t1)
    counter_message.add_row('Tariff 2: ', electricity_in_t2, electricity_out_t2)
    counter_message.add_row('TOTAL: ', electricity_in_total, electricity_out_total, style="bold")

    #    Align.center( counter_message),
    message_panel = Panel( counter_message, box=box.ROUNDED, padding=(1, 2), style="white on black", border_style="dark_green")
    return message_panel

def make_quality_message(telegram) -> Panel:

    voltage_sags_L1 = f'{int(telegram["1-0:32.32.0"])}'
    voltage_sags_L2 = f'{int(telegram["1-0:52.32.0"])}'
    voltage_sags_L3 = f'{int(telegram["1-0:72.32.0"])}'

    voltage_swells_L1 = f'{int(telegram["1-0:32.36.0"])}'
    voltage_swells_L2 = f'{int(telegram["1-0:52.36.0"])}'
    voltage_swells_L3 = f'{int(telegram["1-0:72.36.0"])}'

    count_power_failures = f'{int(telegram["0-0:96.7.21"])}'
    count_long_power_failures = f'{int(telegram["0-0:96.7.9"])}'
    failure_info = f'{telegram["1-0:99.97.0"]}'
    text_message = f'{telegram["0-0:96.13.0"]}'

    quality_message = Table(box=box.SIMPLE, show_header=False, title="quality information", show_edge=False)
    quality_message.add_column(style="bold", justify="left")
    quality_message.add_column(justify="right")
    quality_message.add_row('Voltage sags L1 ', voltage_sags_L1)
    quality_message.add_row('Voltage sags L2 ', voltage_sags_L2)
    quality_message.add_row('Voltage sags L3 ', voltage_sags_L3)
    quality_message.add_row('Voltage swells L1 ', voltage_swells_L1)
    quality_message.add_row('Voltage swells L2 ', voltage_swells_L2)
    quality_message.add_row('Voltage swells L3 ', voltage_swells_L3)

    quality_message.add_row('Count power failures: ', count_power_failures)
    quality_message.add_row('Count long power failures: ', count_long_power_failures)
    quality_message.add_row('Failure info: ', failure_info)
    quality_message.add_row('Text message: ', text_message)

    #    Align.center( counter_message),
    message_panel = Panel( quality_message, box=box.ROUNDED, padding=(1, 2), style="white on black", border_style="dark_green")
    return message_panel

def make_phase_message(telegram) -> Panel:
    voltage_L1 = f'{telegram["1-0:32.7.0"]}V'
    voltage_L2 = f'{telegram["1-0:52.7.0"]}V'
    voltage_L3 = f'{telegram["1-0:72.7.0"]}V'

    current_L1 = f'{telegram["1-0:31.7.0"]}A'
    current_L2 = f'{telegram["1-0:51.7.0"]}A'
    current_L3 = f'{telegram["1-0:71.7.0"]}A'

    power_message = Table(title="Electrical characteristics", header_style="bold", show_edge=False)
    power_message.add_column("", style="white", justify="left", min_width=8)
    power_message.add_column("L1", style="bold", justify="right", min_width=8)
    power_message.add_column("L2", style="bold", justify="right", min_width=8)
    power_message.add_column("L3", style="bold", justify="right", min_width=8)
    power_message.add_row('Voltage: ', voltage_L1, voltage_L2, voltage_L3)
    power_message.add_row('Current: ', current_L1, current_L2, current_L3)

    #    Align.center( power_message),
    message_panel = Panel( power_message, box=box.ROUNDED, padding=(1, 2), style="white on black", border_style="dark_green")
    return message_panel

def make_gas_message(telegram) -> Panel:
    device_type = f'{telegram["0-1:24.1.0"]}'
    equipment_ID = f'{telegram["0-1:96.1.0"]}'
    measure_time = datetime.datetime.strptime(telegram_info['0-1:24.2.1.A'][:-1], '%y%m%d%H%M%S').strftime('%Y-%m-%d %H:%M:%S') + telegram_info['0-1:24.2.1.A'][-1:]
    measure_value = f'{telegram["0-1:24.2.1.B"] / 1000.0:0.3f}m3'

    gas_message = Table(title="gas measurements", header_style="bold", show_edge=False)
    gas_message.add_column("", style="bold", justify="left", min_width=8)
    gas_message.add_column("value", justify="right", min_width=8)
    gas_message.add_row('device type: ', device_type)
    gas_message.add_row('equipment_ID: ', equipment_ID)
    gas_message.add_row('measurement time: ', measure_time)
    gas_message.add_row('measurement value: ', measure_value)

    #    Align.center( gas_message),
    message_panel = Panel( gas_message, box=box.ROUNDED, padding=(1, 2), style="white on dark_blue", border_style="dark_green")
    return message_panel

class Header:
    """Display header with clock."""

    def __rich__(self) -> Panel:
        grid = Table.grid(expand=True)
        grid.add_column(justify="center", ratio=1)
        grid.add_column(justify="right")
        grid.add_row(
            "[b]Marcel[/b] Slimme meter output",
            datetime.datetime.now().ctime().replace(":", "[blink]:[/]"),
        )
        return Panel(grid, style="white on blue")


layout = make_layout()
layout["header"].update(Header())

mcastAddr = '224.7.2.1'
mcastPort = 52001

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind((mcastAddr, mcastPort))
mreq = struct.pack('4sl', socket.inet_aton(mcastAddr), socket.INADDR_ANY)
sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

data = None

with Live(layout, refresh_per_second=10, screen=True):

    while True:
        (buf, who) = sock.recvfrom(10240)
        try:
            data = json.loads(buf)
        except:
            pass

        meta_info = data['meta']
        telegram_info = data['telegram']

        layout["meta"].update(make_meta_message(meta_info=meta_info))
        layout["telegram"].update(make_metatelegram_message(telegram_info=telegram_info))
        layout["power information"].update(make_power_message(telegram=telegram_info))
        layout["cummulative information"].update(make_counter_message(telegram=telegram_info))
        layout["phase information"].update(make_phase_message(telegram=telegram_info))
        layout["quality information"].update(make_quality_message(telegram=telegram_info))
        layout["gas"].update(make_gas_message(telegram=telegram_info))
