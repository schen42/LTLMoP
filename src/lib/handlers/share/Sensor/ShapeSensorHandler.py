#!/usr/bin/env python
"""
=====================================
ShapeSensorHandler.py - Detect shapes
=====================================

Enter description here
"""

import atexit, multiprocessing, pickle, threading, subprocess, os, time, socket
import numpy, math
import sys
import circle_detector.camera as detector
import lib.handlers.handlerTemplates as handlerTemplates
import logging

class ShapeSensorHandler(handlerTemplates.SensorHandler):
    def __init__(self, executor, shared_data):
        """
        Initialize the sensor handler by starting the detector subprocess and listener thread.
        The sensor handler sends the subprocess its IP and port so that the subprocess knows
        where to send back the detected circles.

        Currently, a subprocess is created for the detector code, and the subprocess sends back 
        a serialized list of shapes found using a UDP socket.
        
        TODO: 
            0. Figure out a way to send a list of file names to the subprocess.
            1. Take the port number as a parameter.  
            2. give the user the option to run the shape detector locally or remotely.
            3. handle malicious user input
        """
        atexit.register(self._close_socket)

        self.detector_running = True

        self.ip = '127.0.0.1'
        self.port = 48484

        # Create a subprocess to run the shape detector
        self.subprocess = multiprocessing.Process(target=detector.main, 
            kwargs={'remote_ip':self.ip, 'remote_port':self.port})
        self.subprocess.start()

        # Create a thread to listen for detection result
        self.listen_thread = threading.Thread(target=self._listen_for_shapes)
        self.listen_thread.start()

        self.is_shape_detected = False

    def _listen_for_shapes(self):
        """ Listen for detected shapes found by the subprocess.  Create a socket for the 
        data transfer. The data will be serialized using the pickle module, so unpickle it 
        as well.  If there are shapes detected, it will also set the global is_shape_detected
        flag """
        UDP_IP = self.ip
        UDP_PORT = self.port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # UDP
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((UDP_IP, UDP_PORT))
        logging.info("--Listening:")
        sys.stdout.flush()
        while self.detector_running:
            # Add try and catch
            data, addr = self.sock.recvfrom(1024)
            data = pickle.loads(data)
            if len(data) > 0:
                logging.info("----received circles: %s" % (str(data)))
            self.detected_shapes = data
            self.is_shape_detected = True if len(self.detected_shapes) > 0 else False
        self.sock.close()

    def shape_detected(self, init_value, initial=False):
        """
        return true if a circle is detected
        init_value (bool): The initial state of the sensor (default=False)
        file_names (list): The list of file names of the calibration files that the sensor
        should use
        """
        if initial:
            self.is_shape_detected = init_value
        else:
            return self.is_shape_detected


    def _close_socket(self):
        """ Callback to close socket when program completes """
        if self.sock is not None:
            print "Tearing down", self.sock
            self.sock.close()

