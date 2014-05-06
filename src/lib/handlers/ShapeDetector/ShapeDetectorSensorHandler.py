#!/usr/bin/env python
"""
=====================================
ShapeDetectorSensorHandler.py - Detect circles
=====================================

Enter description here
"""

import atexit, multiprocessing, pickle, threading, subprocess, os, time, socket
import numpy, math
import sys
import circle_detector.camera as detector
import lib.handlers.handlerTemplates as handlerTemplates
import logging

class ShapeDetectorSensorHandler(handlerTemplates.SensorHandler):
    def __init__(self, executor, shared_data):
        """
        Initialize the sensor settings
        """
		# Bind exit event
        atexit.register(self._close_socket)

		# Indicate that the detector is starting
        self.detector_running = True

		# Let the sensor listen to data
        self.ip = "127.0.0.1"
        self.port = 48484

        # Create a subprocess to run the circle detector
        self.subprocess = multiprocessing.Process(target=detector.main, 
            kwargs={'remote_ip':self.ip, 'remote_port':self.port, 'hsv_target':self.hsv_target})
        self.subprocess.start()

        # Create a thread to listen for detection result
        self.listen_thread = threading.Thread(target=self._listen_for_circles)
        self.listen_thread.start()

        self.is_circle_detected = False

    def _listen_for_circles(self):
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
            self.detected_circles = data
            self.is_circle_detected = True if len(self.detected_circles) > 0 else False
        self.sock.close()

    def circle_detected(self, init_value, initial=False):
        """
        return true if a circle is detected
        init_value (bool): The initial state of the sensor (default=False)
        """
        if initial:
            self.is_circle_detected = init_value
        else:
            return self.is_circle_detected


    def _close_socket(self):
        """ Callback to close socket when program completes """
        if self.sock is not None:
            print "Tearing down", self.sock
            self.sock.close()

