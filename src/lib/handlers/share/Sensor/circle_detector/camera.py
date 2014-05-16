import cv2 as cv2
import cv2.cv as cv
import numpy as np
import detector as d
import cd_utils as utils
import socket, pickle
import time
import sys, os
print "OpenCV Version:", cv2.__version__ # Code written for 2.4.6

"""
Description
===========

camera.py captures a live feed from a camera until the ESC key is pressed.  It can be 
used to apply an object detector.  It filters all the colors but the one provided in 
the calibration file (which can be created using calibrator.py)  In addition to 
filtering out the colors, which decreases the object search space, it also does 
other relevant image pre-processing to improve object detection rate.

NOTE: If running this on a robot / not debugging, don't forget to remove the displays (unnecessary overhead)

Currently only detects circles

Possible Improvements
=====================
-Protection against malicious inputs
"""

def main(**kwargs):
  ##############################
  # Choose the calibration files to use
  ##############################
  calib_files = ['lightblue.xml']
  if len(kwargs) == 0:
    local = True
  else:
    # Get the host/port of the remote to send back data
    if 'remote_ip' in kwargs:
      remote_ip = kwargs['remote_ip']
    else:
      raise Exception("remote ip not provided")

    if 'remote_port' in kwargs:
      remote_port = int(kwargs['remote_port'])
    else:
      raise Exception("remote port not provided")

    if 'calib_files' in kwargs:
      calib_files = kwargs['calib_files']
    else:
      pass

    # Also set up the UDP socket
    UDP_IP = remote_ip
    UDP_PORT = remote_port
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.connect((UDP_IP, UDP_PORT))

    # Finally, indicate that we will be sending data to the remote
    local = False

  # Create a kernel for erosion and dilation (if you choose to use it)
  kernel = np.ones((5,5),np.uint8)

  ##############################
  # Choose the detector
  ##############################
  circle_detector = d.CircleMorphDetector()

  # Camera loop
  cam_id = utils.get_camera_id()
  print cam_id
  capture = cv.CaptureFromCAM(cam_id)
  
  # read all HSV values at beginning, so we don't constantly open files
  file_dir = os.path.dirname(os.path.realpath(__file__))
  hsv_list = []
  for file_string in calib_files:
    # Look in current directory
    success, h, s, v = utils.read_xml(os.path.join(file_dir, file_string))
    if success:
      hsv_list.append((h,s,v))
    else:
      raise Exception("Incorrectly formatted calibration file %s\n" % (file_string))
  if len(hsv_list) == 0:
    raise Exception("No files specified")

  import time
  time.sleep(2) # delays for 5 seconds
  while True:
    # Pre-processing
    # Uncomment the next two lines if using live webcam feed
    img = cv.QueryFrame(capture)
    img = np.asarray(img[:,:]) # Slice copy 2d array
    # Uncomment next line if loading from a file
    #img = cv2.imread("triangle.jpg")

    # Smooth the image for rounder edges
    blurred_img = cv2.GaussianBlur(img, (5,5), 0, 0) 
    # Gray image is for MSER detection
    #gray_img = cv2.cvtColor(blurred_img, cv2.COLOR_BGR2GRAY) # Blurred gray image
    # Convert the image from RGB space to HSV space
    img_hsv = cv2.cvtColor(blurred_img, cv2.COLOR_BGR2HSV_FULL) # Blurred HSV image
  
    mask = None
    for hsv in hsv_list:
      this_mask = utils.get_color_mask(img_hsv, hsv[0], crange=30, low_sat=50, low_val=50)
      if mask is None: # The first time, just set the mask
        mask = this_mask
      else: # Other times, bitwise OR
        mask = cv2.bitwise_or(mask, this_mask)

    if cv2.countNonZero(mask) > 0.05 * mask.shape[0] * mask.shape[1]:
      # Detect circles and draw them onto the image if there are enough pixels that are of the color
      found_circles = circle_detector.detect(mask)
    else:
      found_circles = []
    binary = mask
    mask = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
    if found_circles is not None and len(found_circles) > 0:
      for circle in found_circles:
        ###################################
        # Chose what kind of shape to draw
        ###################################
        # Morphological, the color is proportional to the intensity of the response
        cv2.circle(mask, (circle[0], circle[1]), circle[2]/2, utils.int_to_bgr(int(circle[3])))
    if not local:
      serialized = pickle.dumps(found_circles)
      if sys.getsizeof(serialized) > 1024:
        print "Too many objects, not sending"
      else:
        sock.send(serialized)

    # Uncomment the next two lines if you want to attempt to remove noise
    #mask = cv2.erode(mask, kernel, iterations=2)
    #mask = cv2.dilate(mask, kernel, iterations=2)

    cv.ShowImage("Mask", cv.fromarray(mask))
    if cv.WaitKey(10) == 27:
      break
  cv.DestroyAllWindows()

if __name__ == "__main__":
  main()