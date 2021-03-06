import os
import unittest
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
import logging
import numpy as np
from functools import partial


#
# ColourObjectTracker
#

class ColourObjectTracker(ScriptedLoadableModule):

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Colour Object Tracker" # TODO make this more human readable by adding spaces
    self.parent.categories = ["Examples"]
    self.parent.dependencies = []
    self.parent.contributors = ["Zachary Baum (PerkLab)"] # replace with "Firstname Lastname (Organization)"
    self.parent.helpText = """
    Scripted module to use webcam for tracking coloured objects.
    """
    self.parent.acknowledgementText = """
    This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc.
    and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
""" # replace with organization, grant and thanks.

#
# ColourObjectTrackerWidget
#

class ColourObjectTrackerWidget(ScriptedLoadableModuleWidget):

  def setup(self):
    ScriptedLoadableModuleWidget.setup(self)

    # Instantiate and connect widgets ...

    #
    # Parameters Area
    #
    parametersCollapsibleButton = ctk.ctkCollapsibleButton()
    parametersCollapsibleButton.text = "Parameters"
    self.layout.addWidget(parametersCollapsibleButton)

    # Layout within the dummy collapsible button
    parametersFormLayout = qt.QFormLayout(parametersCollapsibleButton)

    #
    # Start Server / Launch Webcam Button
    #
    self.startWebcamButton = qt.QPushButton("Start Webcam")
    self.startWebcamButton.enabled = True
    parametersFormLayout.addRow(self.startWebcamButton)

    #
    # ColorPicker Buttons
    #
    self.startColorPickButton = qt.QPushButton("Show ROI")
    self.startColorPickButton.enabled = True
    self.colorPickButton = qt.QPushButton("Pick Object Color")
    self.colorPickButton.enabled = True
    hbox = qt.QHBoxLayout()
    hbox.addWidget(self.startColorPickButton)
    hbox.addWidget(self.colorPickButton)
    parametersFormLayout.addRow(hbox)

    #
    # Apply Button
    #
    self.startButton = qt.QPushButton("Start")
    self.startButton.enabled = True
    self.stopButton = qt.QPushButton("Stop")
    self.stopButton.enabled = True
    hbox = qt.QHBoxLayout()
    hbox.addWidget(self.startButton)
    hbox.addWidget(self.stopButton)
    parametersFormLayout.addRow(hbox)

    #
    # Output Table
    #
    parametersFormLayout.addRow(qt.QLabel(''))
    parametersFormLayout.addRow(qt.QLabel('Tracked Objects'))
    self.objectsTable = qt.QTableWidget()
    self.objectsTable.setRowCount(0)
    self.objectsTable.setColumnCount(5)
    self.objectsTable.setSizePolicy(qt.QSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Expanding))
    self.objectsTable.horizontalHeader().setResizeMode(0, qt.QHeaderView.Stretch)
    self.objectsTable.horizontalHeader().setResizeMode(1, qt.QHeaderView.Fixed)
    self.objectsTable.horizontalHeader().resizeSection(1, 100)
    self.objectsTable.setHorizontalHeaderLabels(["Object Name","Found", "Shape", "Color", "Delete"])
    parametersFormLayout.addRow(self.objectsTable)

    # connections
    self.startWebcamButton.connect('clicked(bool)', self.onWebcamButton)
    self.startColorPickButton.connect('clicked(bool)', self.onStartColorPickButton)
    self.colorPickButton.connect('clicked(bool)', self.onPickColorButton)
    self.startButton.connect('clicked(bool)', self.onStartButton)
    self.stopButton.connect('clicked(bool)', self.onStopButton)

    # Add vertical spacer
    self.layout.addStretch(1)

    # Refresh Apply button state
    self.onSelect()

    self.logic = ColourObjectTrackerLogic()

  def cleanup(self):
    pass


  def onSelect(self):
    self.startWebcamButton.enabled = True


  def onStartButton(self):
    self.logic.run()


  def onStopButton(self):
    self.logic.stop()


  def onWebcamButton(self):
    self.logic.startWebcam()


  def onPickColorButton(self):
    self.logic.pickColor()


  def onStartColorPickButton(self):
    self.logic.startPickColor()

#
# ColourObjectTrackerLogic
#

class ColourObjectTrackerLogic(ScriptedLoadableModuleLogic):

  trackedObjectDict = {}
  numberOfTrackedObjects = 0
  currentTrackedObjects = 0

  def getVtkImageDataAsOpenCVMat(self, volumeNodeName):
    cameraVolume = slicer.util.getNode(volumeNodeName)
    image = cameraVolume.GetImageData()
    shape = list(cameraVolume.GetImageData().GetDimensions())
    shape.reverse()
    components = image.GetNumberOfScalarComponents()
    if components > 1:
      shape.append(components)
      shape.remove(1)
    imageMat = vtk.util.numpy_support.vtk_to_numpy(image.GetPointData().GetScalars()).reshape(shape)

    return imageMat


  def getOpenCVMatAsVtkImageData(self, imageMat):
    imageMat = np.rot90(imageMat, 1)
    imageMat = np.flipud(imageMat)
    
    destinationArray = vtk.util.numpy_support.numpy_to_vtk(imageMat.transpose(2, 1, 0).ravel(), deep = True)
    destinationImageData = vtk.vtkImageData()    
    destinationImageData.SetDimensions(imageMat.shape)
    destinationImageData.GetPointData().SetScalars(destinationArray)

    return destinationImageData


  def createWebcamPlusConnector(self):
    webcamConnectorNode = slicer.util.getNode('WebcamPlusConnector')
    if not webcamConnectorNode:
      webcamConnectorNode = slicer.vtkMRMLIGTLConnectorNode()
      webcamConnectorNode.SetLogErrorIfServerConnectionFailed(False)
      webcamConnectorNode.SetName('WebcamPlusConnector')
      slicer.mrmlScene.AddNode(webcamConnectorNode)
      webcamConnectorNode.SetTypeClient('localhost', 18944)
      logging.debug('Webcam PlusConnector Created')
    webcamConnectorNode.Start()


  def onWebcamImageModified(self, caller, eventid):
    import cv2
    
    # Get the vtkImageData as an np.array.
    imData = self.getVtkImageDataAsOpenCVMat('Image_Reference')
    
    for trackedObjectNumber in range(self.numberOfTrackedObjects):
      trackedObject = self.trackedObjectDict[trackedObjectNumber]

      # Go through each of the boundaries defined and combine the binary images with the original.
      for (lower, upper) in trackedObject.boundaries:
        lower = np.array(lower, dtype = 'uint8')
        upper = np.array(upper, dtype = 'uint8')

        mask = cv2.inRange(imData, lower, upper)
        output = cv2.bitwise_and(imData, imData, mask = mask)

      # Make everything monochrome and threshold
      imgray = cv2.cvtColor(output, cv2.COLOR_RGB2GRAY)
      ret, thresh = cv2.threshold(imgray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

      nonZero = np.ndarray.nonzero(thresh)
      if nonZero is not np.array([]):
        sigma = np.cov(nonZero)
        if not np.isnan(sigma).any():
          evals, evecs = np.linalg.eig(sigma)
          sortedEvals = np.sort(evals)
          lenRatio = sortedEvals[1] / sortedEvals[0]

          trackedObject.found = "YES"
          if lenRatio > 5:
            trackedObject.shape = 'LINEAR'
          else: 
            trackedObject.shape = 'SQUARE'
        else:
          trackedObject.found = "NO"
          trackedObject.shape = 'NONE'

      # Find the contours and draw them out to the to the original image.
      # The first contour fills the generated lines, second enhances the edges of the contour.
      im2, contours, hierarchy = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

      contourColor = (255 - trackedObject.color[0],
                      255 - trackedObject.color[1],
                      255 - trackedObject.color[2])
      cv2.drawContours(imData, contours, -1, contourColor, thickness = -1, maxLevel = 2)
      cv2.drawContours(imData, contours, -1, contourColor, thickness = 2, maxLevel = 2)

      self.updateTrackedObjectInTable(trackedObject, trackedObjectNumber)


  def onDrawBox(self, caller, eventid):
    import cv2
    
    # Get the vtkImageData as an np.array.
    imData = self.getVtkImageDataAsOpenCVMat('Image_Reference')
    self.x = imData.shape[1] / 2
    self.y = imData.shape[0] / 2
    self.w = 25
    self.h = 25

    cv2.rectangle(imData, (self.x - self.w, self.y - self.h), (self.x + self.w, self.y + self.h), (255, 0, 0), 2)


  def getImageColorBoundaries(self):
    import cv2
    
    # Get the vtkImageData as an np.array.
    imData = self.getVtkImageDataAsOpenCVMat('Image_Reference')
    valList = []
    red = 0
    blue = 0
    green = 0
    numPx = 0

    for i in xrange(self.x - self.w, self.x + self.w, 10):
      for j in xrange(self.y - self.h, self.y + self.h, 10):

        value = imData[i, j]
        #lower = [x - 20 if (x - 20) >= 0 else 0 for x in value]
        #upper = [x + 20 if (x + 20) <= 255 else 255 for x in value]
        #valList.append((lower, upper))

        red += value[0]
        green += value[1]
        blue += value[2]
        numPx += 1

    avgValue = [red/numPx, green/numPx, blue/numPx]
    lower = [x - 20 if (x - 20) >= 0 else 0 for x in avgValue]
    upper = [x + 20 if (x + 20) <= 255 else 255 for x in avgValue]
    valList = [(lower, upper)]

    return valList
    

  def startWebcam(self):
    self.webcamImageVolume = slicer.util.getNode('Image_Reference')
    if not self.webcamImageVolume:
      imageSpacing = [0.2, 0.2, 0.2]
      imageData = vtk.vtkImageData()
      imageData.SetDimensions(640, 480, 1)
      imageData.AllocateScalars(vtk.VTK_UNSIGNED_CHAR, 1)
      thresholder = vtk.vtkImageThreshold()
      thresholder.SetInputData(imageData)
      thresholder.SetInValue(0)
      thresholder.SetOutValue(0)
      # Create volume node
      self.webcamImageVolume = slicer.vtkMRMLVectorVolumeNode()
      self.webcamImageVolume.SetName('Image_Reference')
      self.webcamImageVolume.SetSpacing(imageSpacing)
      self.webcamImageVolume.SetImageDataConnection(thresholder.GetOutputPort())
      # Add volume to scene
      slicer.mrmlScene.AddNode(self.webcamImageVolume)
      displayNode = slicer.vtkMRMLVectorVolumeDisplayNode()
      slicer.mrmlScene.AddNode(displayNode)
      self.webcamImageVolume.SetAndObserveDisplayNodeID(displayNode.GetID())

    self.createWebcamPlusConnector()
    redWidget = slicer.app.layoutManager().sliceWidget('Red')
    redWidget.setSliceOrientation('Axial')
    redWidget.sliceLogic().GetSliceCompositeNode().SetBackgroundVolumeID(self.webcamImageVolume.GetID())
    redWidget.sliceLogic().FitSliceToAll()


  def startPickColor(self):
    self.drawBoxObserver = self.webcamImageVolume.AddObserver(slicer.vtkMRMLVolumeNode.ImageDataModifiedEvent, self.onDrawBox)


  def addTrackedObjectToTable(self, trackedObject, row):
    self.widget.objectsTable.setRowCount(row + 1)
    self.widget.objectsTable.setItem(row, 0, qt.QTableWidgetItem(trackedObject.name))
    self.widget.objectsTable.setItem(row, 1, qt.QTableWidgetItem(trackedObject.found))
    self.widget.objectsTable.setItem(row, 2, qt.QTableWidgetItem(trackedObject.shape))
    self.widget.objectsTable.setItem(row, 3, qt.QTableWidgetItem(''))
    self.widget.objectsTable.item(row, 3).setBackground(qt.QColor(trackedObject.color[0], trackedObject.color[1], trackedObject.color[2]))
    deleteObjectTableButton = qt.QPushButton()
    deleteObjectTableButton.setIcon(qt.QIcon(":/Icons/MarkupsDelete.png"))
    deleteObjectTableButton.connect('clicked()', partial(self.removeTrackedObjectFromTable, trackedObject))
    self.widget.objectsTable.setCellWidget(row, 4, deleteObjectTableButton)


  def updateTrackedObjectInTable(self, trackedObject, objectNumber):
    self.widget.objectsTable.setItem(objectNumber, 1, qt.QTableWidgetItem(trackedObject.found))
    self.widget.objectsTable.setItem(objectNumber, 2, qt.QTableWidgetItem(trackedObject.shape))


  def removeTrackedObjectFromTable(self, trackedObject):
    for row in range(self.widget.objectsTable.rowCount):
      if str(self.widget.objectsTable.item(row, 0).text()) == trackedObject.name:
        self.widget.objectsTable.removeRow(row)
        break

    keys = [key for (key, value) in self.trackedObjectDict.iteritems() if value == trackedObject]
    del self.trackedObjectDict[keys[0]]
    self.currentTrackedObjects -= 1

    #for key in self.trackedObjectDict:
    #  if key > keys[0]
    #  self.addTrackedObjectToTable(self.trackedObjectDict[key], row)



  def pickColor(self):
    self.widget = slicer.modules.ColourObjectTrackerWidget
    self.webcamImageVolume.RemoveObserver(self.drawBoxObserver)
    
    trackedObject = TrackedObject('TrackedObject_' + str(self.numberOfTrackedObjects), self.getImageColorBoundaries())
    self.addTrackedObjectToTable(trackedObject, self.currentTrackedObjects)
    self.trackedObjectDict[self.numberOfTrackedObjects] = trackedObject
    self.numberOfTrackedObjects += 1
    self.currentTrackedObjects += 1

    self.boundaries = self.getImageColorBoundaries()


  def run(self):
    import cv2
    self.widget = slicer.modules.ColourObjectTrackerWidget
    self.webcamImageVolume = slicer.util.getNode('Image_Reference')
    self.imageDataModifiedObserver = self.webcamImageVolume.AddObserver(slicer.vtkMRMLVolumeNode.ImageDataModifiedEvent, self.onWebcamImageModified)
    

  def stop(self):
    self.webcamImageVolume.RemoveObserver(self.imageDataModifiedObserver)    


class ColourObjectTrackerTest(ScriptedLoadableModuleTest):

  def setUp(self):
    slicer.mrmlScene.Clear(0)


  def runTest(self):
    self.setUp()
    self.test_ColourObjectTracker1()


  def test_ColourObjectTracker1(self):
    return 1


class TrackedObject:

  def __init__(self, name, boundaries):
    self.boundaries = boundaries
    self.name = name
    self.found = 'NO'
    self.shape = 'NONE'
    self.color = (self.boundaries[0][0][0] + 20,
                  self.boundaries[0][0][1] + 20,
                  self.boundaries[0][0][2] + 20)

  def __repr__(self):
    return str(self.name + ' ' + self.found + ' ' + self.shape + ' ' + str(self.color))