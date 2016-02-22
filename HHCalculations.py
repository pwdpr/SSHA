#hydraulic and hydrologic calculation tools

import arcpy
from arcpy import env
import math

# =================
# DATA CONNECTIONS
# =================

geodb = r"\\PWDHQR\Data\Planning & Research\Linear Asset Management Program\Water Sewer Projects Initiated\03 GIS Data\Hydraulic Studies\Small_Sewer_Capacity.gdb"
study_pipes = geodb + r"\StudiedWasteWaterGravMains"
study_areas = geodb + r"\Small_Sewer_Drainage_Areas"


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
	
	try:
		n = getMannings(shape, diameter)
		A = xarea(shape, diameter, height, width)
		Rh = hydraulicRadius(shape, diameter, height, width )
		
		s =  math.pow((n * peakQ) / ( 1.49 * A * math.pow(Rh, 0.667) ), 2)
		s = math.ceil(s*1000.0)/1000.0 #round up to nearest 10th of a percent
		
		return round(s*100.0, 1) #percent, round here to fix weird floating point inaccuracy
		
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
		#during the first run through, should apply these default flags, and skip all other calcs
		pipe.setValue("TC_Path", "N")
		pipe.setValue("StudySewer", "N")
		pipe.setValue("Tag", "None")
		study_pipes_cursor.updateRow(pipe)
	
	del study_pipes_cursor

def minimumCapacityStudySewer(studypipes, study_area_id):
	#Return the minimum study sewer capacity in a given study area
	
	#search cursor on study sewers in ascending order on capacity
	where = "StudyArea_ID = '" + study_area_id + "' AND StudySewer = 'Y'"
	fs ="Capacity; OBJECTID; STICKERLINK; Year_Installed; PIPESHAPE; Diameter; Height; Width;Slope_Used;LABEL" #fields to pull
	pipesCursor = arcpy.SearchCursor(studypipes, where_clause = where, fields=fs, sort_fields="Capacity D")
	
	#return first value, being the minimum capacity
	#capacity = 0.0
	#id = "null"
	for pipe in pipesCursor:
		capacity 		= pipe.getValue("Capacity")
		id 				= pipe.getValue("OBJECTID")
		sticker_link 	= pipe.getValue("STICKERLINK")
		intall_year 	= pipe.getValue("Year_Installed")
		D 				= pipe.getValue("Diameter")
		H 				= pipe.getValue("Height")
		W 				= pipe.getValue("Width")
		Shape 			= pipe.getValue("PIPESHAPE")
		slope			= pipe.getValue("Slope_Used")
		label			= pipe.getValue("LABEL")
		continue #move on after first iteration
	
	del pipesCursor
	return {'capacity':capacity, 'id':id, 'sticker_link':sticker_link, 'intall_year':intall_year, 'D':D, 'H':H, 'W':W, 'Shape':Shape, 'Slope':slope, 'Label':label}
		


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
def runHydrology(drainage_areas_cursor):
	
	for drainage_area in drainage_areas_cursor:
		
		#work with each study area and determine the pipe calcs based on study area id
		study_area_id = drainage_area.getValue("StudyArea_ID")
		
		#CALCULATIONS ON TC PATH PIPES
		tc = timeOfConcentration(study_pipes, study_area_id)
				
		#find limiting pipe in study area
		limitingPipe =minimumCapacityStudySewer(study_pipes, study_area_id)
		capacity = limitingPipe['capacity']
		arcpy.AddMessage("\t limted pipe slope = " + str(limitingPipe['Slope']) + ", ID = " + str(id))
		
		#RUNOFF CALCULATIONS
		C = drainage_area.getValue("Runoff_Coefficient")
		A = drainage_area.getValue("SHAPE_Area") / 43560
		I = 116 / ( tc + 17)
		peak_runoff =  C * I * A
		
		#replacement pipe characteristics
		#replacementCapacity = max(peak_runoff, limitingPipe['capacity']) #capacity provided in new pipe should match existing Q or runoff Q (never decrease capacity)
		replacementCapacity = peak_runoff #replacement pipe capacity can be decreased from existing
		replacementD = max( minimumEquivalentCircularPipe(replacementCapacity, limitingPipe['Slope']), 18) #pipe diameter (inches) needed to pass the required Q, with a minimum D if 18 inches  
		minimumGrade = minSlopeRequired (shape="CIR", diameter=replacementD, height=None, width=None, peakQ=replacementCapacity) 
		#minimumGrade = minSlopeRequired(limitingPipe['Shape'], limitingPipe['D'], limitingPipe['H'], limitingPipe['W'], replacementCapacity) 
		
		#set row values and update row
		drainage_area.setValue("Capacity", limitingPipe['capacity'])
		drainage_area.setValue("TimeOfConcentration", tc)
		drainage_area.setValue("StickerLink", limitingPipe['sticker_link'])
		drainage_area.setValue("InstallDate", limitingPipe['intall_year'])
		drainage_area.setValue("Intsensity", round(I, 2)) #NOTE -> spelling error in field name
		drainage_area.setValue("Peak_Runoff", round(peak_runoff, 2))
		drainage_area.setValue("Size", limitingPipe['Label']) #show existing size
		drainage_area.setValue("ReplacementSize", str(replacementD))
		drainage_area.setValue("MinimumGrade", round(minimumGrade, 4))
		drainage_areas_cursor.updateRow(drainage_area)
		

	del drainage_areas_cursor,
	
	
#iterate through pipes and run calcs
def runCalcs (study_pipes_cursor):

	for pipe in study_pipes_cursor:
		
		#Grab pipe parameters
		S 		= pipe.getValue("Slope_Used") #slope used in calculations 
		S_orig	= pipe.getValue("Slope") #original slope from DataConv data
		L 		= pipe.shape.length #access geometry directly to avoid bug where DA perimeter is read after join
		D 		= pipe.getValue("Diameter")
		H 		= pipe.getValue("Height")
		W 		= pipe.getValue("Width")
		Shape 	= pipe.getValue("PIPESHAPE")
		U_el	= pipe.getValue("UpStreamElevation")
		D_el	= pipe.getValue("DownStreamElevation")
		id 		= pipe.getValue("OBJECTID")
		TC		= pipe.getValue("TC_Path")
		ss		= pipe.getValue("StudySewer")
		tag 	= pipe.getValue("Tag")
		
		#boolean flags for symbology
		missingData = False #boolean representing whether the pipe is missing important data
		isTC = checkPipeYN(TC) #False
		isSS = checkPipeYN(ss) #False
		calculatedSlope = False
		minSlopeAssumed = False
		
		#check if slope is Null, try to compute a slope or asssume a minimum value
		arcpy.AddMessage("checking  pipe "  + str(id) + ", has length = " + str(L))
		if S_orig is None:
			if (U_el is not None) and (D_el is not None):
				S = ( (U_el - D_el) / L ) * 100.0 #percent
				pipe.setValue("Hyd_Study_Notes", "Autocalculated Slope")
				calculatedSlope = True
				arcpy.AddMessage("\t calculated slope = " + str(S) + ", ID = " + str(id))
			else:	
				S = default_min_slope
				pipe.setValue("Hyd_Study_Notes", "Minimum " + str(S) +  " slope assumed")
				minSlopeAssumed = True
				arcpy.AddMessage("\t min slope assumed = " + str(S)  + ", ID = " + str(id))
						
		else: S = S_orig #use DataConv slope if provided
		
		pipe.setValue("Slope_Used", round(float(S), 2))
		
		
		
		# check if any required data points are null, and skip accordingly
		#logic -> if (diameter or height exists) and (if Shape is not UNK), then enough data for calcs
		if ((D != None) or (H != None)) and (Shape != "UNK" or Shape != None):
			
			try:
				#compute pipe velocity
				V = (1.49/ getMannings(Shape, D)) * math.pow(hydraulicRadius(Shape, D, H, W), 0.667) * math.pow(float(S)/100.0, 0.5) 
				pipe.setValue("Velocity", round(float(V), 2)) 
				
				#compute the capacity
				Qmax = xarea(Shape, D, H, W) * V
				pipe.setValue("Capacity", round(float(Qmax), 2)) 				
				
				#compute travel time in the pipe segment, be conservative if a min slope was used
				if (minSlopeAssumed):
					v_conservative = (1.49/ getMannings(Shape, D)) * math.pow(hydraulicRadius(Shape, D, H, W), 0.667) * math.pow(default_TC_slope/100, 0.5)
					T = (L / v_conservative) / 60 # minutes
				else:
					T = (L / V) / 60 # minutes
				
				pipe.setValue("TravelTime_min", round(float(T), 3)) #arcpy.AddMessage("time = " + str(T))
			
			except TypeError:
				arcpy.AddWarning("Type error on pipe " + str(pipe.getValue("OBJECTID")))
		
		else:
			missingData = True #not enough data for calcs
			arcpy.AddMessage("skipped pipe " + str(pipe.getValue("OBJECTID")))
		
		
		#apply symbology tag
		theflag = determineSymbologyTag(missingData, isTC, isSS, calculatedSlope, minSlopeAssumed)
		pipe.setValue("Tag", str(theflag))

		study_pipes_cursor.updateRow(pipe)
		
	del study_pipes_cursor