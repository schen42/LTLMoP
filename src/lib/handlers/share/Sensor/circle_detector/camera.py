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

Possible Improvements
=====================
-Protection against malicious inputs
"""

def read_xml(filename="calibdata.xml"):
  """ Read the configuration file """
  import xml.etree.ElementTree as ET
  tree = ET.parse(filename)
  root = tree.getroot()
  colordata = root.find('Color')
  if colordata is not None:
    # Minimal handling for malformed/malicious inputs
    h = colordata.attrib['H']
    s = colordata.attrib['S']
    v = colordata.attrib['V']
    if h is not None and s is not None and v is not None:
      return True, int(h), int(s), int(v)
  return False, 0, 0, 0 


def get_color_mask(img, color, crange=10, low_sat=100, high_sat=255, low_val=100, high_val=255):
  """
      Turn an image into a binary mask (0, 255) where the pixel is 1 if it is within the provided
      color threshold and 0 otherwise.

      img: an 8 bit (by default) numpy array with HSV values. 8-bit means that the range of H 
          is [0-255].  Note: HSV range is [0-180], and afterwards, it repeats
          HSV_FULL range is [0-255] with no repeats.  This is achieved by multiplying by 255/180
          We will use FULL_RANGE
      color: a hue in the range [0, 255]
      range: the precision/width of the hue detection.  A higher value produces more detected values
          but more false positives [0, 255]
      low_sat, high_sat: The desired range for saturation [0-255]. Not a centered value to provide
        more flexibility with saturation and value 
      low_val, high_val: The desired range for value/brightness [0-255]
  """
  # 0. Validate Inputs
  assert (crange > 1 and crange <= 360 and low_sat > 0 and high_sat > low_sat and low_val > 0 
  and high_val > low_val and high_sat <= 255 and high_val <= 255)

  # 1. Calculate the range of the hue and make sure it remains in the range [0, 255].
  # Also determine if the range has wrapped around
  # (this will happen with red, which can be at both the 0 and 255 ends of the spectrum). 
  low = color - int(crange/2)
  high = color + int(crange/2)
  wrapped = False
  if low < 0:
    wrapped = True
    low += 255
  elif high > 255:
    wrapped = True
    high -= 255
  if wrapped:
    low, high = high, low
  assert high >= low

  # 2. inRange Mask. If it wrapped, we need to apply inRange twice to capture both ends of the spectrum
  if (wrapped):
    mask1 = cv2.inRange(img, np.array([0, low_sat, low_val]), np.array([low, high_sat, high_val]))
    mask2 = cv2.inRange(img, np.array([high, low_sat, low_val]), np.array([255, high_sat, high_val]))
    return cv2.bitwise_or(mask1, mask2)
  else:
    return cv2.inRange(img, np.array([low, low_sat, low_val]), np.array([high, high_sat, high_val]))

def main(**kwargs):
  # Default files to use
  calib_files = ['red.xml', 'lightblue.xml']
  if len(kwargs) == 0:
    # If we run it locally, load local file
    local = True
    # Read the calibration file
    read_success, h, s, v = read_xml()
    if not read_success:
      raise Exception("Couldn't read calibration file (calibdata.xml)")
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

  # Choose the detector
  circle_detector = d.CircleMorphDetector()
  #circle_detector = d.CircleHoughDetector()
  #triangle_detector = d.TriangleMorphDetector(30)

  # Camera loop
  cam_id = utils.get_camera_id()
  print cam_id
  capture = cv.CaptureFromCAM(cam_id)
  
  # read all HSV values at beginning, so we don't constantly open files
  file_dir = os.path.dirname(os.path.realpath(__file__))
  hsv_list = []
  for file_string in calib_files:
    # Look in current directory
    success, h, s, v = read_xml(os.path.join(file_dir, file_string))
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
      this_mask = get_color_mask(img_hsv, hsv[0], crange=30, low_sat=50, low_val=50)
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
    if found_circles is not None:
      for circle in found_circles:
        # Morphological, the color is proportional to the intensity of the response
        cv2.circle(mask, (circle[0], circle[1]), circle[2]/2, utils.int_to_bgr(int(circle[3])))
        # Hough
        #cv2.circle(mask, (int(circle[0][0]), int(circle[0][1])), int(circle[0][2]), (0, 255, 0))
    if not local:
      serialized = pickle.dumps(found_circles)
      if sys.getsizeof(serialized) > 1024:
        print "Too many objects, not sending"
      else:
        sock.send(serialized)

    # Uncomment the next two lines if you want to attempt to remove noise
    #mask = cv2.erode(mask, kernel, iterations=2)
    #mask = cv2.dilate(mask, kernel, iterations=2)
    '''found_triangles = triangle_detector.detect(binary)
    if found_triangles is not None:
      for circle in found_triangles:
        # Morphological, the color is proportional to the intensity of the response
        cv2.circle(mask, (circle[0], circle[1]), circle[2]/2, utils.int_to_bgr(int(circle[3])))'''

    cv.ShowImage("Mask", cv.fromarray(mask))
    if cv.WaitKey(10) == 27:
      break
  cv.DestroyAllWindows()

if __name__ == "__main__":
  main()