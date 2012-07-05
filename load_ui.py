#!/usr/bin/env python
import sys
import math
import numpy as np
import gobject, pygst
pygst.require('0.10')
import gst
from subprocess import Popen
import processor
import cPickle
from configobj import ConfigObj
from PyQt4 import QtCore, QtGui, uic
#from PyQt4.QtGui import QAction, QMainWindow, QWidget, QApplication, qApp, QIcon, QTextEdit, QMenu, QGridLayout, QPushButton, QGraphicsView, QGraphicsScene, qBlue, QPen, QRadioButton, QGroupBox, QButtonGroup, QPixmap, QSizePolicy, QPainter, QFont, QFrame, QPallete
from PyQt4.QtGui import *
from PyQt4.QtCore import QLine, QString, QObject, SIGNAL, QLineF, QRectF, QRect, QPoint, QPointF
form_class, base_class = uic.loadUiType("front_window2.ui")
from numpy import *
from PyQt4 import Qt
import PyQt4.Qwt5 as Qwt
#from pyqtgraph.graphicsItems import ImageItem
#import uc480
from CameraGraphicsView import CameraGraphicsView


#    def showEvent(self, event):
#        self.timer = self.startTimer(50)
#        self.counter = 0
#
#    def timerEvent(self, event):
#        self.counter += 1
#        self.update()
#        if self.counter == 60:
#            self.killTimer(self.timer)
#            self.hide()

def gray2qimage(gray):
    """Convert the 2D numpy array `gray` into a 8-bit QImage with a gray
    colormap.  The first dimension represents the vertical image axis.
    http://www.mail-archive.com/pyqt@riverbankcomputing.com/msg17961.html"""
    if len(gray.shape) != 2:
        raise ValueError("gray2QImage can only convert 2D arrays")

    gray = np.require(gray, np.uint8, 'C')

    h, w = gray.shape

    result = QtGui.QImage(gray.data, w, h, QtGui.QImage.Format_Indexed8)
    result.ndarray = gray
    for i in range(256):
        result.setColor(i, QtGui.QColor(i, i, i).rgb())
    return result

class AcquirerProcessor(QtCore.QThread):
    def __init__(self, config, parent=None):
        self.config = config
        QtCore.QThread.__init__(self, parent)

    def run(self):
        self.fd = open("raw_data")
        self.unipickler = cPickle.Unpickler(self.fd)
        while not self.fd.closed:
            try:
                self.data = self.unipickler.load()
            except Exception, e:
                self.fd.close()
                continue
            self.prev = self.data
            parameters = {"brightness":-00, "contrast":2}
            self.data = processor.process(self.data, parameters, self.config)
            self.emit(QtCore.SIGNAL("data_ready(PyQt_PyObject)"), self.data)

class OCT (QtGui.QMainWindow, form_class):
    def __init__(self,parent = None, selected = [], flag = 0, *args):
        QtGui.QWidget.__init__(self, parent, *args)
        self.setupUi(self)
        QObject.connect(self.start, SIGNAL("clicked()"), self.start_acquisition)
        QObject.connect(self.imagej, SIGNAL("clicked()"), self.image_j)
        self.config = processor.parse_config()
        self.setup_a_scan()
#        self.setup_camera()
        self.setup_tomography()
        self.setup_select_image()
        self.processed_data = []
        self.current_image = 0
        self.setup_show_scale()

    def setup_show_scale(self):
        QObject.connect(self.show_scale_checkbox, SIGNAL("stateChanged( int )"), self.show_scale_event)

    def show_scale_event(self):
        if self.show_scale_checkbox.isChecked():
            self.make_scale()
        else :
            self.remove_scale()

    def closeEvent(self, event):
        pass
#        self.camera_timer.stop()
#        self.camera_device.StopLiveVideo()
#        self.camera_device.FreeImageMem()
#        self.camera_device.ExitCamera()

    def image_j(self):
        filename = self.save_tiff(self.processed_data[self.current_image])
        import subprocess
        subprocess.Popen(["imagej", '-o', filename], stdout = subprocess.PIPE)

    def save_tiff(self, data):
        import Image
        data = data.T
        image = Image.frombuffer("L" ,data.shape ,data.data, 'raw', 'L', 0 ,1)
        import tempfile
        import os
        fd, filename = tempfile.mkstemp(suffix = ".tiff")
        with os.fdopen(fd, 'w') as fp:
            image.save(fp = fp, format = "tiff")
        return filename

    def setup_select_image(self):
        QObject.connect(self.select_image, SIGNAL("valueChanged( int )"), self.update_image)

    def setup_tomography(self):
        self.tomography_scene = QGraphicsScene(0,0,640,480)
        self.tomography_view.setScene(self.tomography_scene) 

        self.tomography_scene.mousePressEvent = self.tomography_pressed
        self.tomography_scene.mouseMoveEvent = self.tomography_pressed
#        self.make_scale()
        self.plot_in_tomography_view(np.zeros((480,640)))
        self.tomography_view.fitInView(QRectF(0,0,640,480), QtCore.Qt.KeepAspectRatio)
#        self.tomography_scene.mouseReleaseEvent = self.camera_released
    

    def make_scale(self):
        scene_rect = self.tomography_scene.sceneRect()
        bl = scene_rect.bottomRight()
        size = QtCore.QSizeF(scene_rect.width()/4,scene_rect.height()/20)
        self.scale_rect = QRectF(bl - QtCore.QPointF(size.width()+size.height(),size.height()*2), size)
        self.scale_item = self.tomography_scene.addRect(self.scale_rect, QPen(Qt.Qt.yellow, 1), QBrush(Qt.Qt.yellow, Qt.Qt.SolidPattern))

    def remove_scale(self):
        self.tomography_scene.removeItem(self.scale_item)

    def tomography_pressed(self, event):
        x = int(event.scenePos().x())
        if hasattr(self, "tomography_line_item"):
            self.tomography_scene.removeItem(self.tomography_line_item)
        yf = int(self.tomography_scene.sceneRect().top())
        y0 = int(self.tomography_scene.sceneRect().bottom())
        self.tomography_line_item = self.tomography_scene.addLine(x, y0, x, yf, QPen(Qt.Qt.yellow, 1, Qt.Qt.DotLine))
        if x >= self.current_tomography_data.shape[1]:
            x = self.current_tomography_data.shape[1] - 1
        elif x < 0:
            x = 0
        Y = self.current_tomography_data[:,x]
        X = np.linspace(10,0,len(Y))
        self.curve.setData(Y,X)
        self.plot.replot()

    def setup_a_scan(self):
        self.plot = Qwt.QwtPlot()
        size_policy = QSizePolicy()
        size_policy.setHorizontalStretch(1) 
        size_policy.setHorizontalPolicy(size_policy.Preferred) 
        size_policy.setVerticalPolicy(size_policy.Preferred) 
        self.plot.setSizePolicy(size_policy)
#        self.plot.enableAxis(Qwt.QwtPlot.yLeft, False)
        self.plot.enableAxis(Qwt.QwtPlot.xBottom, False)

        grid = Qwt.QwtPlotGrid()
        grid.attach(self.plot)
        grid.setPen(Qt.QPen(Qt.Qt.white, 0, Qt.Qt.DotLine))
        self.plot.setCanvasBackground(Qt.Qt.black)
        self.plot_holder_widget.children()[0].addWidget(self.plot)

        self.curve = Qwt.QwtPlotCurve()
        self.curve.attach(self.plot)
        self.curve.setPen(Qt.QPen(Qt.Qt.green, 1))

    def update_image(self, index):
        self.current_image = index - 1
        self.plot_in_tomography_view(self.processed_data[self.current_image])
        
    def setup_camera(self):
        self.camera_view = CameraGraphicsView()
        self.widget_7.children()[0].addWidget(self.camera_view)

        self.camera_scene = QGraphicsScene()
        self.camera_view.setScene(self.camera_scene)
        self.camera_scene.mousePressEvent = self.camera_pressed
        self.camera_scene.mouseMoveEvent = self.camera_moved
        self.camera_scene.mouseReleaseEvent = self.camera_released
        self.scan_type = 'continuous'
        QObject.connect(self.d2, SIGNAL('clicked()'), self.change_selector) 
        QObject.connect(self.d3, SIGNAL('clicked()'), self.change_selector) 
        self.d2.click()
        self.camera_device = uc480.camera(1)
        self.camera_device.AllocImageMem()
        self.camera_device.SetImageMem()
        self.camera_device.SetImageSize()
        self.camera_device.SetColorMode()
        self.camera_device.CaptureVideo()
        self.camera_timer = QtCore.QTimer()
        self.connect(self.camera_timer, QtCore.SIGNAL("timeout()"), self.update_camera_image_timer)
        self.update_camera_image()
        self.camera_timer.start(500)

    def update_camera_image(self):
        if hasattr(self,"camera_pixmap"):
            self.camera_scene.removeItem(self.camera_pixmap)
        self.camera_device.CopyImageMem()
        self.camera_image = gray2qimage(self.camera_device.data)
        pixmap_image = QtGui.QPixmap.fromImage(self.camera_image)
        self.camera_pixmap = self.camera_scene.addPixmap(pixmap_image)
        if hasattr(self, 'item'):
            self.camera_pixmap.stackBefore(self.item)
        self.camera_scene.setSceneRect(self.camera_pixmap.boundingRect())
        self.camera_view.fitInView(self.camera_pixmap, QtCore.Qt.KeepAspectRatio)

    def update_camera_image_timer(self):
        self.update_camera_image()
        self.camera_timer.start(500)

    def change_selector(self):
        if self.d2.isChecked():
            self.scan_type = "continuous"
            self.selector = lambda start, end: self.camera_scene.addLine(QLineF(start, end))
        else:
            self.scan_type = "3D"
            self.selector = self.select_rect
#            self.selector = lambda start, end: self.camera_scene.addRect(QRectF(start, end))

    def area_select(self, start, end):
        return self.camera_scene.addRect(QRectF(start, end))

    def camera_pressed(self, event):
        self.pressed_pos = event.scenePos()
        self.camera_moved(event)

    def update_config_path(self, start, end):
        start = self.convert_to_path(start)
        end = self.convert_to_path(end)
        self.config[self.scan_type]['x0'] = start.x() 
        self.config[self.scan_type]['y0'] = start.y() 
        self.config[self.scan_type]['xf'] = start.x() 
        self.config[self.scan_type]['yf'] = start.y() 

    def convert_to_path(self, point):
        scale = self.config['camera_to_path_scale']
        return point*scale

    def fix_rect_points(self, A, B):
        x0 = min([A.x(), B.x()])
        xf = max([A.x(), B.x()])
        y0 = min([A.y(), B.y()])
        yf = max([A.y(), B.y()])
        return QPointF(x0, y0), QPointF(xf, yf)

    def camera_moved(self, event):
        if hasattr(self, "item"):
            self.camera_scene.removeItem(self.item)
#        start, end = self.fix_rect_points(self.pressed_pos, event.scenePos())
        start, end = self.pressed_pos, event.scenePos()
        self.item = self.selector(start, end)

    def camera_released(self, event):
        if hasattr(self, "item"):
            self.camera_scene.removeItem(self.item)
        self.released_pos = event.scenePos()
#        start, end = self.fix_rect_points(self.pressed_pos, event.scenePos())
        start, end = self.pressed_pos, event.scenePos()
        self.update_config_path(start, end)
        self.item = self.selector(start, end)

    def select_rect(self, start, end):
        start, end = self.fix_rect_points(start, end)
        return self.camera_scene.addRect(QRectF(start, end))

    def save_processed_data(self, filename):
        import h5py
        file = h5py.File(filename, 'w')
        root = file.create_group("root")
        for i, image in enumerate(self.processed_data):
            root.create_dataset('image_%03d'%i, image.shape, image.dtype) 
        file.close()

    def plot_in_tomography_view(self, data):
        self.image.updateImage(data)
        self.tomography.fitInView(self.image, QtCore.Qt.KeepAspectRatio)
        self.processed_data += [data]
        n_images = len(self.processed_data)
        self.current_image = n_images - 1
        self.select_image.setMaximum(n_images)


    def start_acquisition(self):
        from subprocess import Popen 
        self.acquisition = Popen(["python","image_generator.py",
                                  "-a","--count=10","--rate=25",
                                  "--height=480", "--width=640"],)
        self.start_prev()
        
if __name__ == '__main__':
    app = QtGui.QApplication(sys.argv)
    main_window = OCT()
    main_window.show()
    app.exec_()
