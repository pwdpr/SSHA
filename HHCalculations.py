#hydraulic and hydrologic calculation tools

import arcpy
from arcpy import env
import math
import Working_RC_Calcs
import ssha_tools
import utils
import os
#import hhcalcs

# ====================
# HYDRUALIC EQUATIONS
# ====================

#define default hydraulic params
default_min_slope = 0.01 # percent - assumed when slope is null
default_TC_slope = 5.0 # percent - conservatively assumed for travel time calculation when slope
pipeSizesAvailable = [18,21,24,27,30,36,42,48,54,60,66,72,78,84] #circular pipe sizes in inches


def getMannings( shape, diameter ):
	n = 0.015 #default value
	if ((shape == "CIR" or shape == "CIRCULAR") and (diameter <= 24) ):
		n = 0.015
	elif ((shape == "CIR" or shape == "CIRCULAR") and (diameter > 24) ):
		n = 0.013
	return n

def xarea( shape, diameter, height, width ):
	#calculate cross sectional area of pipe
	#supports circular, egg, and box shape
	if (shape == "CIR" or shape == "CIRCULAR"):
		return 3.1415 * (math.pow((diameter/12.0),2.0 ))/4.0
	elif (shape == "EGG" or shape == "EGG SHAPE"):
		return 0.5105* math.pow((height/12.0),2.0 )
	elif (shape == "BOX" or shape == "BOX SHAPE"):
		return height*width/144.0

def  minSlope( slope ):
	#replaces null slope value with the assumed minimum 0.01%
	if slope == None:
		return 0.01
	else:
		return slope

def hydraulicRadius(shape, diameter, height, width ):
	#calculate full flow hydraulic radius of pipe
	#supports circular, egg, and box shape
	if (shape == "CIR" or shape == "CIRCULAR"):
		return (diameter/12.0)/4.0
	elif (shape == "EGG" or shape == "EGG SHAPE"):
		return 0.1931* (height/12.0)
	elif (shape == "BOX" or shape == "BOX SHAPE"):
		return (height*width) / (2.0*height + 2.0*width) /12.0

def minSlopeRequired (shape, diameter, height, width, peakQ) :

	minV = 2.5 #ft/s
	maxV = 15.0 #ft/s

	try:
		n = getMannings(shape, diameter)
		A = xarea(shape, diameter, height, width)
		Rh = hydraulicRadius(shape, diameter, height, width )

		s =  math.pow( (n * peakQ) / ( 1.49 * A * math.pow(Rh, 0.667) ), 2)
		s = math.ceil(s*10000.0)/10000.0 #round up to nearest 100th of a percent

		s_min_v = math.pow( (n*minV) / (1.49 * math.pow(Rh, 0.667) ) , 2) #lower bound slope based on minimum pipe velocity
		s_max_v = math.pow( (n*maxV) / (1.49 * math.pow(Rh, 0.667) ) , 2) #upper bound slope based on maximum pipe velocity

		#limit slope to bounds based on settling and scouring velocities
		s = max(s, s_min_v)
		s = min(s, s_max_v)

		return round(s*100.0, 2) #percent, round here to fix weird floating point inaccuracy

	except TypeError:
		arcpy.AddWarning("Type error on pipe ")
		return 0.0

def manningsCapacity(diameter, slope, height=None, width=None, shape="CIR"):

	#compute mannings flow in full pipe
	A = xarea(shape, diameter, height, width)
	Rh = hydraulicRadius(shape, diameter, height, width)
	n = getMannings(shape, diameter)
	k = (1.49 / n) * math.pow(Rh, 0.667) * A

	Q = k * math.pow(slope/100.0, 0.5)

	return Q

def minimumEquivalentCircularPipe(peakQ, slope):

	#return the minimum ciruclar pipe diameter required to convey a given Q peak
	for D in pipeSizesAvailable:
		q = manningsCapacity(diameter=D, slope=slope, shape="CIR")
		if q > peakQ: return D


def determineSymbologyTag(missingData, isTC, isSS, calculatedSlope, minSlopeAssumed):

	flag = None #this is fucking stupid

	if (isSS):
		#flags about study sewers (SS)
		flag = "SS"
		if missingData: flag = "SS_UNDEFINED"
		if calculatedSlope: flag = "SS_CALC_SLOPE"
		if minSlopeAssumed: flag = "SS_MIN_SLOPE"

	elif (isTC):
		flag = "TC"
		if missingData: flag = "TC_UNDEFINED"
		if calculatedSlope: flag = "TC_CALC_SLOPE"
		if minSlopeAssumed: flag = "TC_MIN_SLOPE"

	return flag

def checkPipeYN (pipeValue):
	#return boolean based on TC and Study Sewer flag
	if (pipeValue == "Y"): return True
	else: return False

def applyDefaultFlags(study_pipes_cursor):

	for pipe in study_pipes_cursor:

		#print(pipe.getValue("OBJECTID"))
		#during the first run through, should apply these default flags, and skip all other calcs
		pipe[1] = 'N' # pipe.setValue("TC_Path", "N")
		pipe[2] = 'N' # pipe.setValue("StudySewer", "N")
		pipe[3] = 'None' # pipe.setValue("Tag", "None")
		study_pipes_cursor.updateRow(pipe)

	del study_pipes_cursor

def minimumCapacityStudySewer(sewers_layer, study_area_id):

	"""
	Return the minimum study sewer capacity in a given study area.

	this fails when processing a studyarea_id with none of the sewers tagged
	with StudySewer = "Y"
	"""
	#search cursor on study sewers in ascending order on capacity
	where = "StudyArea_ID = '{}' AND StudySewer = 'Y'".format(study_area_id)
	sort = (None, 'ORDER BY Capacity ASC')
	# fs ="Capacity; OBJECTID; STICKERLINK; Year_Installed; PIPESHAPE; Diameter; Height; Width;Slope_Used;LABEL;Label_Tag;SHEDNAME"
	fields = ['Capacity', 'OBJECTID', 'STICKERLINK', 'Year_Installed',
			'PIPESHAPE', 'Diameter', 'Height', 'Width','Slope_Used',
			'LABEL','SHEDNAME','Label_Tag']

	#sewers_layer = r'C:\Data\Code\HydraulicStudiesDevEnv\Small_Sewer_Capacity.gdb\StudiedWasteWaterGravMains'
	arcpy.AddMessage('where = {}'.format(where))

	with arcpy.da.UpdateCursor(sewers_layer, fields,
								where, sql_clause = sort) as sewer_cursor:

		#arcpy.AddMessage('sewer_cursor len	: {}'.format( len([row for row in sewer_cursor]) ))

		#return first value, being the minimum capacity
		for s in sewer_cursor:
			arcpy.AddMessage('min pipe searching {}'.format(s[1]))
			#grab values
			capacity 		= s[0] #pipe.getValue("Capacity")
			id 				= s[1] #pipe.getValue("OBJECTID")
			sticker_link 	= s[2] #pipe.getValue("STICKERLINK")
			intall_year 	= s[3] #pipe.getValue("Year_Installed")
			Shape 			= s[4] #pipe.getValue("PIPESHAPE")
			D 				= s[5] #pipe.getValue("Diameter")
			H 				= s[6] #pipe.getValue("Height")
			W 				= s[7] #pipe.getValue("Width")
			slope			= s[8] #pipe.getValue("Slope_Used")
			label			= s[9] #pipe.getValue("LABEL")
			shed			= s[10] #pipe.getValue("SHEDNAME")

			#assign tag for labeling purposes
			s[11] = 'LimitingSewer' #pipe.setValue("Label_Tag", "LimitingSewer")
			sewer_cursor.updateRow(s)

			break #move on after first iteration

		try:
			# if the no StudySewer tags are "Y", the query returns nothing, and
			# these variables are not assigned
			return {'capacity':capacity,
					'id':id, 'sticker_link':sticker_link,
					'intall_year':intall_year,
					'D':D, 'H':H, 'W':W,
					'Shape':Shape, 'Slope':slope,
					'Label':label, 'Shed':shed}

		except:
			arcpy.AddWarning("Minimum capacity sewer not found in {}".format(study_area_id))
			arcpy.AddWarning("Did you tag the StudySewers in that Study Area?")


# ====================
# HYDROLOGIC EQUATIONS
# ====================

def timeOfConcentration(studypipes, study_area_id):
	#Return the time of concentration in a given study area
	#search cursor on study sewers in ascending order on capacity
	where = "StudyArea_ID = '" + study_area_id + "' AND TC_Path = 'Y'"
	pipesCursor = arcpy.SearchCursor(studypipes, where_clause = where, fields="TravelTime_min; OBJECTID")


	tc = 3.0000 #set the initial tc to 3 minutes
	for pipe in pipesCursor:
		#print(pipe.getValue("TravelTime_min"))
		tc += float(pipe.getValue("TravelTime_min") or 0) #the 'float or 0' handles null values

	del pipesCursor
	return round(tc, 2)


def phillyStormPeak (tc, area, C):

	#computes peak based on TC, Philly intensity, runoff C, and area in acres
	I = 116 / ( tc + 17)
	return round(C * I * area, 2) #CFS


#iterate through each DA within a given project and sum the TCs with their DrainageArea_ID
#drainage_areas_cursor = arcpy.UpdateCursor(DAs, where_clause = "Project_ID = " + project_id)
def run_hydrology(project_id, study_sewers, study_areas, study_area_id=None):

	"""
	run hydrologic calculations on a set of study areas within a project_id
	scope (or optionally a single study area scope)
	"""

	where = utils.where_clause_from_user_input(project_id, study_area_id)
	arcpy.AddMessage("where hydrol = {}\nenv = {}".format(where, arcpy.env.workspace))
	drainage_areas_cursor = arcpy.UpdateCursor(study_areas, where_clause = where)

	for drainage_area in drainage_areas_cursor:

		#work with each study area and determine the pipe calcs based on study area id
		study_area_id = drainage_area.getValue("StudyArea_ID")
		project_id = drainage_area.getValue("Project_ID")

		#CALCULATIONS ON TC PATH PIPES
		tc = timeOfConcentration(study_sewers, study_area_id)

		#find limiting pipe in study area
		arcpy.AddMessage("minimumCapacityStudySewer({},{})".format(study_sewers, study_area_id))
		limitingSewer = minimumCapacityStudySewer(study_sewers, study_area_id)
		# capacity = limitingSewer['capacity']
		arcpy.AddMessage("min slope={}, id={}".format(limitingSewer['Slope'], id))

		#RUNOFF CALCULATIONS
		C = drainage_area.getValue("Runoff_Coefficient")
		#C = Working_RC_Calcs.getC(study_area_id, project_id)
		print C
		A = drainage_area.getValue("SHAPE_Area") / 43560
		I = 116 / ( tc + 17)
		peak_runoff =  C * I * A

		#update the peakflow in the study sewer
		where = "Project_ID = {} AND StudyArea_ID = '{}' AND StudySewer = 'Y'".format(project_id, study_area_id)
		with arcpy.da.UpdateCursor(study_sewers, ['Peak_Runoff'], where_clause=where) as cursor:
			for sewer in cursor:
				sewer[0] = peak_runoff
				cursor.updateRow(sewer)

		#replacement pipe characteristics
		#replacementCapacity = max(peak_runoff, limitingPipe['capacity']) #capacity provided in new pipe should match existing Q or runoff Q (never decrease capacity)
		replacementCapacity = peak_runoff #replacement pipe capacity can be decreased from existing
		replacementD = max( minimumEquivalentCircularPipe(replacementCapacity, limitingSewer['Slope']), 18) #pipe diameter (inches) needed to pass the required Q, with a minimum D if 18 inches
		minimumGrade = minSlopeRequired (shape="CIR", diameter=replacementD, height=None, width=None, peakQ=replacementCapacity)
		#minimumGrade = minSlopeRequired(limitingPipe['Shape'], limitingPipe['D'], limitingPipe['H'], limitingPipe['W'], replacementCapacity)

		#set row values and update row
		drainage_area.setValue("Runoff_Coefficient", C)
		drainage_area.setValue("Capacity", limitingSewer['capacity'])
		drainage_area.setValue("TimeOfConcentration", tc)
		drainage_area.setValue("StickerLink", limitingSewer['sticker_link'])
		drainage_area.setValue("InstallDate", limitingSewer['intall_year'])
		drainage_area.setValue("Intsensity", round(I, 2)) #NOTE -> spelling error in field name
		drainage_area.setValue("Peak_Runoff", round(peak_runoff, 2))
		drainage_area.setValue("Size", limitingSewer['Label']) #show existing size
		drainage_area.setValue("ReplacementSize", str(replacementD))
		drainage_area.setValue("MinimumGrade", round(minimumGrade, 4))
		drainage_area.setValue("StudyShed", limitingSewer['Shed'])
		drainage_areas_cursor.updateRow(drainage_area)

	del drainage_areas_cursor,



#iterate through pipes and run calcs
#def runCalcs (study_pipes_cursor):
def run_hydraulics(project_id, study_sewers, study_area_id=None):

	where = utils.where_clause_from_user_input(project_id, study_area_id)
	arcpy.AddMessage("where = {}".format(where))
	study_sewers_cursor = arcpy.UpdateCursor(study_sewers, where_clause = where)

	for sewer in study_sewers_cursor:

		#Grab pipe parameters
		S 		= sewer.getValue("Slope_Used") #slope used in calculations
		S_orig	= sewer.getValue("Slope") #original slope from DataConv data
		L 		= sewer.shape.length #access geometry directly to avoid bug where DA perimeter is read after join
		D 		= sewer.getValue("Diameter")
		H 		= sewer.getValue("Height")
		W 		= sewer.getValue("Width")
		Shape 	= sewer.getValue("PIPESHAPE")
		U_el	= sewer.getValue("UpStreamElevation")
		D_el	= sewer.getValue("DownStreamElevation")
		id 		= sewer.getValue("OBJECTID")
		TC		= sewer.getValue("TC_Path")
		ss		= sewer.getValue("StudySewer")
		tag 	= sewer.getValue("Tag")

		#boolean flags for symbology
		missingData = False #boolean representing whether the pipe is missing important data
		isTC = checkPipeYN(TC) #False
		isSS = checkPipeYN(ss) #False
		calculatedSlope = False
		minSlopeAssumed = False

		#check if slope is Null, try to compute a slope or asssume a minimum value
		arcpy.AddMessage("checking  sewer "  + str(id))
		if S_orig is None:
			if (U_el is not None) and (D_el is not None):
				S = ( (U_el - D_el) / L ) * 100.0 #percent
				sewer.setValue("Hyd_Study_Notes", "Autocalculated Slope")
				calculatedSlope = True
				arcpy.AddMessage("calculated slope = " + str(S) + ", ID = " + str(id))
			elif S is not None and S != default_min_slope:
			 	arcpy.AddMessage("Manual slope input on {}".format(id))
			 	sewer.setValue("Hyd_Study_Notes", 'Manual slope input')
				print 'type of thing {}'.format(type(S))
			 	S = float(S)
			else:
				S = default_min_slope
				sewer.setValue("Hyd_Study_Notes", "Minimum " + str(S) +  " slope assumed")
				minSlopeAssumed = True
				arcpy.AddMessage("\t min slope assumed = " + str(S)  + ", ID = " + str(id))

		else: S = S_orig #use DataConv slope if provided

		sewer.setValue("Slope_Used", round(float(S), 2))



		# check if any required data points are null, and skip accordingly
		#logic -> if (diameter or height exists) and (if Shape is not UNK), then enough data for calcs
		if ((D != None) or (H != None)) and (Shape != "UNK" or Shape != None):

			try:
				#compute pipe velocity
				V = (1.49/ getMannings(Shape, D)) * math.pow(hydraulicRadius(Shape, D, H, W), 0.667) * math.pow(float(S)/100.0, 0.5)
				sewer.setValue("Velocity", round(float(V), 2))

				#compute the capacity
				Qmax = xarea(Shape, D, H, W) * V
				sewer.setValue("Capacity", round(float(Qmax), 2))

				#compute travel time in the pipe segment, be conservative if a min slope was used
				if (minSlopeAssumed):
					v_conservative = (1.49/ getMannings(Shape, D)) * math.pow(hydraulicRadius(Shape, D, H, W), 0.667) * math.pow(default_TC_slope/100, 0.5)
					T = (L / v_conservative) / 60 # minutes
				else:
					T = (L / V) / 60 # minutes

				sewer.setValue("TravelTime_min", round(float(T), 3)) #arcpy.AddMessage("time = " + str(T))

			except TypeError:
				arcpy.AddWarning("Type error on pipe " + str(sewer.getValue("OBJECTID")))

		else:
			missingData = True #not enough data for calcs
			arcpy.AddMessage("skipped pipe " + str(sewer.getValue("OBJECTID")))


		#apply symbology tag
		theflag = determineSymbologyTag(missingData, isTC, isSS, calculatedSlope, minSlopeAssumed)
		sewer.setValue("Tag", str(theflag))

		study_sewers_cursor.updateRow(sewer)

	del study_sewers_cursor
