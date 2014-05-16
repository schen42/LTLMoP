import cv2 as cv2
import numpy as np

"""
Color Detection Utility functions used by the color and object detection code
"""

def in_bounds(h, w, r, c):
  """ Given the height, width, row/column coordinates, determine
  if the coordinates are in bounds """
  return r >= 0 and r < h and w >= 0 and c < w

def int_to_bgr(value):
  """ Convert an integer [0, 255] into an HSV hue and then into RGB.
  Red/Yellow is low, Indigo/Red is high """
  import colorsys
  # colorsys takes and returns values [0, 1]
  (r,g,b) = colorsys.hsv_to_rgb(value/255.0, 1, 1)
  return (255*b, 255*g, 255*r)

def get_camera_id(filename="camera_id.txt"):
  """ Get the camera id in the file. Should be a number [0-2].  If
  there are any errors, return 0 and hope that a camera is actually 
  connected.  If there isn't, an exception will be thrown. """
  import os
  try:
    file_dir = os.path.dirname(os.path.realpath(__file__))
    full_path = os.path.join(file_dir, filename)
    f = open(full_path, 'r')
    id_ = f.readline(1) # Read a single byte
    f.close()
  except IOError:
    print ("%s could not be opened") % (full_path) 
    id_ = 0

  try:
    id_ = int(id_)
    return id_
  except ValueError:
    print "Invalid file contents"
    return 0

def read_xml(filename="calibdata.xml"):
  """ Read the configuration file.  [filename] should be an absolute path
  if possible. Returns a boolean indicating if the read was successful, and the read
  HSV values if it was (0,0,0 otherwise). """
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
      Turn an image into a binary mask (0, 255) where the pixel is 255 if it is within the provided
      color threshold and 0 otherwise.

      img: an 8 bit (by default) numpy array with HSV values. 8-bit means that the range of H 
          is [0-255].  Note: HSV range is [0-180], and afterwards, it repeats.
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