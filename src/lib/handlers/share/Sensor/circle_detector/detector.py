import cv2 as cv2
import cv2.cv as cv
import numpy as np
import cd_utils as utils
import scipy.cluster.vq as vq

"""
Description
===========

Provides a detector interface to standardize object detection as well as implementation
of several, simple detectors

Possible Improvements
=====================
-Need to pull out/generalize the pyramiding/suppression
-Definitely need to make all the parameters tweakable
-Implement a wrapper to standardize the outputs for easier plugging/testing into camera.py
-Implement this in C (At this point, trying to optimize is crazy...While loops end up being slower than
  for loops + range() function, bitshifts end up being slower than division -- 
  Python makes low-level optimization difficult)
"""

class Detector(object):
  """ Detector interface.  All detectors should provide a method that indicates
  if an object was found """
  def __init__(self):
    self.exists = False
    self.interest_points = None
  
  def detect(self, img):
    """ A detector should find interest points and then store it in 
    self.interest_points in the form necessary. It should also indicate
    if the feature exists using self.exists """
    raise Exception("detect is an abstract method and must be implemented by the derived class")

  def is_object_detected(self):
    return self.exists

  def get_interest_points(self):
    return self.interest_points

  def set_interest_points(self, arraylike):
    """ Automatically toggles exists flag """
    if len(arraylike) > 0:
      self.exists = True
    self.interest_points = arraylike

def print_ndarray(arr):
  """ Function to help debugging by formatting and printing a whole ndarray """
  print arr.shape[0], arr.shape[1]
  for r in range(arr.shape[0]):
    print "[", 
    for c in range(arr.shape[1]):
      print "%6.2f" % (arr[r][c]),
    print "]\n"

def print_ndarray_window(arr, xmin, xmax, ymin, ymax):
  """ Function to help debugging by formatting and printing a portion of an ndarray
  The portion is a rectangle specified by the 4 parameters: xmin, xmax, ymin, ymax.
  Bounds are not checked. """
  print arr.shape[0], arr.shape[1]
  for r in range(arr.shape[0]):
    if r >= ymin and r <= ymax:
      print "[", 
      for c in range(arr.shape[1]):
        if c >= xmin and c <= xmax:
          print "%.2f" % (arr[r][c]),
      print "]\n"

class ScaleSuppressMethod:
  """ Used in CircleMorphDetector to indicate the suppression method over scales.
  1. KMeans should be used if we know the number of objects that we need to detect a priori
  2. NMS (non maximum suppression) should be used if we do not know the number of objects
    to detect, and it will simply return the strongest detected candidates. """
  KMeans = 1
  NMS = 2

class MorphDetector(Detector):
  """
  Description
  ===========
  A morph detector applies a morphological filter (http://en.wikipedia.org/wiki/Mathematical_morphology)
  (i.e. a pre-defined shape) to an image at multiple scales.

  Possible Improvements
  =====================
  -See suppress and detect TODOs
  """
  def __init__(self, filter_width=30, window_size=3, threshold=150, pyramid_scale=2, sm=ScaleSuppressMethod.NMS):
    """ We assume that the detector will be applied to an image larger than the filter """
    super(MorphDetector, self).__init__()
    # The width of the filter, to be used in determining number of images in the pyramid, etc.
    self.filter_width = filter_width
    # The square window, mainly used in suppression
    self.window_size = window_size
    # The response threshold. Values below the threshold are ignored.  Should be [0-255]
    self.threshold = threshold
    # The scaling of the images in the pyramid.  For example, a scale of 2 means divide an image
    # in half for every successive pyramid application
    self.pyramid_scale = pyramid_scale
    # The scale suppression method.  See ScaleSuppressMethod
    self.sm = sm
    # Scale of the highest detected response (assuming one object of interest)
    self.best_scale = None

  def create_filter(self):
    raise Exception("create_filter is abstract and must be implemented by the derived class")

  def get_filter(self):
    if self.filter is None:
      raise Exception("No filter created")
    else:
      return self.filter

  def suppress(self, img, scale):
    """ 
    img: a binary image with response values.  
    scale: The current scale of the image, which is the inverse of (current size / original image size)
    returns: The location in pixels of the interest points, scaled to the pyramid, the actual size
      of the feature and the response value
      e.g. For a circle, a list of tuples (x : int, y : int, diameter : int, score : float) 

    Loop through all the pixels in img and determine if each pixel is a local maximum a square 
    window of width=window_size. If the pixel is a local max, then leave it, otherwise, 
    set the new value to 0.  Higher window_size means less false positives

    The points still need to be suppressed over scales

    Note that the threshold, when using a normalized filter, directly represents the proportion
    of the area captured by the morphological filter, but one should not necessarily set the
    threshold to a high value such as 200 or 255.  Such high values (80-100%)
    can only really be achieved if filter's size is exactly equal to the feature size (which is
    very unlikely).  Also, the threshold can be increased if pyramid scale is more granular

    Possible Improvements
    ===================== 
    1. Floating points are really slow, maybe move to gpu
    2. Use a non-maximum suppression method specified in Neubeck """
    rows = img.shape[0] # height
    cols = img.shape[1] # width
    offset = self.window_size / 2
    result_pixels = []
    for r in range(rows - self.window_size):
      for c in range(cols - self.window_size):
        center_response = int(img[r + offset][c + offset])
        # Ignore pixels under the threshold (optimization)
        if center_response < self.threshold:
          continue
        suppressed = False
        for w_r in range(self.window_size):
          for w_c in range(self.window_size):
            # suppress current pixel if there's a larger response nearby
            # we ignore negative pixels for now
            if int(img[r + w_r][c + w_c]) > center_response:
              suppressed = True
        if not suppressed:
          # Note that we're reversing c to be x and r to be y
          result_pixels.append((int(c * scale), int(r * scale), int(self.filter_width * scale), center_response))

    return result_pixels

  def detect(self, img):
    """
    img: a binary image with the filtered colors. Note that opencv images are row-first ordered
    pyramid_scale: the granularity of the image pyramid.
    returns an array of the features with the highest response.

    TODO:
    1. Massive optimization
      -Search list in scale suppression instead of searching window (makes it faster by about 25% (0.05s))
      -Break/continue statements (this actually ends up being slower on my machine)
      -The significant portion of time is used by suppress
      -If something is found, detect only at that scale until the object is lost (tracking)
    2. Scale suppress (heuristically, we can take the largest circles in a cluster, or k-means clusters
      for a known number of circles such as 1) """
    # 0. Reset detector flags
    self.interest_points = []
    self.exists = False

    # 1. Convert int8 array to float32 array to avoid overflows and get more precision
    pyramid = img.astype(np.float32)

    if self.best_scale is not None:
      # Pyramid is a full sized image
      # Neighbor scales
      low_scale = self.best_scale * self.pyramid_scale # Smaller image
      high_scale = self.best_scale / self.pyramid_scale # Larger image

      low = cv2.resize(pyramid, (int(pyramid.shape[1]/low_scale), 
        int(pyramid.shape[0]/low_scale)), interpolation=cv2.INTER_NEAREST)
      # Only suppress the low image if it's larger than the filter
      if low.shape[0] >= self.filter_width or low.shape[1] >= self.filter_width:
        response_l = cv2.filter2D(low, -1, self.filter, borderType=cv2.BORDER_REPLICATE)
        self.interest_points = self.interest_points + self.suppress(response_l, low_scale)
      # same scale
      mid = cv2.resize(pyramid, (int(pyramid.shape[1]/self.best_scale), 
        int(pyramid.shape[0]/self.best_scale)), interpolation=cv2.INTER_NEAREST)
      response_m = cv2.filter2D(mid, -1, self.filter, borderType=cv2.BORDER_REPLICATE)
      # one size higher
      high = cv2.resize(pyramid, (int(pyramid.shape[1]/high_scale), 
        int(pyramid.shape[0]/high_scale)), interpolation=cv2.INTER_NEAREST)
      response_h = cv2.filter2D(high, -1, self.filter, borderType=cv2.BORDER_REPLICATE)
      self.interest_points = (self.interest_points + self.suppress(response_m, self.best_scale) + 
        self.suppress(response_h, high_scale))
    else:
      scale = 1
      # 2. Convolve (actually cross-correlate) filter with the image at multiple scales of the image.  
      # This allows us to detect different sized circles
      while(pyramid.shape[0] > self.filter_width and pyramid.shape[1] > self.filter_width):
        response = cv2.filter2D(pyramid, -1, self.filter, borderType=cv2.BORDER_REPLICATE)
        self.interest_points = self.interest_points + self.suppress(response, scale)
        scale = scale * self.pyramid_scale
        # Resize using nearest neighbor for speed
        pyramid = cv2.resize(pyramid, (int(pyramid.shape[1]/self.pyramid_scale), 
          int(pyramid.shape[0]/self.pyramid_scale)), interpolation=cv2.INTER_NEAREST)


    # 3. Do a suppression of scales. Add the suppression type as an argument to determine best suppression method
    if self.sm == ScaleSuppressMethod.NMS:
      #print "Scale Suppression, %d interest points found" % (len(self.interest_points))
      num_rows = img.shape[0]
      num_cols = img.shape[1]
      # an array in column first order (also, x=col, y=row).  The array stores pointers to interest point tuples
      point_array = [[None for x in range(num_rows)] for y in range(num_cols)]
      suppressed_points = []
      # populate array
      for p in self.interest_points:
        point_array[p[0]][p[1]] = p
      # suppress using the list for efficiency, while looking up neighbors using the array
      for p in self.interest_points:
        current_response = p[3]
        # use the filter_width as a window
        is_max = True
        offset = p[2] / 2
        for r in range(p[2]):
          for c in range(p[2]):
            n_c = p[0] + c - offset
            n_r = p[1] + r - offset
            # if in bounds, circle exists, suppress if current point is not the maximum
            if utils.in_bounds(num_rows, num_cols, n_r, n_c):
              neighbor = point_array[n_c][n_r]
              if neighbor is not None and p is not neighbor:
                if current_response <= neighbor[3]:
                  point_array[p[0]][p[1]] = None
                  is_max = False
                else:
                  # remove the neighbor by searching the list, which is faster than going
                  # through the window size of the window size is large. To be specific, this
                  # is effective if len(list) < window_size * window_size
                  point_array[neighbor[0]][neighbor[1]] = None
                  self.interest_points.remove(neighbor)
        if is_max:
          suppressed_points.append(p)
      self.set_interest_points(suppressed_points)
      if len(self.interest_points) == 1:
        self.best_scale = float(self.interest_points[0][2]) / self.filter_width
    elif self.sm == ScaleSuppressMethod.KMeans:
      # We can use this if we know that a single circle will exist, alternatively, we can write
      # the code to pass in k as a parameter vq.kmeans2
      # Convert the interest points to an ndarray of the location and and size.  
      # The resulting response is meaningless
      # TODO: Probably want to remove outliers
      if len(self.interest_points) > 0:
        lst = np.array(map(lambda pt: np.array([pt[0], pt[1], pt[2], pt[3]]), self.interest_points))
        # get the centroids
        result = (vq.kmeans2(lst, 1)[0]).astype(np.uint32)
        self.set_interest_points(result)
    else:
      raise Exception("Not implemented")
    
    return self.interest_points

class CircleMorphDetector(MorphDetector):
  """ 
  Description
  ===========
  CircleMorphDetector uses a morphological filter and image pyramids to find circles
  in an image.  The general steps are as follows:
  1. Create a circular filter of arbitrary size.  A larger circle is more efficient because 
  it requires less images, but it will only detect larger circles.
  2. We convolve the filter at multiple scales using images that decrease in size.  The set 
  of images is also known as an image pyramid.  This allows us to detect multiple sized 
  selectors.  At each scale, the convolution results in an image in which each pixel 
  contains a response (a "score").  The response indicates how likely there is a circle
  centered at that pixel.  The higher the value, the more likely it is.
  3. At each scale, we take only the highest responses in each area of the image that exceeds
  a provided threshold.
  4. We have best circles at each scale, but we can be detecting the same circle at multiple
  scales. Thus, we run scale suppression to find the best circles along all scales.
  5. Finally, we return the detected circles and hope they are actually circles.
  """
  def __init__(self, filter_width=61, window_size=3, threshold=200, pyramid_scale=1.3, sm=ScaleSuppressMethod.NMS):
    """ We assume that the detector will be applied to an image larger than the filter.  Note that
    the filter width is equal to the diameter of the circle 
    filter_with: The diameter of the circle """
    if filter_width % 2 == 0 or filter_width < 3:
      raise Exception("Filter width needs to be an odd number larger than 3")
    super(CircleMorphDetector, self).__init__(filter_width, window_size, threshold, pyramid_scale, sm)
    self.filter = self.create_filter(filter_width)

  def create_filter(self, diameter):
    """ Creates a circular filter with 1s on the circle and -1s everywhere else.  The filter
    is then normalized.  A point is determined to be on the circle if its distance to the 
    origin is less than or equal to the radius.  The circle will always be odd length """
    import math
    radius = (diameter - 1) / 2
    #average = 1.0/(diameter*diameter)
    circle_area = math.pi * radius * radius
    average = 1.0/circle_area
    f = [[1 for y in range(diameter)] for x in range(diameter)]
    # We're shifting the origin to the center of the circle (by radius length)
    radius_sq = radius*radius
    for col in range(diameter):
      for row in range(diameter):
        c = col - radius
        r = row - radius
        distance_sq = c*c + r*r
        if distance_sq > radius_sq:
          f[col][row] = -1*average
        else:
          f[col][row] = 1*average
    return np.array(f, dtype=np.float32)

class TriangleMorphDetector(MorphDetector):
  """ 
  Description
  ===========
  """
  def __init__(self, degrees, filter_width=51, window_size=3, threshold=200, pyramid_scale=1.2, sm=ScaleSuppressMethod.NMS):
    """ The filter_width for a triangle is actually the height of the triangle.
    degrees: half the angle of the top of the triangle.  In other words, the triangle is inscribed in a square with
      a single vertex touching the midpoint of the top of the square. The degrees is the half the angle of that vertex
      Currently requires the degrees to be less than 30 """
    super(TriangleMorphDetector, self).__init__(filter_width, window_size, threshold, pyramid_scale, sm)
    if filter_width % 2 == 0 or degrees < 30:
      raise Exception("Filter width needs to be of odd length and degrees less than 30")
    self.filter = self.create_filter(filter_width, degrees)

  def create_filter(self, height, degrees):
    """ Create a triangle by comparing the degree of the segment connected the tip of the triangle to the point and 
    the provided degree for the triangle """
    import math
    f = [[0 for x in range(height)] for y in range(height)] # row first order
    offset = height / 2
    radians = (90 - degrees) * math.pi / 180.0
    tip_x = height # column, on screen
    tip_y = height / 2 # row, on screen
    area = height * (height * math.tan(degrees * math.pi / 180.0))
    average = 1 / area
    for x in range(height):
      for y in range(height):
        cx = abs(x - tip_x)
        cy = abs(y - tip_y)
        if cy == 0:
          curr_d = 0
        else:
          curr_d = math.atan(float(cx)/cy)
        if curr_d > radians or curr_d == 0:
          f[x][y] = average
        else:
          f[x][y] = -1*average
    self.filter = np.flipud(np.array(f, dtype=np.float32))
    #print self.filter
    return self.filter

class CircleHoughDetector(Detector):
  """
  Uses the
  http://stackoverflow.com/questions/7734377/cv-hough-circle-parameters-to-detect-circles
  http://stackoverflow.com/questions/10716464/what-are-the-correct-usage-parameter-values-for-houghcircles-in-opencv-for-iris
  """
  def __init__(self):
    None

  def detect(self, img):
    """ Returns the circles in an array of arrays. The first index of each inner array contains a tuple of 
    the x-position, y-position and radius. """
    average = (img.shape[0] + img.shape[1]) / 2
    found_circles = cv2.HoughCircles(img, cv.CV_HOUGH_GRADIENT, dp=4, minDist=average/3, minRadius=average/10, maxRadius=average/2)
    return found_circles
