from pymeasure.instruments.keithley import Keithley2400
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import time
import csv




class Control_Keithley:


	def __init__(self, area = 0.048, address='GPIB0::22::INSTR'): 
		"""
			Initializes Keithley 2400 class SMUs
		"""
		self.area = area
		self.wires = 4
		self.compliance_current = 1.05 # A
		self.compliance_voltage = 2 # V
		self.buffer_points = 2
		self._scan_speeds = {
			"H": [0.1, 0.1, 0.1], # [I, V, R]
			"M": [1, 1, 1], # [I, V, R]
			"L": [10, 10, 10], # [I, V, R]
		}
		self._current_nplc = 1
		self._voltage_nplc = 1
		self._resistance_nplc = 1
		self._source_delay = 0.001
		self.__previewFigure = None
		self.__previewAxes = None
		self.connect(keithley_address=address)
		self.preview_figs = {}


	def help(self):
		"""
			Prints useful information to terminal
		"""
		output = "Variables\n"
		output += f'self.area = {self.area}\n'
		output += f'self.wires = {self.wires}\n'
		output += f'self.compliance_current = {self.compliance_current}\n'
		output += f'self.compliance_voltage = {self.compliance_voltage}\n'
		print(output)


	def connect(self, keithley_address):
		"""
			Connects to the GPIB interface
		"""
		self.keithley = Keithley2400(keithley_address)
		self.keithley.reset()
		self.keithley.use_front_terminals()
		self.keithley.apply_voltage()
		self.keithley.wires = self.wires
		self.keithley.compliance_current = self.compliance_current
		self.keithley.buffer_points = self.buffer_points
		self.keithley.source_voltage = 0



	def disconnect(self):
		"""
			Disconnects from the GPIB interface
		"""
		self.keithley.shutdown()

	def _source_voltage_measure_current(self):
		"""
			Sets up sourcing voltage and measuring current
		"""
		self.keithley.apply_voltage()
		self.keithley.measure_current()
		self.keithley.compliance_current = self.compliance_current
		self.keithley.souce_voltage = 0


	def _source_current_measure_voltage(self):
		"""
			Sets up sourcing current and measuring voltage
		"""
		self.keithley.apply_current()
		self.keithley.measure_voltage()
		self.keithley.compliance_voltage = self.compliance_voltage
		self.keithley.source_current = 0


	def _measure(self):
		"""
			Measures voltage, current, and resistance
			
			Returns:
				list(np.ndarray): voltage (V), current (A), resistance (Ohms)
		"""
		self.keithley.config_buffer(self.buffer_points)
		self.keithley.start_buffer()
		self.keithley.wait_for_buffer()
		return self.keithley.means

	def _measure_2(self, **kwargs):
		counts = kwargs.get('buffer_counts', self.buffer_points)
		trigger_delay = kwargs.get('trigger_delay', 0) # auto-set to 0 in keithley
		timeout = kwargs.get('buffer_timeout', 60) # stop the buffer after this many seconds
		interval = kwargs.get('buffer_interval', 0.1) # how many seconds between pings to check if buffer is full
		self.keithley.config_buffer(points = counts, delay = trigger_delay)
		t0_ = time.time()
		self.keithley.start_buffer()
		self.keithley.wait_for_buffer(timeout = timeout, interval = interval)
		b_t = time.time() - t0_
		return self.keithley.means, self.keithley.standard_devs, b_t

	def _jv_sweep_2(self, vstart, vend, vsteps, source_delay, buffer_counts, NPLC = [1, 1, 1], delay_time = 0.001, trigger_time = 0, light = True):

		# initialize arrays:
		v = np.linspace(vstart, vend, vsteps)
		vmeas = np.zeros((vsteps,))
		i = np.zeros((vsteps,))
		v_duration = np.zeros((vsteps,))
		vmeas_std = np.zeros((vsteps,))
		i_std = np.zeros((vsteps,))
		buffer_times = np.zeros((vsteps,))

		# set scan settings:
		i_n, v_n, r_n = NPLC
		self.keithley.current_nplc = i_n
		self.keithley.voltage_nplc = v_n
		self.keithley.resistance_nplc = r_n
		self.keithley.source_delay = source_delay # seconds

		# set scan:
		self._source_voltage_measure_current()
		t0 = time.time()
		self.keithley.source_voltage = vstart
		self.keithley.enable_source()

		# if light:
			# self.open_shutter()
		for m, v_ in enumerate(v):
			if m > 0:
				t0 = time.time()
			self.keithley.source_voltage = v_
			means, std, b_t = self._measure_2(buffer_counts = buffer_counts, trigger_time = trigger_time)
			vmeas[m], i[m], _ = means
			vmeas_std[m], i_std[m], _ = std
			v_duration[m] = time.time() - t0
			buffer_times[m] = b_t
		# if light:
			# self.close_shutter()
		self.keithley.disable_source()

		# re-set to defaults:
		self.keithley.current_nplc = self._current_nplc
		self.keithley.voltage_nplc = self._voltage_nplc
		self.keithley.resistance_nplc = self._resistance_nplc
		self.keithley.source_delay = self._source_delay

		return v, i, vmeas, vmeas_std, i_std, v_duration, buffer_times, light
	
	def _format_jv_2(self, v, i, vmeas, vmeas_std, i_std, v_duration, source_delay, buffer_times, light, name, dir, scan_number, scan_speed, preview = True):
		"""
			Uses output of _jv_sweep along with crucial info to preview and save JV data
			
			Args:
				v (np.ndarray(float)): voltage array (output from _sweep_jv_2)
				i (np.ndarray(float)): current array (output from _sweep_jv_2)
				vmeas (np.ndarray(float)): measured voltage array (output from _sweep_jv_2)
				vmeas_std (np.ndarray(float)): measured voltage standard deviation array (output from _sweep_jv_2)
				i_std (np.ndarray(float)): measured current standard deviation array (output from _sweep_jv_2)
				v_duration (np.ndarray(float)): Duration of each voltage step (output from _sweep_jv_2)
				source_delay (float): Duration of source delay step of SMU cycle (seconds)
				buffer_times (np.ndarray(float)): How long the buffer was open for each voltage step (output from _sweep_jv_2)
				light (boolean = True): boolean to describe status of light
				name (string): name of device
				dir (string): direction -- fwd or rev
				scan_number (int): suffix for multiple scans in a row
				scan_speed (string): Scan Rate is Low (L), Medium (M), or High (H)
				preview (boolean = True): option to preview in graph
		"""
		j = []
		j_std = []
		for i_, i_std_ in zip(i, i_std):
			j.append(-i_*1000/self.area) # amps to mA/cm2, sign flip for solar cell current convention
			j_std.append(i_std_*1000/self.area)
		p = [j_*v_ for j_, v_ in zip(j, vmeas)]
		p_std = [(j_*v_)*np.sqrt(((v_std**2)/v_) + ((j_std**2)/j_)) for j_, j_std, v_, v_std in zip(j, j_std, vmeas, vmeas_std)]
		
		data = pd.DataFrame({
			"Voltage (V)": v,
			"Current Density (mA/cm2)": j,
			"Measured Voltage (V)": vmeas,
			"Current (A)": i,
			"Power Density (mW/cm2)": p,
			"Voltage Step Duration (s)": v_duration,
			"Voltage Step Measurement Buffer Duration (s)": buffer_times,
			"Measured Voltage Standard Deviation (V)": vmeas_std,
			"Measured Current Density Standard Deviation (mA/cm2)": j_std,
			"Measured Current Standard Deviation (A)": i_std,
			"Power Density Standard Deviation (mW/cm2)": p_std,
		})
		# save csv
		if light:
			light_on_off = "light"
		else:
			light_on_off = "dark"
		if scan_number is None:
			scan_n = ""
		else:
			scan_n = f"_{scan_number}"
		if scan_speed is None:
			scan_s = ""
		else:
			scan_s = f"_{scan_speed}"
		if source_delay is None:
			scan_d = ""
		else:
			scan_d_ = f"_{source_delay}"
			first, second = scan_d_.split('.')
			scan_d = "{}-{}".format(first, second)
		data.to_csv(f"{name}{scan_n}_{dir}_{light_on_off}{scan_s}{scan_d}.csv")

		# preview
		if preview:
			self._preview(v, j,'Voltage (V)','Current Density (mA/cm2)', f'{name}{scan_n}_{dir}_{light_on_off}{scan_s}')
		

	def _preview(self,xd,yd,xl,yl,label):
		"""
			Appends the [xd,yd] arrays to preview window with labels [xl,yl] and trace label label.
			
			Args:
				xd (list): x value
				yd (list): y value
				yl (string): y label
				xl (string): xlabel
				label (string): label for graph
		"""

		def handle_close(evt, self):
			del self.preview_figs[f'{xl},{yl}']


		if f'{xl},{yl}' not in self.preview_figs.keys():
			plt.ioff()
			self.__previewFigure, self.__previewAxes = plt.subplots()
			self.__previewFigure.canvas.mpl_connect('close_event', lambda x: handle_close(x, self))	# if preview figure is closed, lets clear the figure/axes handles so the next preview properly recreates the handles
			self.__previewAxes.set_xlabel(xl)
			self.__previewAxes.set_ylabel(yl)
			self.__previewAxes.set_ylim(0,30)
			self.__previewAxes.set_xlim(-.2,2)
			plt.ion()
			plt.show()
			self.preview_figs[f'{xl},{yl}'] = [self.__previewFigure, self.__previewAxes]

		if len(xd) == 1:
			self.preview_figs[f'{xl},{yl}'][1].scatter([xd],[yd], label = label)
		else:	
			self.preview_figs[f'{xl},{yl}'][1].plot(xd,yd, label = label)
		self.preview_figs[f'{xl},{yl}'][1].legend()
		self.preview_figs[f'{xl},{yl}'][0].canvas.draw()
		self.preview_figs[f'{xl},{yl}'][0].canvas.flush_events()
		time.sleep(1e-4)		#pause allows plot to update during series of measurements 


	def _jv_sweep(self, vstart, vend, vsteps, light = True):
		""" 
			Workhorse function to run a singular JV sweep.
			
			Args:
				vstart (foat): starting voltage for JV sweep (V)
				vend (float): ending voltage for JV sweep (V)
				vsteps (int): number of voltage steps
				light (boolean = True): boolean to describe light status
			
			Returns:
				list: Voltage (V), Current Density (mA/cm2), Current (A), and Measured Voltage (V) arrays and Light Boolean
		"""
		
		# setup v, vmeas, i
		v = np.linspace(vstart, vend, vsteps)
		vmeas = np.zeros((vsteps,))
		i = np.zeros((vsteps,))
		
		# set scan
		self._source_voltage_measure_current()
		self.keithley.source_voltage = vstart
		self.keithley.enable_source()

		for m, v_ in enumerate(v):
			self.keithley.source_voltage = v_
			vmeas[m], i[m], _ = self._measure()

		self.keithley.disable_source()
		
		# build dataframe and return
		return v, i, vmeas, light


	def _format_jv(self, v, i, vmeas, light, name, dir, scan_number, preview = True):
		"""
			Uses output of _jv_sweep along with crucial info to preview and save JV data
			
			Args:
				v (np.ndarray(float)): voltage array (output from _sweep_jv)
				i (np.ndarray(float)): current array (output from _sweep_jv)
				vmeas (np.ndarray(float)): measured voltage array (output from _sweep_jv)
				light (boolean = True): boolean to describe status of light
				name (string): name of device
				dir (string): direction -- fwd or rev
				scan_number (int): suffix for multiple scans in a row
				preview (boolean = True): option to preview in graph
		"""
		# calc param
		j = []
		for value in i:
			j.append(-value*1000/self.area) #amps to mA/cm2. sign flip for solar cell current convention)	
		p = [num1*num2 for num1, num2 in zip(j,vmeas)]

		# build dataframe
		data = pd.DataFrame({
			'Voltage (V)': v,
			'Current Density (mA/cm2)': j,
			'Current (A)': i,
			'Measured Voltage (V)': vmeas,
			'Power Density (mW/cm2)': p,
		})
		
		# save csv
		if light:
			light_on_off = "light"
		else:
			light_on_off = "dark"
		if scan_number is None:
			scan_n = ""
		else:
			scan_n = f'_{scan_number}'
		data.to_csv(f'{name}{scan_n}_{dir}_{light_on_off}.csv')

		# preview
		if preview:
			self._preview(v, j,'Voltage (V)','Current Density (mA/cm2)', f'{name}{scan_n}_{dir}_{light_on_off}')
		
		return data


	def _format_spo(self, v, i, vmeas, t, name, preview = True):
		"""
			Uses output of _jv_sweep along with crucial info to preview and save JV data
			
			Args:
				v (np.ndarray(float)): voltage array (output from _sweep_jv)
				i (np.ndarray(float)): current array (output from _sweep_jv)
				t (np.ndarray(float)): current density array (output from _sweep_jv)
				vmeas (np.ndarray(float)): measured voltage array (output from _sweep_jv)
				light (boolean = True): boolean to describe status of light
				name (string): name of device
				dir (string): direction -- fwd or rev
				scan_number (int): suffix for multiple scans in a row
				preview (boolean = True): option to preview in graph
		"""

		# calc params
		j = []
		for value in i:
			j.append(value*1000/self.area) #amps to mA/cm2. sign flip for solar cell current convention)	
		p = [num1*num2 for num1, num2 in zip(j,vmeas)]

		# build dataframe
		data = pd.DataFrame({
			'Voltage (V)': v,
			'Current Density (mA/cm2)': j,
			'Current (A)': i,
			'Measured Voltage (V)': vmeas,
			'Power Density (mW/cm2)': p,
			'Time Elapsed (s)': t,
		})

		# save csv
		data.to_csv(f'{name}_SPO.csv', sep=',')

		# preview
		if preview:
			self._preview(t, p,'Time (s)','Power (mW/cm2)', f'{name}_SPO')

		return data


	def jsc(self, printed = True) -> float:
		"""
			Conducts a short circut current density measurement
			
			Args:
				printed (boolean = True): boolean to determine if jsc is printed
			
			Returns:
				float: Short Circut Current Density (mA/cm2)
		"""
		self._source_voltage_measure_current()
		self.keithley.source_voltage = 0
		self.keithley.enable_source()
		isc = -self._measure()[1]
		jsc_val = isc*1000/self.area
		self.keithley.disable_source()
		if printed:
			print(f'Isc: {isc:.3f} A, Jsc: {jsc_val:.2f} mA/cm2')
		return jsc_val


	def voc(self, printed = True) -> float:
		"""
			Conduct a Voc measurement
			
			Args:
				printed (boolean = True): boolean to determine if voc is printed 
			
			Returns:
				float: Open circut voltage (V)
		"""
		self._source_current_measure_voltage()
		self.souce_current = 0
		self.keithley.enable_source()
		voc_val = self._measure()[0]
		self.keithley.disable_source()
		if printed:
			print(f'Voc: {voc_val*1000:.2f} mV')
		return voc_val


	def jv(self, name, direction, vmin, vmax, vsteps = 50, light = True, preview = True):
		"""
			Conducts a JV scan, previews data, saves file
			
			Args:
				name (string): name of device
				direction (string): direction -- fwd, rev, fwdrev, or revfwd
				vmin (float): start voltage for JV sweep (V)
				xmax (float): end voltage for JV sweep (V)
				vsteps (int = 50): number of voltage steps between max and min
				light (boolean = True): boolean to describe status of light
				preview (boolean = True): boolean to determine if data is plotted
		"""

		# fwd is going to be from the lower abs v to higher abs v, reverse will be opposite
		if abs(vmin) < abs(vmax):
			v0 = vmin
			v1 = vmax
		elif abs(vmin) > abs(vmax):
			v0 = vmax
			v1 = vmin

		# seperate on call using _jv_sweep and _format_jv functions for light and dark
		if light:
			if (direction == 'fwd'):
				v, i, vmeas, light = self._jv_sweep(vstart = v0, vend = v1, vsteps = vsteps, light = True)
				data = self._format_jv(v=v, i=i, vmeas=vmeas, light=light, name=name, dir='fwd', scan_number=None, preview = preview)
			elif (direction == 'rev'):
				v, i, vmeas, light = self._jv_sweep(vstart = v1, vend = v0, vsteps = vsteps, light = True)
				data = self._format_jv(v=v, i=i, vmeas=vmeas, light=light, name=name, dir='rev', scan_number=None, preview = preview)
			elif (direction == 'fwdrev'):
				v, i, vmeas, light = self._jv_sweep(vstart = v0, vend = v1, vsteps = vsteps, light = True)
				data = self._format_jv(v=v, i=i, vmeas=vmeas, light=light, name=name, dir='fwd', scan_number=None, preview = preview)
				v, i, vmeas, light = self._jv_sweep(vstart = v1, vend = v0, vsteps = vsteps, light = True)
				data = self._format_jv(v=v, i=i, vmeas=vmeas, light=light, name=name, dir='rev', scan_number=None, preview = preview)
			elif (direction == 'revfwd'):
				v, i, vmeas, light = self._jv_sweep(vstart = v1, vend = v0, vsteps = vsteps, light = True)
				data = self._format_jv(v=v, i=i, vmeas=vmeas, light=light, name=name, dir='rev', scan_number=None, preview = preview)
				v, i, vmeas, light = self._jv_sweep(vstart = v0, vend = v1, vsteps = vsteps, light = True)
				data = self._format_jv(v=v, i=i, vmeas=vmeas, light=light, name=name, dir='fwd', scan_number=None, preview = preview)
		if not light:
			if (direction == 'fwd'):
				v, i, vmeas, light = self._jv_sweep(vstart = v0, vend = v1, vsteps = vsteps, light = False)
				data = self._format_jv(v=v, i=i, vmeas=vmeas, light=light, name=name, dir='fwd', scan_number=None, preview = preview)
			elif (direction == 'rev'):
				v, i, vmeas, light = self._jv_sweep(vstart = v1, vend = v0, vsteps = vsteps, light = False)
				data = self._format_jv(v=v, i=i, vmeas=vmeas, light=light, name=name, dir='rev', scan_number=None, preview = preview)
			elif (direction == 'fwdrev'):
				v, i, vmeas, light = self._jv_sweep(vstart = v0, vend = v1, vsteps = vsteps, light = False)
				data = self._format_jv(v=v, i=i, vmeas=vmeas, light=light, name=name, dir='fwd', scan_number=None, preview = preview)
				v, i, vmeas, light = self._jv_sweep(vstart = v1, vend = v0, vsteps = vsteps, light = False)
				data = self._format_jv(v=v, i=i, vmeas=vmeas, light=light, name=name, dir='rev', scan_number=None, preview = preview)
			elif (direction == 'revfwd'):
				v, i, vmeas, light = self._jv_sweep(vstart = v1, vend = v0, vsteps = vsteps, light = False)
				data = self._format_jv(v=v, i=i, vmeas=vmeas, light=light, name=name, dir='rev', scan_number=None, preview = preview)
				v, i, vmeas, light = self._jv_sweep(vstart = v0, vend = v1, vsteps = vsteps, light = False)
				data = self._format_jv(v=v, i=i, vmeas=vmeas, light=light, name=name, dir='fwd', scan_number=None, preview = preview)

	def spo(self, name, vstart, vstep, vdelay, interval, interval_count, preview = True):
		""" 
			Function to run a SPO test.
			
			Args:
				name (string): name of device/file
				vstart (foat): starting voltage SPO (V)
				vstep (int): voltage to iterate SPO by (V)
				vdelay (int): time to wait between setting voltage and measuring current (s)
				interval (float) : time between measurements (s)
				interval_count (int): number of times to repeat interval
				preview (boolean = True): boolean to determine if data is plotted

		"""
		
		# setup v, vmeas, i arrays for MPP tracking
		v = [] # positive
		vmeas = [] # positive
		i = [] # negative
		t = [] # time
		
		# setup keithly config
		self._source_voltage_measure_current()
		self.keithley.source_voltage = 0
		self.keithley.enable_source()
		vapplied = vstart

		# first measurement
		stime = time.time()
		ctime = time.time() - stime
		n = 0

		# make two measurements, iterating voltage in + direction
		while ctime < interval*(2):

			# if we arent at the next time, sleep; else run
			if (ctime <= n*interval):
				time.sleep(1e-3)
			else:
				self.keithley.source_voltage = vapplied
				time.sleep(vdelay)
				tempv, tempi, _ = self._measure()
				vmeas.append(tempv)
				v.append(vapplied)
				i.append(-1*tempi)
				t.append(ctime)
				print(vapplied,tempv,tempi,n)
				n+=1 
				vapplied += vstep
			ctime = time.time() - stime

		# until we have passed the interval 
		while ctime < interval*(interval_count):

			# if we arent at the next time, sleep; else run
			if ctime < interval*n:
				time.sleep(1e-3)
			else:
				# calculate last powers
				p0 = vmeas[-2]*i[-2]
				p1 = vmeas[-1]*i[-1]
				# iterate in appropriate direction
				if p1 <= p0: #p dec
					if v[-1] < v[-2]: #v dec
						vapplied += vstep 
					else:
						vapplied -= vstep
				else: # p inc
					if v[-1] > v[-2]: #v dec
						vapplied += vstep 
					else:
						vapplied -= vstep

				# apply voltage, measure current and voltage
				self.keithley.source_voltage = vapplied
				time.sleep(vdelay)
				tempv, tempi, _ = self._measure()
				
				# update dictionary & arrays
				vmeas.append(tempv)
				v.append(vapplied)
				i.append(-1*tempi)
				t.append(ctime)
				print(f'Vapplied: {1000*vapplied:0.1f}mV, PCE: {-1000*vapplied*tempi/self.area:0.2f}%')
				n+=1
			ctime = time.time() - stime
		
		# shutoff keithley
		self.keithley.disable_source()

		# save data
		data = self._format_spo(v=v,i=i,t=t,vmeas=vmeas,name=name, preview = preview)


	def jsc_time(self, name, interval, interval_count, preview = True):
		"""
			Conducts multiple jcc scans over a period of time, preveiws data, saves file
			
			Args:
				name (string): name of device
				interval (float): time between JV scans (s)
				interval_count (int): number of times to repeat interval
				preview (boolean = True): boolean to determine if data is plotted
		"""
		
		# create header
		data_df = pd.DataFrame(columns = ["Time", "Jsc (mA/cm2)"])
		data_df.to_csv(f'{name}_jsc.csv', sep = ',')
		del data_df
		xs = []
		ys = []

		# cycle through for duration of test
		n = 0
		stime = time.time()
		ctime = time.time()-stime
		while (ctime <= interval*(interval_count+1)):

			# if we arent at the next time, sleep; else run
			if (ctime < n*interval):
				time.sleep(1e-3)
			else:
				jsc_val = self.voc(printed = False)
				new_data_df = pd.DataFrame(data=zip([ctime],[jsc_val]), index =[n])
				new_data_df.to_csv(f'{name}_jsc.csv', mode='a', header=False, sep=',')
				if preview:
					self._preview([ctime], [jsc_val],'Time (s)','Short Circut Current Density (mA/cm2)', f'{name}')
				del new_data_df
				n += 1

			ctime = time.time()-stime


	def voc_time(self, name, interval, interval_count, preview = True):
		"""
			Conducts multiple Voc scans over a period of time, preveiws data, saves file
			
			Args:
				name (string) : name of device
				interval (float) : time between JV scans (s)
				interval_count (int): number of times to repeat interval
				preview (boolean = True): boolean to determine if data is plotted
		"""
		
		# create header
		data_df = pd.DataFrame(columns = ["Time", "Voc (V)"])
		data_df.to_csv(f'{name}_voc.csv', sep = ',')
		del data_df

		# cycle through for duration of test
		n = 0
		stime = time.time()
		ctime = time.time()-stime
		
		while (ctime <= interval*(interval_count+1)):

			# if we arent at the next time, sleep; else run
			if (ctime < n*interval):
				time.sleep(1e-3)
			else:	
				voc_val = self.voc(printed = False)
				new_data_df = pd.DataFrame(data=zip([ctime],[voc_val]), index =[n])
				new_data_df.to_csv(f'{name}_voc.csv', mode='a', header=False, sep=',')
				if preview:
					self._preview([ctime], [voc_val],'Time (s)','Open Circut Voltage (V)', f'{name}')
				del new_data_df
				n += 1

			ctime = time.time()-stime

	def jv_time(self, name, direction, vmin, vmax, interval, interval_count, vsteps = 50, light = True, preview = True):
		"""
			Conducts multiple JV scans over a period of time, previews data, saves file
			
			Args:
				name (string): name of device
				direction (string): direction -- fwd, rev, fwdrev, or revfwd
				vmin (float): minimum voltage for JV sweep (V)
				vmax (float): maximum voltage for JV sweep (V)
				interval (float): time between JV scans (s)
				interval_count (int): number of times to repeat interval				
				vsteps (int = 50): number of voltage steps between max and min
				light (boolean = True): boolean to describe status of light
				preview (boolean = True): boolean to determine if data is plotted
		"""
		
		# Cycle through # of times selected by user
		n = 0
		stime = time.time()
		ctime = time.time() - stime

		while (ctime <= interval*(interval_count+1)):

			# if we arent at the next time, sleep; else run
			if (ctime <= n*interval):
				time.sleep(1e-3)
			else:
						
				# fwd is going to be from the lower abs v to higher abs v, reverse will be opposite
				if abs(vmin) < abs(vmax):
					v0 = vmin
					v1 = vmax
				elif abs(vmin) > abs(vmax):
					v0 = vmax
					v1 = vmin

				# seperate on call using _jv_sweep and _format_jv functions for light and dark
				if light:
					if (direction == 'fwd'):
						v, i, vmeas, light = self._jv_sweep(vstart = v0, vend = v1, vsteps = vsteps, light = True)
						data = self._format_jv(v=v, i=i, vmeas=vmeas, light=light, name=name, dir='fwd', scan_number=int(ctime), preview = True)
					elif (direction == 'rev'):
						v, i, vmeas, light = self._jv_sweep(vstart = v1, vend = v0, vsteps = vsteps, light = True)
						data = self._format_jv(v=v, i=i, vmeas=vmeas, light=light, name=name, dir='rev', scan_number=int(ctime), preview = True)
					elif (direction == 'fwdrev'):
						v, i, vmeas, light = self._jv_sweep(vstart = v0, vend = v1, vsteps = vsteps, light = True)
						data = self._format_jv(v=v, i=i, vmeas=vmeas, light=light, name=name, dir='fwd', scan_number=int(ctime), preview = True)
						v, i, vmeas, light = self._jv_sweep(vstart = v1, vend = v0, vsteps = vsteps, light = True)
						data = self._format_jv(v=v, i=i, vmeas=vmeas, light=light, name=name, dir='rev', scan_number=int(ctime), preview = True)
					elif (direction == 'revfwd'):
						v, i, vmeas, light = self._jv_sweep(vstart = v1, vend = v0, vsteps = vsteps, light = True)
						data = self._format_jv(v=v, i=i, vmeas=vmeas, light=light, name=name, dir='rev', scan_number=int(ctime), preview = True)
						v, i, vmeas, light = self._jv_sweep(vstart = v0, vend = v1, vsteps = vsteps, light = True)
						data = self._format_jv(v=v, i=i, vmeas=vmeas, light=light, name=name, dir='fwd', scan_number=int(ctime), preview = True)
				if not light:
					if (direction == 'fwd'):
						v, i, vmeas, light = self._jv_sweep(vstart = v0, vend = v1, vsteps = vsteps, light = False)
						data = self._format_jv(v=v, i=i, vmeas=vmeas, light=light, name=name, dir='fwd', scan_number=int(ctime), preview = True)
					elif (direction == 'rev'):
						v, i, vmeas, light = self._jv_sweep(vstart = v1, vend = v0, vsteps = vsteps, light = False)
						data = self._format_jv(v=v, i=i, vmeas=vmeas, light=light, name=name, dir='rev', scan_number=int(ctime), preview = True)
					elif (direction == 'fwdrev'):
						v, i, vmeas, light = self._jv_sweep(vstart = v0, vend = v1, vsteps = vsteps, light = False)
						data = self._format_jv(v=v, i=i, vmeas=vmeas, light=light, name=name, dir='fwd', scan_number=int(ctime), preview = True)
						v, i, vmeas, light = self._jv_sweep(vstart = v1, vend = v0, vsteps = vsteps, light = False)
						data = self._format_jv(v=v, i=i, vmeas=vmeas, light=light, name=name, dir='rev', scan_number=int(ctime), preview = True)
					elif (direction == 'revfwd'):
						v, i, vmeas, light = self._jv_sweep(vstart = v1, vend = v0, vsteps = vsteps, light = False)
						data = self._format_jv(v=v, i=i, vmeas=vmeas, light=light, name=name, dir='rev', scan_number=int(ctime), preview = True)
						v, i, vmeas, light = self._jv_sweep(vstart = v0, vend = v1, vsteps = vsteps, light = False)
						data = self._format_jv(v=v, i=i, vmeas=vmeas, light=light, name=name, dir='fwd', scan_number=int(ctime), preview = True)
				n+=1
			ctime = time.time()-stime

	def jv_rate(self, name, direction, vmin, vmax, vsteps, source_delay = None, speed = "M", buffer_counts = 2, light = True, preview = True):
		if len(direction) == 3:
			dir_0 = direction
			skip_dir_1 = True
		else:
			dir_0 = direction[:3]
			skip_dir_1 = False
			dir_1 = direction[3:]
		
		if abs(vmin) < abs(vmax):
			v0 = vmin
			v1 = vmax
		elif abs(vmin) > abs(vmax):
			v0 = vmax
			v1 = vmin
		# fwd is going from lower to higher V, reverse is opposite
		if 'f' in dir_0:
			vstart_0 = v0
			vend_0 = v1
			vstart_1 = v1
			vend_1 = v0
		else:
			vstart_0 = v1
			vend_0 = v0
			vstart_1 = v0
			vend_1 = v1
		if speed not in ["M", "L", "H"]:
			raise Exception("The `speed` input must be one of ['L', 'M', 'H'], corresponding to low, medium, and high scan rates.")
		NPLC = self._scan_speeds[speed]
		if source_delay is None:
			source_delay = self._source_delay

		v, i, vmeas, vmeas_std, i_std, v_duration, buffer_times, light = self._jv_sweep_2(vstart = vstart_0, vend = vend_0, vsteps = vsteps, source_delay = source_delay, buffer_counts = buffer_counts, NPLC = NPLC, light = light)
		data = self._format_jv_2(v = v, i = i, vmeas = vmeas, vmeas_std = vmeas_std, i_std = i_std, v_duration = v_duration, source_delay = source_delay, buffer_times = buffer_times, light = light, name = name, dir = dir_0, scan_number = None, scan_speed = speed, preview = preview)
		if not skip_dir_1:
			v, i, vmeas, vmeas_std, i_std, v_duration, buffer_times, light = self._jv_sweep_2(vstart = vstart_1, vend = vend_1, vsteps = vsteps, source_delay = source_delay, buffer_counts = buffer_counts, NPLC = NPLC, light = light)
			data = self._format_jv_2(v = v , i = i, vmeas = vmeas, vmeas_std = vmeas_std, i_std = i_std, v_duration = v_duration, source_delay = source_delay, buffer_times = buffer_times, light = light, name = name, dir = dir_1, scan_number = None, scan_speed = speed, preview = preview)



	def jv_spo(self, name, direction, vmin, vmax, vsteps, sweep_speed, sweep_buffer_counts, light = True, preview = True):

		# format jv sweep

		# take jv sweep

		# dump jv sweep data

		# calculate MPP

		# format SPO

		# take SPO

		# dump SPO data
		raise Exception('Eric has not finished this yet.')