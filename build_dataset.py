# USAGE
# python build_dataset.py

# import the necessary packages
from pyimagesearch.iou import compute_iou
from pyimagesearch import config
from bs4 import BeautifulSoup
from imutils import paths
import cv2
import os
import tqdm
import imutils

# loop over the output positive and negative directories
for dirPath in ( [config.NEGATIVE_PATH]): #config.POSITVE_PATH,
	# if the output directory does not exist yet, create it
	if not os.path.exists(dirPath):
		os.makedirs(dirPath)

# grab all image paths in the input images directory
imagePaths = list(paths.list_images(config.ORIG_IMAGES))

# initialize the total number of positive and negative images we have
# saved to disk so far
totalPositive = 0
totalNegative = 0

# loop over the image paths
for (i, imagePath) in tqdm.tqdm(enumerate(imagePaths[:])):
	# show a progress report
	print("[INFO] processing image {}/{}...".format(i + 1,
		len(imagePaths)))

	# extract the filename from the file path and use it to derive
	# the path to the XML annotation file
	filename = imagePath.split(os.path.sep)[-1]
	filename = filename[:filename.rfind(".")]
	annotPath = os.path.sep.join([config.ORIG_ANNOTS,
		"{}.xml".format(filename)])

	if not os.path.exists(annotPath):
		print(f"No such file or directory:{annotPath}")
		continue

	# load the annotation file, build the soup, and initialize our
	# list of ground-truth bounding boxes
	contents = open(annotPath).read()
	soup = BeautifulSoup(contents, "html.parser")
	gtBoxes = []

	# extract the image dimensions
	w = int(soup.find("width").string)
	h = int(soup.find("height").string)

	# loop over all 'object' elements
	for o in soup.find_all("object"):
		# extract the label and bounding box coordinates
		label = o.find("name").string
		if label == "container_small":				
			print(f"{imagePath} contains  container_small")
			continue
		print(label)
		xMin = int(o.find("xmin").string)
		yMin = int(o.find("ymin").string)
		xMax = int(o.find("xmax").string)
		yMax = int(o.find("ymax").string)

		# truncate any bounding box coordinates that may fall
		# outside the boundaries of the image
		xMin = max(0, xMin)
		yMin = max(0, yMin)
		xMax = min(w, xMax)
		yMax = min(h, yMax)

		# update our list of ground-truth bounding boxes
		gtBoxes.append((label, (xMin, yMin, xMax, yMax)))

	# load the input image from disk
	image = cv2.imread(imagePath)
	h, w, _ = image.shape
	image = imutils.resize(image, width=500)
	h_new, w_new, _ = image.shape
	h_fact = h/h_new
	w_fact = w/w_new
	# run selective search on the image and initialize our list of
	# proposed boxes
	print("1a")
	ss = cv2.ximgproc.segmentation.createSelectiveSearchSegmentation()
	print("1b")
	ss.setBaseImage(image)
	ss.switchToSelectiveSearchFast()
	rects = ss.process()
	proposedRects= []
	print("1c")
	# loop over the rectangles generated by selective search
	for (x, y, w, h) in rects:
		# convert our bounding boxes from (x, y, w, h) to (startX,
		# startY, startX, endY)
		proposedRects.append((x, y, x + w, y + h))

	# initialize counters used to count the number of positive and
	# negative ROIs saved thus far
	positiveROIs = 0
	negativeROIs = 0
	# loop over the maximum number of region proposals
	for proposedRect in proposedRects[:config.MAX_PROPOSALS]:
		# unpack the proposed rectangle bounding box
		(propStartX, propStartY, propEndX, propEndY) = proposedRect

		# loop over the ground-truth bounding boxes
		for label, gtBox in gtBoxes:
			
			# compute the intersection over union between the two
			# boxes and unpack the ground-truth bounding box
			(gtStartX, gtStartY, gtEndX, gtEndY) = gtBox
			(gtStartX, gtStartY, gtEndX, gtEndY) = (int(gtStartX/w_fact), int(gtStartY/h_fact), int(gtEndX/w_fact), int(gtEndY/h_fact))
			gtBox = (gtStartX, gtStartY, gtEndX, gtEndY)
			iou = compute_iou(gtBox, proposedRect)
			# (gtStartX, gtStartY, gtEndX, gtEndY) = gtBox
			# print((gtStartX, gtStartY, gtEndX, gtEndY))
			# (gtStartX, gtStartY, gtEndX, gtEndY) = (int(gtStartX/w_fact), int(gtStartY/h_fact), int(gtEndX/w_fact), int(gtEndY/h_fact))
			# print((gtStartX, gtStartY, gtEndX, gtEndY))
			
			# initialize the ROI and output path
			roi = None
			outputPath = None

			# check to see if the IOU is greater than 70% *and* that
			# we have not hit our positive count limit
			if iou > 0.7 and positiveROIs <= config.MAX_POSITIVE:
				# extract the ROI and then derive the output path to
				# the positive instance
				print("positiveROIs", positiveROIs, config.MAX_POSITIVE)
				roi = image[propStartY:propEndY, propStartX:propEndX]
				filename_new = "{}_{}.png".format(filename, totalPositive)
				PATH_LABEL = os.path.sep.join([config.BASE_PATH, label])
				os.makedirs(PATH_LABEL, exist_ok=True)
				outputPath = os.path.sep.join([PATH_LABEL, #config.POSITVE_PATH
					filename_new])

				# increment the positive counters
				positiveROIs += 1
				totalPositive += 1
			
			# determine if the proposed bounding box falls *within*
			# the ground-truth bounding box
			fullOverlap = propStartX >= gtStartX
			fullOverlap = fullOverlap and propStartY >= gtStartY
			fullOverlap = fullOverlap and propEndX <= gtEndX
			fullOverlap = fullOverlap and propEndY <= gtEndY

			# check to see if there is not full overlap *and* the IoU
			# is less than 5% *and* we have not hit our negative
			# count limit
			if not fullOverlap and iou < 0.05 and \
				negativeROIs < config.MAX_NEGATIVE:
				# extract the ROI and then derive the output path to
				# the negative instance
				print(negativeROIs, config.MAX_NEGATIVE)
				roi = image[propStartY:propEndY, propStartX:propEndX]
				filename_new = "{}_{}.png".format(filename, totalNegative)
				outputPath = os.path.sep.join([config.NEGATIVE_PATH,
					filename_new])

				# increment the negative counters
				negativeROIs += 1
				totalNegative += 1

			# check to see if both the ROI and output path are valid
			if roi is not None and outputPath is not None:
				# resize the ROI to the input dimensions of the CNN
				# that we'll be fine-tuning, then write the ROI to
				# disk
				roi = cv2.resize(roi, config.INPUT_DIMS,
					interpolation=cv2.INTER_CUBIC)
				cv2.imwrite(outputPath, roi)