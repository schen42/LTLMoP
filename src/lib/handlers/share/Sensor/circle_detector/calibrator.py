import cv2 as cv2
import cv2.cv as cv
import numpy as np
import wx
import os
import cd_utils as utils
from camera import get_color_mask

"""
Description
===========

This simple tool allows a user to take a picture using a webcam or load an image, so that
a desired color may be extracted from it.  This is achieved by allowing the user to "brush" over
the image (left mouse click, and while the button is still held down, drag over the area). The tool
then averages the colors in the brushed area.  The color can then be saved to a configuration file
and used to preprocess images by filtering out colors that are not the selected color.

OpenCV is used to take a webcam picture and save it to disk. The image is then saved into a wxImage,
which is loaded into a wxStaticBitmap to be displayed.

As per OpenCV conventions, each value for HSV is in the range [0, 255]

Known Bugs
==========
-See load_image

Possible Improvements
=====================
-Efficient event handling
  -Allow user to see the strokes as s/he is making them
"""

class CalibratorFrame(wx.Frame):
  ############
  # HANDLERS #
  ############
  def ShowCameraErrorMessage():
    wx.MessageBox('Camera Could Not Be Read', 'Warning', wx.OK | wx.ICON_INFORMATION)

  def load_image(self, filename):
    """ Helper function to load an image from disk into the global variables and other tasks.
    Bugs: 
    1. Panel size doesn't change (Possible solution:
      http://stackoverflow.com/questions/3484326/resizing-a-wxpython-wx-panel) """
    # Set last_file_name so that we may reload the image when necessary
    self.last_file_name = filename
    # Destroy children, if any, then create a new image, which stores the actual image
    # and imagebitmap, which displays the image.  Attach all necessary handlers
    self.img_panel.DestroyChildren()
    self.image = wx.Image(filename, wx.BITMAP_TYPE_ANY) # image info
    self.imageBitmap = wx.StaticBitmap(self, wx.ID_ANY, wx.BitmapFromImage(self.image))
    wx.EVT_LEFT_DOWN(self.imageBitmap, self.image_click_handler)
    wx.EVT_LEFT_UP(self.imageBitmap, self.image_release_handler) 
    wx.EVT_MOTION(self.imageBitmap, self.image_move_handler)
    # Reset all counts, unbrush all
    self.sum_red = self.sum_blue = self.sum_green = self.pixel_count = 0
    img_w, img_h = self.image.GetWidth(), self.image.GetHeight()
    self.brushed = [[False for x in xrange(img_h)] for x in xrange(img_w)]
    self.brushedImage = [[False for x in xrange(img_h)] for x in xrange(img_w)]
    # Finally, re-render
    self.box.Fit(self.img_panel)
    self.box.RecalcSizes()
    self.img_panel.Refresh()
    self.Refresh()

  def save_config(self, handler):
    """ Save a configuration file which details the hue, saturation and value of the brushed area in 
    the image into a user-specified file """
    # http://stackoverflow.com/questions/1912434/how-do-i-parse-xml-in-python
    config_string = ("""<CalibData><Color H=\"%d\" S=\"%d\" V=\"%d\"></Color></CalibData>""" 
      % (self.calib_h, self.calib_s, self.calib_v))
    dialog = wx.FileDialog(None, "Choose a file", os.getcwd(), "", "XML File (*.xml)|*.xml", wx.OPEN)
    if dialog.ShowModal() == wx.ID_OK:
      f = open(dialog.GetPath(), 'w')
      f.write(config_string)
      f.close()
      print "Saved:", "H:", self.calib_h, "S:", self.calib_s, "V:", self.calib_v, " into", dialog.GetPath()

  def open_image(self, handler):
    """ Handler for open file dialog """
    wildcard = "JPEG image (*.jpg)|*.jpg| PNG image (*.png)|*.png"
    dialog = wx.FileDialog(None, "Choose a file", os.getcwd(), "", wildcard, wx.OPEN)
    if dialog.ShowModal() == wx.ID_OK:
      print "Opening", dialog.GetPath()
      self.load_image(dialog.GetPath())  

  def image_click_handler(self, handler):
    """ Handler for when user pressed left mouse button.  We set a flag indicating
    that the button was pressed, so that brush accumulation can be handled in a mousemove
    event """
    self.is_left_depressed = True
    self.brushedImage[handler.GetPositionTuple()[0]][handler.GetPositionTuple()[1]] = True

  def image_move_handler(self, handler):
    """ Called when the mouse moves in the image.  It stores all the pixels that the 
    mouse moved over, but does not fill out actual brush strokes until later.  Such post-processing
    is necessary for smooth brush movement (since we're sort of hacking together a canvas) """
    if self.is_left_depressed is True:
      this_col = handler.GetPositionTuple()[0]
      this_row = handler.GetPositionTuple()[1]
      # Mark the centers, for later processing (efficiency purposes)
      self.brushedImage[this_col][this_row] = True  

  def in_bounds(self, h, w, r, c):
    """ Helper function. Given the height, width, row/column coordinates, determine
    if the coordinates are in bounds """
    return r >= 0 and r < h and w >= 0 and c < w

  def image_release_handler(self, handler):
    """ When the dragging motion is over, this event is triggered.  Take all the pixels
    accumulated during the mouse_move event and fill them in/average them using the brush
    radius.  Store the HSV averages into global variables. Finally, indicate that an area 
    has been brushed by modifying the image. """
    self.is_left_depressed = False

    # Used in the computation of the area to accumulate
    offset = self.brush_radius
    img_w = self.image.GetWidth()
    img_h = self.image.GetHeight()     
    # Loop through the image   
    for col in range(img_w):
      for row in range(img_h):
        # If this was marked, get area around it
        if self.brushedImage[col][row]:
          # Loop through the square of width radius * 2
          for col_offset in range(self.brush_radius * 2):
            for row_offset in range(self.brush_radius * 2):
              curr_c = col - offset + col_offset
              curr_r = row - offset + row_offset
              if self.in_bounds(img_h, img_w, curr_r, curr_c) and not self.brushed[curr_c][curr_r]:
                # don't forget to indicate that this pixel was accumulated
                self.brushed[curr_c][curr_r] = True            
                self.sum_red += self.image.GetRed(curr_c, curr_r)
                self.sum_blue += self.image.GetBlue(curr_c, curr_r)
                self.sum_green += self.image.GetGreen(curr_c, curr_r)
                self.image.SetRGB(curr_c, curr_r, 0, 0, 0)
                self.pixel_count += 1
    # Ensure that we are not dividing by zero
    if self.pixel_count > 0:
      r = self.sum_red / self.pixel_count
      g = self.sum_green / self.pixel_count
      b = self.sum_blue / self.pixel_count
      self.imageBitmap.SetBitmap(wx.BitmapFromImage(self.image))
      # Convert RGB to HSV
      # http://docs.wxwidgets.org/trunk/classwx_image_1_1_h_s_v_value.html#details
      hsv = wx.Image.RGBtoHSV(wx.Image_RGBValue(r, g, b))
      self.calib_h = hsv.hue * 255.0
      self.calib_s = hsv.saturation * 255.0
      self.calib_v = hsv.value * 255.0
      self.colors_textbox.SetValue(self.get_formatted_hsv_string())

  def hsv_text_change(self, handler):
    """ A dummy handler to update the textbox that displays the currently accumulated HSV """
    None

  def dummy_handler(self, handler):
    """ A dummy handler that does nothing """
    None

  def reset_strokes(self, handler):
    """ Just reload the image for now """
    self.load_image(self.last_file_name)

  def get_formatted_hsv_string(self):
    return "%.2f %.2f %.2f" % (self.calib_h, self.calib_s, self.calib_v)

  def update_radius(self, handler):
    """ Change the radius of the brush using the slider """
    self.brush_radius = self.slider.GetValue()
    self.radius_textbox.SetValue(str(self.brush_radius))

  def take_picture(self, handler):
    """ Take a picture and write it to disk, for later use such as debugging.  Alternatively,
    we can load it into a wxImage after getting it into a 3D array """
    capture = cv.CaptureFromCAM(utils.get_camera_id())
    #http://ivtvdriver.org/index.php/Main_Page
    import time
    time.sleep(2) # Wait for the camera to turn on
    img = cv.QueryFrame(capture)
    # A hack to fix the weird capture issue with the VX-700 where the first frame is always black
    # and possibly the discoloration issue with the other webcam
    img = cv.QueryFrame(capture)
    if img is not None:
      img = np.asarray(img[:,:]) # Slice copy 2d array
      cv2.imwrite("./webcam_capture.jpg", img)
      self.load_image("./webcam_capture.jpg")
    else:
      print "An error occurred, please try taking the picture again"

  def __init__(self, *args, **kwargs):
    super(CalibratorFrame, self).__init__(*args, **kwargs)
    ###########
    # MEMBERS #
    ###########
    # the wxImage which stores the actual image data such as the color of each pixel
    self.image = None
    # the wxStaticBitmap widget that displays the image
    self.imageBitmap = None
    # The wxPanel that contains the bitmap, so that it can be refreshed elsewhere
    self.img_panel = None
    # a binary map indicating the centers of the regions to brush.  Useful for efficient
    # handling of the mouse events, so that we may fill out the brushed areas after the mouse
    # button is raised
    self.brushedImage = None
    # Indicate if an area has been brushed already so we don't double count values
    self.brushed = None  
    self.calib_h = 0 # The h, s and v values computed, so that they may be saved in a config file
    self.calib_s = 0
    self.calib_v = 0
    self.pixel_count = 0
    self.sum_red = 0
    self.sum_blue = 0
    self.sum_green = 0
    self.Frame = None # The main GUI frame
    self.is_left_depressed = False # Indicates if the left mouse button is pressed, for the drag action
    self.brush_radius = 7 # Radius of the brush stroke
    self.last_file_name = None # name of the file loaded, so that it may be reloaded

    # Call UI Initialization
    self.InitUI()
    
  def InitUI(self):
    """Initialize the CalibrationFrame (self)"""
    # Menu
    menubar = wx.MenuBar()
    filemenu = wx.Menu()
    open_item = filemenu.Append(wx.ID_ANY, '&Open Image', 'Open an image')
    self.Bind(wx.EVT_MENU, self.open_image, open_item)
    save_item = wx.MenuItem(filemenu, wx.ID_SAVE, '&Save Config')
    filemenu.AppendItem(save_item)
    self.Bind(wx.EVT_MENU, self.save_config, save_item)
    reset_item = filemenu.Append(wx.ID_ANY, '&Reset Strokes', 'Reset the brushed areas of the image')
    self.Bind(wx.EVT_MENU, self.reset_strokes, reset_item)
    menubar.Append(filemenu, '&File')
    self.SetMenuBar(menubar)

    # Main boxsizer that contains everything
    self.box = wx.BoxSizer(wx.HORIZONTAL)
    self.SetSizer(self.box)

    # Side boxsizer for buttons
    header0 = wx.StaticText(self, wx.ID_ANY, label="HSV Values:")
    ctrl_box = wx.BoxSizer(wx.VERTICAL)
    header1 = wx.StaticText(self, wx.ID_ANY, label="Brush Width:")
    # Textbox
    self.colors_textbox = wx.TextCtrl(self, wx.ID_ANY, self.get_formatted_hsv_string(), style=wx.TE_READONLY)
    self.colors_textbox.Bind(wx.EVT_TEXT, self.hsv_text_change)
    # Slider
    self.slider = wx.Slider(self, wx.ID_ANY, value=self.brush_radius, minValue=1, maxValue=50)
    self.slider.Bind(wx.EVT_SLIDER, self.update_radius)
    # Textbox for slider radius
    self.radius_textbox = wx.TextCtrl(self, wx.ID_ANY, str(self.brush_radius), style=wx.TE_READONLY)
    self.slider.Bind(wx.EVT_TEXT, self.dummy_handler)
    # Button
    camera_button = wx.Button(self, wx.ID_ANY, label="Take Picture")
    camera_button.Bind(wx.EVT_BUTTON, self.take_picture)
    # Instructions
    instructions = wx.StaticText(self, wx.ID_ANY, label= 
      "Brush over a color by clicking and dragging over the color you wish to use")

    # Add the widgets to the box
    ctrl_box.Add(header0)
    ctrl_box.Add(self.colors_textbox)
    ctrl_box.AddSpacer(10)
    ctrl_box.Add(header1)
    ctrl_box.Add(self.slider)
    ctrl_box.Add(self.radius_textbox)
    ctrl_box.AddSpacer(10)
    ctrl_box.Add(camera_button)
    ctrl_box.Add(instructions)

    # Image Panel
    self.img_panel = wx.Panel(self)
    self.img_panel.SetBackgroundColour('#4f5049')
    #self.load_image('webcam_capture.jpg') # comment out when done testing
    self.box.Add(self.img_panel)
    self.box.Add(ctrl_box)

    # Self Frame
    self.SetSize((800, 600))
    self.SetTitle('Calibrator')
    self.Centre()
    self.Show(True)
    
  def OnQuit(self, e):
    self.Close()

def main():
  calibrator_frame = wx.App()
  CalibratorFrame(None)
  calibrator_frame.MainLoop()

if __name__ == '__main__':
  main()