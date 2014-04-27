"""
Utility functions used by the color and object detection code
"""

def in_bounds(h, w, r, c):
  """ Given the height, width, row/column coordinates, determine
  if the coordinates """
  return r >= 0 and r < h and w >= 0 and c < w

def int_to_bgr(value):
  """ Convert an integer [0, 255] into an HSV hue and then into RGB.
  Red/Yellow is low, Indigo/Red is high """
  import colorsys
  # colorsys takes and returns values [0, 1]
  (r,g,b) = colorsys.hsv_to_rgb(value/255.0, 1, 1)
  return (255*b, 255*g, 255*r)
