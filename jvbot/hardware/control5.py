from pymeasure.instruments.keithley import Keithley2400
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import time
import csv
from time import sleep,time

#################################################
# THIS IS EXPERIMENTAL CODE FOR SCAN RATE and DARK JVs #
#################################################

class Control:


	def __init__(self, area = 0.048, address='GPIB0::22::INSTR'):
		"""
			Initializes Keithley 2400 class SMUs
		"""
		self.area = area
		self.pause = 0.001
		self.wires = 4
		self.compliance_current = 1.05 #2 #1.05 # 1.05 # A
		self.compliance_voltage = 20 #80 #2 # V
		self.buffer_points = 1
		self.counts = 1
        self.iNPLC = 1
        self._scan_speeds = {
            "S": 10, # slow measurement speed
			"M": 1, # medium measurement speed
			"F": 0.1 # fast measurement speed
		}
        self._voltage_nplc = 1
        self._resistance_nplc = 1
        self._source_delay = 0.001

		self.__previewFigure = None
		self.__previewAxes = None
		self.connect(keithley_address=address)
		self.preview_figs = {}

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

	def _source_voltage_measure_current(self, NPLC):

        self.keithley.current_nplc = NPLC
        # self.keithley.voltage_nplc = NPLC
        # self.keithley.resistance_nplc = NPLC
		self.keithley.apply_voltage()
		self.keithley.measure_current()
		self.keithley.sample_continuously()
		self.keithley.compliance_current = self.compliance_current
		self.keithley.source_voltage = 0

	def _measure(self):

		# self.keithley.config_buffer(self.counts)
		# self.keithley.start_buffer()
		# self.keithley.wait_for_buffer()
		return self.keithley.read().strip()

	def _execute_step(self, voltage_step, source_delay, measure_duration):
		t0 = time.time()
		self.keithley.source_voltage(voltage_step)
		if source_delay > 0:
			time.sleep(source_delay)    
        v_delay_ = time.time() - t0
        t0 = time.time()
        t = time.time()
		i = []
		while t - t0 <= measurement_duration:
            t = time.time()
            i_ = float(self._measure())
			i.append(i_)
		return np.mean(i), np.std(i), v_delay_, t - t0

	def _jv_sweep(self, vstart, vend, vsteps, source_delay = 0, NPLC, light = True):

		v = np.linspace(vstart, vend, vsteps)
		# vmeas = np.zeros((vsteps,))
		i = np.zeros((vsteps,))
        i_std = np.zeros((vsteps,))
        v_delay = np.zeros((vsteps,))
        measure_duration = np.zeros((vsteps,))
        step_duration = np.zeros((vsteps,))
		self._source_voltage_measure_current(NPLC)
		self.keithley.source_voltage = vstart
		self.keithley.enable_source()

		begin_time = time.time()
        t0 = time.time()
		for m, v_ in enumerate(v):
            if m > 0:
                t0 = time.time()
			i[m], i_std[m], v_delay[m], measure_duration[m] = self._execute_step(voltage, source_delay, measure_duration)
            step_duration[m] = time.time() - t0
		
		end_time = time.time()
		times = end_time-begin_time
		self.keithley.disable_source()
        # reset to defaults:
        self.keithley.current_nplc = self._current_nplc
        
		return v, i, v_delay, measure_duration, step_duration, light, times

    def _format_jv(self, v, i, i_std, v_delay, measure_duration, step_duration, times, light_on_off = True, dir = "fwd", scan_number = "S1", scan_speed = "M", source_delay = None, preview = True):
        """
            Uses output of _jv_sweep along with crucial info to preview and save JV data

            Args:
                v (np.ndarray(float)): voltage array (output from _jv_sweep)
                i (np.ndarray(float)): current array (output from _jv_sweep)
                i_std (np.ndarray(float)): standard deviation of current measurements per voltage step (output from _jv_sweep)
                v_delay (np.ndarray(float)): Duration of settlement time after applying the fresh voltage step to the cell (output from _jv_sweep)
                measure_duration (np.ndarray(float)): Duration of measurement period after settlement time finishes (output from _jv_sweep)
                step_duration (np.ndarray(float)): Full duration of each voltage step (output from _jv_sweep)
                light_on_off (boolean): For file name generation, is the lamp on?
                dir (str): For file name generation, was this a Fwd or Rev scan?
                scan_number (boolean): For file name generation, which repeat scan is this?
                scan_speed (boolean): For file name generation, are we speedy, average, or leisurely? (~V/s)
                source_delay (number): For file name generation, what source_delay/current settlement duration did this scan plan to use?
        """
        j = [-i_*1000/self.area for i_ in i]
        j_std = [-i_*1000/self.area for i_ in i_std]
        p = [j_*v_ for j_, v_ in zip(j, v)]

        data = pd.DataFrame(
            "Times (s)": times,
            "Voltage (V)": v,
            "Current Density (mA/cm2)": j,
            "Current (A)": i,
            "Power Density (mW/cm2)": p,
            "Current Settlement Duration (s)": v_delay,
            "Current Measurement Duration (s)": measure_duration,
            "Voltage Step Duration (s)": step_duration,
            "Measured Current Density Standard Deviation (mA/cm2)": j_std,
            "Measured Current Standard Deviation (A)": i_std
        )
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
            scan_s = f"_SS{scan_speed}"
        if source_delay is None:
            scan_d = ""
        else:
            scan_d_ = f"_{source_delay}"
            first, second = scan_d_.split('.')
            scan_d = "{}-{}".format(first, second)
        data.to_csv(f"{name}{scan_n}_{dir}_{light_on_off}{scan_s}{scan_d}.csv")

        if preview:
            self._preview(v, j, 'Voltage (V)', 'Current Density (mA/cm2)', f'{name}{scan_n}_{dir}_{light_on_off}{scan_s}')


	def jv(self, name, direction, vmin, vmax, vsteps = 50, speed_opt = 'M', source_delay = None, measure_duration = None, light = True, pause=False, preview = True):
        
        if len(direction) == 3:
            dir_0 = direction; skip_dir_1 = True
        else:
            dir_0 = direction[:3]; skip_dir_1 = False; dir_1 = direction[3:]
        
		if abs(vmin) < abs(vmax):
			v0 = vmin
			v1 = vmax
		elif abs(vmin) > abs(vmax):
			v0 = vmax
			v1 = vmin
        # fwd is from low -> high V, reverse is opposite
        if 'f' in dir_0:
            vstart_0 = v0; vend_0 = v1
            vstart_1 = v1; vend_1 = v0
        else:
            vstart_0 = v0; vend_0 = v1
            vstart_1 = v1; vend_1 = v0
        if speed_opt not in ["Medium", "Slow", "Fast"]:
            raise Exception("The `speed` input must be 'M', 'S', or, 'F', corresponding to Medium, Slow, Fast NPLC measurement rates.")
        NPLC = self._scan_speeds[speed_opt]
        if source_delay is None:
            source_delay = self._source_delay
        if measure_duration is None:
            measure_duration = 10
        
        v, i, v_delay, measure_duration_, step_duration, light, times = self._jv_sweep_2(vstart = vstart_0, vend = vend_0, vsteps = vsteps, source_delay = source_delay, measure_duration = measure_duration, NPLC = NPLC, light = light)
		data = self._format_jv_2(v = v, i = i, i_std = i_std, v_delay = v_delay, measure_duration = measure_duration_, step_duration = step_duration, times = times, light_on_off = light, dir = dir_0, scan_number = scan_n, scan_speed = speed_opt, source_delay = source_delay, preview = True)
		if not skip_dir_1:
			v, i, vmeas, vmeas_std, i_std, v_duration, buffer_times, light = self._jv_sweep_2(vstart = vstart_1, vend = vend_1, vsteps = vsteps, source_delay = source_delay, measure_duration = measure_duration, NPLC = NPLC, light = light)
			data = self._format_jv_2(v = v, i = i, i_std = i_std, v_delay = v_delay, measure_duration = measure_duration_, step_duration = step_duration, times = times, light_on_off = light, dir = dir_1, scan_number = scan_n, scan_speed = speed_opt, source_delay = source_delay, preview = True)


		

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
		self.open_shutter()
		isc = -self._measure()[1]
		jsc_val = isc*1000/self.area
		self.close_shutter()
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
		self.open_shutter()
		voc_val = self._measure()[0]
		self.close_shutter()
		self.keithley.disable_source()
		if printed:
			print(f'Voc: {voc_val*1000:.2f} mV')
		return voc_val


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
		sleep(1e-4)		#pause allows plot to update during series of measurements 
