from calibration_loader import CalibrationLoader

def main():
	calibrationLoader =  CalibrationLoader("/home/pi/Documents/Radiolib/examples/NonArduino/Raspberry_copy/mass-flow-controller/MFCCalibrations-ReadDirectlyByFlareCode.txt")
	
	mfc_serial = "BL-20C2H2-M24200697B"
	
	gas = "ACETYLENE"
	
	cal = calibrationLoader.get(serial = mfc_serial, gas = gas)
	print(cal)

if __name__ == "__main__":
	main()
