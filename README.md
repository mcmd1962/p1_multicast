# p1_multicast
Listens to P1 port on smart meter and multicast collected data

## Introduction
This set of software is another effort to read the P1 port on the smart meter (slimme meter). Typically this software runs on a ```Raspberry Pi```, which connects with a dedicated USB cable on the serial P1 port.
The disadvantage of this setup is that only one process can connect to the USB port to collect the P1 telegrams.
This setup is using a P1 listener process which still needs to connect to the serial port, but is parsing the data, storing this is a ```Dict``` variable which is converted into ```json``` format and than multicasted on the local LAN.
With this setup all devices in the local network can subscribe to this multicast and do something with the data. This includes for example a mobile phone with Python installed on it.

## Software

This software consists of the following ```Python``` scripts:

  1. P1listener.py
  2. P1reader.py
  3. P1dashboard.py

and a ```configuration``` file:

  4. P1reader.yml

The needed ```Python libraries``` are specified in ```requirements.txt``` file.


### P1listener.py
This Python script will make a connection to the USB port which is connected to the P1 port on the smart meter. It will collect the data, parse this into a ```dict``` structure, convert this into ```json``` format and then multicast this to the network. It will also add some meta information like a timestamp and duration to the data.

### P1reader.py
This Python script will subscribe to the multicast stream and collect the data and store this in files with information:
  1. The details file: a flat file with all details from the collected data. This file is typically rotated on a daily basis.
  2. An interval file: a subset of stored data which is rotated much faster and which I use to update the database quickly with the necessary information.
  3. The day file: same information as the interval file, but rotated on a daily basis.
  4. HTML file: detailed power usage in the last few minutes which can be shown in a browser.
  5. weekly log file: A log file with condensed information rotated on a weekly basis.

### P1dashboard.py
This script is subscribing to the multicast stream and showing all available P1 information in a dashboard type page in the terminal.

### P1reader.yml
A configuration file for the P1listener and the P1reader scripts.
